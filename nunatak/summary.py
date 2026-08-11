"""Terminal summary: the first reading level of the report.

At the end of `run`, the log restates what the report's synthesis will
say, in the same vocabulary: findings ordered by decreasing share of the
sampled time, each with its quantified evidence, then "what this report
does not say". Whoever reads only the job log learns fewer details than
the report shows, never less about how solid the numbers are: a
downgraded value states its reason, an absent quantity is written
`unavailable` - never zero, never a blank - and what is missing is
gathered in one named section instead of scattered across footnotes.
"""

from __future__ import annotations

from nunatak.analysis import (
    STATISTICAL_FLOOR_SAMPLES,
    Derived,
    Diagnostic,
    time_base,
)
from nunatak.pivot import Quality, ResolutionLevel, Run, hotspot_level

# Level 1 is "where to start", not the inventory: the terminal shows the
# heaviest findings and states what it leaves out, the report's second
# level holds the full list.
MAX_FINDINGS = 10

# The Ceilings the roofline envelope is built from - the only ones whose
# uncertainty belongs in the synthesis.
ENVELOPE_CEILINGS = ("flops_dp", "dram_bandwidth")

_PREFIXES = ((1e15, "P"), (1e12, "T"), (1e9, "G"), (1e6, "M"), (1e3, "k"))


def _flops(value: float) -> str:
    """A flop/s value with its natural SI prefix, three significant digits."""
    for scale, prefix in _PREFIXES:
        if value >= scale:
            return f"{value / scale:.3g} {prefix}FLOP/s"
    return f"{value:.3g} FLOP/s"


def _percent(value: float) -> str:
    """A fraction as a percentage, one decimal below 1%."""
    return f"{value:.0%}" if value >= 0.01 or value == 0 else f"{value:.1%}"


def _plural(count: int, noun: str) -> str:
    """`1 Hotspot`, `3 Hotspots`."""
    return f"{count} {noun}{'' if count == 1 else 's'}"


def _downgrades(*derived: Derived) -> list[str]:
    """The distinct downgrade reasons among the quantities a finding shows.

    Derived metrics join the reasons of their inputs with `;`, and two
    metrics often share an input: deduplication works on the individual
    reasons, not on the joined strings.
    """
    reasons: dict[str, None] = {}
    for quantity in derived:
        if quantity.quality is Quality.ESTIMATED and quantity.reason:
            for reason in quantity.reason.split("; "):
                reasons[reason] = None
    return list(reasons)


def _finding(diagnostic: Diagnostic) -> list[str]:
    """One finding: identity and regime, then its quantified evidence."""
    hotspot = diagnostic.hotspot
    head = f"  {hotspot.display_name} ({hotspot.resolution_level.value})"
    if diagnostic.share.value is not None:
        head += f" - {_percent(diagnostic.share.value)} of the sampled time"
    if diagnostic.classification is not None:
        head += f" - {diagnostic.classification}"
    else:
        head += f" - no placement: {diagnostic.classification_reason}"
    lines = [head]

    achieved, attainable = diagnostic.achieved, diagnostic.attainable
    if achieved.value is not None and attainable.value is not None:
        evidence = (
            f"    achieved {_flops(achieved.value)}"
            f" of {_flops(attainable.value)} attainable"
        )
        if diagnostic.envelope_fraction.value is not None:
            evidence += f": {_percent(diagnostic.envelope_fraction.value)} of the envelope"
        lines.append(evidence)
    intensity = diagnostic.dram_intensity
    if intensity.value is not None:
        lines.append(f"    DRAM intensity {intensity.value:.3g} flop/byte")
    if diagnostic.classification == "imbalance" and diagnostic.imbalance.value is not None:
        lines.append(
            f"    most-loaded Locus carries {diagnostic.imbalance.value:.1f}x"
            " the least-loaded"
        )

    reasons = _downgrades(
        diagnostic.share,
        intensity,
        achieved,
        attainable,
        diagnostic.envelope_fraction,
    )
    if reasons:
        lines.append(f"    downgraded to estimated: {'; '.join(reasons)}")
    return lines


def _headline(
    run: Run, diagnostics: list[Diagnostic], floor_samples: int
) -> str:
    """Sampling coverage first: what the findings stand on."""
    if not diagnostics:
        return (
            "summary: no Hotspot above the statistical floor"
            f" of {floor_samples} samples"
        )
    head = f"summary: {_plural(len(diagnostics), 'Hotspot')} above the statistical floor"
    covered = sum(d.share.value or 0.0 for d in diagnostics)
    base = time_base(run)
    if base is None:
        return head
    clocked = [m for m in hotspot_level(run.measurements) if m.counter == base]
    samples = sum(m.sample_count or 0 for m in clocked)
    coverage = f"{samples} samples of {base}"
    if all(m.unit == "ns" for m in clocked):
        seconds = sum(m.value for m in clocked if m.value is not None) / 1e9
        coverage += f" over {seconds:.3g} s"
    verb = "holds" if len(diagnostics) == 1 else "hold"
    return f"{head} {verb} {_percent(min(covered, 1.0))} of the sampled time ({coverage})"


def _admissions(
    run: Run, diagnostics: list[Diagnostic], floor_samples: int
) -> list[str]:
    """What this report does not say, gathered in one place."""
    admissions = []
    covered = sum(d.share.value or 0.0 for d in diagnostics)
    below_floor = 1.0 - covered
    if time_base(run) is not None and below_floor > 0.005:
        admissions.append(
            f"{_percent(below_floor)} of the sampled time sits below the"
            f' statistical floor of {floor_samples} samples, aggregated as "others"'
        )
    unresolved = sum(
        d.share.value or 0.0
        for d in diagnostics
        if d.hotspot.resolution_level is ResolutionLevel.UNRESOLVED
    )
    if unresolved > 0:
        admissions.append(
            f"{_percent(unresolved)} of the sampled time is attributed to"
            " no name (unresolved addresses)"
        )
    for ceiling in run.machine.ceilings:
        if ceiling.name in ENVELOPE_CEILINGS and ceiling.quality is Quality.ESTIMATED:
            admissions.append(f"the {ceiling.name} Ceiling is estimated: {ceiling.reason}")
    return admissions


def summarize(
    run: Run,
    diagnostics: list[Diagnostic],
    floor_samples: int = STATISTICAL_FLOOR_SAMPLES,
) -> list[str]:
    """The lines of the terminal summary, findings first, admissions last.

    `diagnostics` is the output of `analysis.diagnose(run)`, already
    ordered by decreasing share; `floor_samples` must be the floor that
    produced it, so the admissions name the threshold actually applied.
    Returns plain lines: the Console decides how they reach the log.
    """
    lines = [_headline(run, diagnostics, floor_samples)]
    for diagnostic in diagnostics[:MAX_FINDINGS]:
        lines.extend(_finding(diagnostic))
    left_out = diagnostics[MAX_FINDINGS:]
    if left_out:
        remaining = sum(d.share.value or 0.0 for d in left_out)
        lines.append(
            f"  ... and {_plural(len(left_out), 'Hotspot')} above the floor,"
            f" holding {_percent(remaining)} of the sampled time"
        )
    admissions = _admissions(run, diagnostics, floor_samples)
    if admissions:
        lines.append("what this report does not say:")
        lines.extend(f"  - {admission}" for admission in admissions)
    return lines
