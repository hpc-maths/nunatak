"""The prompt: a pure function of the measured pivot.

The model's answer is not reproducible; what the model sees is, and it
is therefore an artifact under test, captured by snapshot - any change
to it becomes a diff read in review. That discipline holds the most
dangerous class of bugs here: sending source under `--no-source`,
sending a Hotspot below the statistical floor, letting assembler slip
through. Nothing else executable would hold it.

What the model receives is the deterministic analysis and the source it
explains: the Diagnostic, the Machine's Ceilings with their Quality, the
static loop facts, the distribution of samples by line, the embedded
extract of the physical function and its hot inline frames. What it
never receives: raw assembler - it would be asked to diagnose, exactly
where its errors are least detectable; a quantity the analysis declared
unavailable - absence is the report's to state, not the model's to
narrate around; and a Hotspot without source - deprived of source the
model produces generality, which discredits the whole output. Such a
Hotspot is withheld with a reason the report shows in its place.
"""

from __future__ import annotations

from dataclasses import dataclass

from nunatak.analysis import (
    Derived,
    Diagnostic,
    details_of,
    downgrade_reasons,
    line_shares,
    time_base,
)
from nunatak.pivot import Hotspot, Quality, ResolutionLevel, Run, SourceExtract

# The role the model is given, verbatim in every call. It restates the
# division of labor the architecture imposes: the facts are established
# and labeled, the model explains and suggests, and a fact's downgrade
# reason bounds the confidence of any advice built on it.
SYSTEM_PROMPT = """\
You are the explanation layer of an HPC profiler. You receive facts a
deterministic analysis already established - a roofline placement and
quantities each labeled with its quality (measured, or estimated with
the reason) - and the source code of one hot function. Your role:
1. Explain in plain language why this function performs the way the
   facts say, for a reader without performance expertise.
2. Suggest 2 to 4 concrete optimizations, ordered by expected gain,
   each with a rough estimate of that gain and a short code sketch.
3. Never contradict the facts. When a fact limits an optimization, say
   so. Treat the reason of an estimated quantity as a caveat on any
   conclusion you draw from it.
You explain and suggest from these facts only: you never diagnose,
measure or classify. Answer in compact markdown, no top-level heading,
at most about 400 words.
"""

_PREFIXES = ((1e15, "P"), (1e12, "T"), (1e9, "G"), (1e6, "M"), (1e3, "k"))


@dataclass(frozen=True)
class Request:
    """One explanation to ask: a Hotspot and the prompt it earned."""

    hotspot: Hotspot
    prompt: str


@dataclass(frozen=True)
class Withheld:
    """One explanation that will not be asked, with the reason the
    report shows where the advice was expected."""

    hotspot: Hotspot
    reason: str


def requests(
    run: Run, diagnostics: list[Diagnostic]
) -> tuple[list[Request], list[Withheld]]:
    """The prompts this Run earns, and the Hotspots withheld with why.

    `diagnostics` is the output of `analysis.diagnose(run)`: the
    statistical floor is already applied there, so a Hotspot too thin to
    diagnose never reaches the model - the report narrates the floor,
    the model never hears of it. Within the diagnosed, no source means
    no Explanation: an unresolved Hotspot has nothing to anchor source
    on, and a Run without an extract for a Hotspot - `--no-source`,
    source not found, refused as stale - yields a Withheld carrying the
    recorded reason.
    """
    asked: list[Request] = []
    withheld: list[Withheld] = []
    base = time_base(run)
    for diagnostic in diagnostics:
        hotspot = diagnostic.hotspot
        if hotspot.resolution_level is ResolutionLevel.UNRESOLVED:
            withheld.append(
                Withheld(
                    hotspot=hotspot,
                    reason="Hotspot not resolved: nothing to anchor source on",
                )
            )
            continue
        extract = run.source_of(hotspot)
        if extract is None:
            withheld.append(
                Withheld(
                    hotspot=hotspot,
                    reason="no source available for this Hotspot in the Run",
                )
            )
            continue
        if extract.text is None:
            withheld.append(Withheld(hotspot=hotspot, reason=extract.reason))
            continue
        asked.append(
            Request(hotspot=hotspot, prompt=_prompt(run, diagnostic, extract, base))
        )
    return asked, withheld


def _prompt(
    run: Run, diagnostic: Diagnostic, extract: SourceExtract, base: str | None
) -> str:
    """The prompt of one Hotspot, sections in reading order."""
    sections = [
        _machine_section(run),
        _diagnostic_section(diagnostic),
        _loop_section(run, diagnostic.hotspot),
        _lines_section(run, diagnostic.hotspot, base),
        _source_section(extract),
        "Explain this behavior and suggest optimizations.",
    ]
    return "\n\n".join(section for section in sections if section is not None)


def _machine_section(run: Run) -> str:
    """The Machine and its Ceilings, each with its Quality."""
    machine = run.machine
    lines = ["## Machine"]
    processor = machine.cpu_model or machine.architecture
    identity = f"- {processor}"
    allocated = machine.allocation.visible_cores
    if allocated is not None and machine.logical_cores is not None:
        identity += f", {allocated} of {machine.logical_cores} logical cores allocated"
    elif machine.logical_cores is not None:
        identity += f", {machine.logical_cores} logical cores"
    lines.append(identity)
    for ceiling in machine.ceilings:
        line = f"- ceiling {ceiling.name}: {_si(ceiling.value, ceiling.unit)}"
        if ceiling.quality is Quality.ESTIMATED:
            line += f" (estimated: {ceiling.reason})"
        lines.append(line)
    return "\n".join(lines)


def _diagnostic_section(diagnostic: Diagnostic) -> str:
    """The Diagnostic's facts, in the vocabulary of the report.

    A quantity without value is omitted entirely - the model never
    receives an unavailable fact - while an absent placement is stated
    with its reason: it is a conclusion of the analysis, not a hole in
    it, and advice must not invent the regime the analysis refused to
    name.
    """
    hotspot = diagnostic.hotspot
    lines = [
        f"## Diagnostic for `{hotspot.display_name}` "
        f"({hotspot.resolution_level.value} level)"
    ]
    if diagnostic.share.value is not None:
        lines.append(
            "- share of the sampled time: "
            f"{diagnostic.share.value:.0%}{_downgrade(diagnostic.share)}"
        )
    if diagnostic.classification is not None:
        lines.append(f"- classification: {diagnostic.classification}")
    else:
        lines.append(f"- no roofline placement: {diagnostic.classification_reason}")
    achieved, attainable = diagnostic.achieved, diagnostic.attainable
    if achieved.value is not None and attainable.value is not None:
        line = (
            f"- achieved {_si(achieved.value, achieved.unit)} of "
            f"{_si(attainable.value, attainable.unit)} attainable"
        )
        if diagnostic.envelope_fraction.value is not None:
            line += f": {diagnostic.envelope_fraction.value:.0%} of the envelope"
        line += _downgrade(achieved, attainable, diagnostic.envelope_fraction)
        lines.append(line)
    intensity = diagnostic.dram_intensity
    if intensity.value is not None:
        lines.append(
            f"- DRAM arithmetic intensity: {intensity.value:.3g} "
            f"{intensity.unit}{_downgrade(intensity)}"
        )
    if diagnostic.classification == "imbalance" and diagnostic.imbalance.value is not None:
        lines.append(
            f"- most-loaded Locus carries {diagnostic.imbalance.value:.1f}x "
            "the least-loaded"
        )
    return "\n".join(lines)


def _loop_section(run: Run, hotspot: Hotspot) -> str | None:
    """The static facts of the hot inner loop, when the Run carries them.

    Counts of what the instruction stream demands - never the stream
    itself: this is the analysis that replaces assembler in front of
    the model, per-iteration facts a reader can check against the
    suggestion built on them.
    """
    found = next((a for a in run.loop_analyses if a.hotspot == hotspot), None)
    if found is None:
        return None
    lines = [
        "## Hot inner loop (static analysis of the instruction stream, "
        "insensitive to cache reuse)",
        f"- {found.instructions} instructions per iteration, "
        f"{found.flops_per_iteration:g} FLOPs",
    ]
    fp = found.vector_fp + found.scalar_fp
    if fp:
        ratio = found.vector_fp / fp
        vector = f"- vectorized: {ratio:.0%} of the FP instructions"
        if found.vector_width_bits is not None:
            vector += f", {found.vector_width_bits}-bit"
        lines.append(vector)
    lines.append(
        f"- {found.loaded_bytes} bytes loaded, {found.stored_bytes} stored "
        f"per iteration; {found.gathers} gathers"
    )
    if found.cycles_ports is not None:
        lines.append(
            f"- cycle bounds (model {found.scheduling_model}): "
            f"{found.cycles_ports:g} port-bound, "
            f"{found.cycles_effective:g} steady state"
        )
    return "\n".join(lines)


def _lines_section(run: Run, hotspot: Hotspot, base: str | None) -> str | None:
    """The distribution of samples over the function's source lines."""
    shares = line_shares(details_of(run, hotspot, base))
    if not shares:
        return None
    lines = ["## Samples by source line"]
    lines += [f"- line {line}: {share:.0%}" for line, share in shares]
    return "\n".join(lines)


def _source_section(extract: SourceExtract) -> str:
    """The embedded extract: the physical function and its hot inline
    frames, exactly the text the Run carries."""
    where = f"`{extract.file}`"
    if extract.start_line is not None and extract.end_line is not None:
        where += f", lines {extract.start_line}-{extract.end_line}"
    if extract.truncated:
        where += ", truncated"
    return f"## Source ({where})\n```\n{extract.text}\n```"


def _downgrade(*quantities: Derived) -> str:
    """The downgrade reasons of a fact line, appended to it."""
    reasons = downgrade_reasons(*quantities)
    if not reasons:
        return ""
    return f" (estimated: {'; '.join(reasons)})"


def _si(value: float, unit: str) -> str:
    """A value with its natural SI prefix, three significant digits.

    flop/s is spelled FLOP/s, as the terminal summary spells it: the
    prompt speaks the report's vocabulary.
    """
    unit = {"flop/s": "FLOP/s"}.get(unit, unit)
    for scale, prefix in _PREFIXES:
        if value >= scale:
            return f"{value / scale:.3g} {prefix}{unit}"
    return f"{value:.3g} {unit}"
