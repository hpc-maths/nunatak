"""Comparison of two Runs: a pure function of two pivots.

The unit of comparison is the **logical function, inlining included** -
(function, source file) - never the physical symbol: when a recompiled
build inlines the function that was just optimized, its symbol vanishes
and its time melts into the caller, which makes a symbol-grained diff
unreadable. Where sampling attributed addresses, each innermost inline
frame contributes its time under its own name; a Hotspot without
address detail falls back to its logical identity, the same key from
the other end. The module is deliberately not part of the key: the
binary was rebuilt between the two Runs, its path and build-id name a
file, and the pair (function, file) names the code a human edits.

Two rules keep the diff honest. **The statistical uncertainty is
carried in the displayed delta**: each side's time comes from a finite
number of samples, and a difference smaller than the combined sampling
error is not a gain - the verdict travels with the row, never in prose
only. And **what is not comparable is declared, never masked**: two
Machines, two rank topologies, two commands or two time bases do not
prevent the diff, they ride above it as named findings.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass

from nunatak import machine as machine_identity
from nunatak.analysis import sampled_view, time_base
from nunatak.pivot import Run

# Below this share of either Run's sampled time, an entity that appears
# or vanishes is churn, not a story: symbols come and go with inlining.
APPEARANCE_FLOOR = 0.01


@dataclass(frozen=True)
class Side:
    """One entity's measurement on one Run: time and its resolution."""

    value: float
    samples: int

    @property
    def error(self) -> float:
        """Absolute sampling error, decreasing in 1/sqrt(n)."""
        return self.value / math.sqrt(self.samples) if self.samples > 0 else 0.0


@dataclass(frozen=True)
class Delta:
    """One compared entity: the logical function, inlining included.

    `significant` is the verdict that travels with every displayed
    difference: the magnitude of (after - before) beyond the combined
    sampling error of the two sides. `before` or `after` is None when the entity
    exists on one side only - appeared or vanished, which inlining
    alone can cause and the reader must see as such.
    """

    function: str
    file: str | None
    before: Side | None
    after: Side | None

    @property
    def change(self) -> float | None:
        """after minus before, None when the entity has one side only."""
        if self.before is None or self.after is None:
            return None
        return self.after.value - self.before.value

    @property
    def combined_error(self) -> float | None:
        """The sampling error of the difference: both sides combined."""
        if self.before is None or self.after is None:
            return None
        return math.hypot(self.before.error, self.after.error)

    @property
    def significant(self) -> bool:
        """Whether the difference exceeds its own sampling error."""
        change, error = self.change, self.combined_error
        if change is None or error is None:
            return False
        return abs(change) > error


@dataclass(frozen=True)
class Finding:
    """One declared non-comparability: named, shown, never a refusal."""

    name: str
    message: str


@dataclass(frozen=True)
class Comparison:
    """The full diff of two Runs, deltas heaviest-first.

    `unit` is the unit every Side's value is expressed in - "ns" for a
    clock base - and None when the two Runs do not share one: the
    values then only compare within their own side, and the finding
    that says so rides in `findings`.
    """

    before: str
    after: str
    unit: str | None
    total_before: Side
    total_after: Side
    deltas: tuple[Delta, ...]
    findings: tuple[Finding, ...]

    @property
    def total(self) -> Delta:
        """The run-level difference, with the same significance rule."""
        return Delta(
            function="(total)",
            file=None,
            before=self.total_before,
            after=self.total_after,
        )


def compare(before: Run, after: Run) -> Comparison:
    """Diff `after` against `before`.

    Entities below the appearance floor on both sides are folded away:
    inlining makes symbols come and go, and a diff drowned in churn
    hides the regression it exists to show.
    """
    first, first_total = _entities(before)
    second, second_total = _entities(after)
    deltas = []
    for key in sorted(set(first) | set(second)):
        one, two = first.get(key), second.get(key)
        heaviest = max(
            (one.value if one else 0.0) / (first_total.value or 1.0),
            (two.value if two else 0.0) / (second_total.value or 1.0),
        )
        if heaviest < APPEARANCE_FLOOR:
            continue
        deltas.append(
            Delta(function=key[0], file=key[1], before=one, after=two)
        )
    deltas.sort(
        key=lambda delta: max(
            delta.before.value if delta.before else 0.0,
            delta.after.value if delta.after else 0.0,
        ),
        reverse=True,
    )
    unit_before, unit_after = _unit(before), _unit(after)
    return Comparison(
        before=before.name,
        after=after.name,
        unit=unit_before if unit_before == unit_after else None,
        total_before=first_total,
        total_after=second_total,
        deltas=tuple(deltas),
        findings=tuple(_findings(before, after)),
    )


def _entities(run: Run) -> tuple[dict[tuple[str, str | None], Side], Side]:
    """Time by logical function, inlining included, plus the run total.

    A Hotspot whose sampled addresses carry inline chains is ventilated
    over its innermost frames - each frame is the function a human
    would edit. A Hotspot without address detail contributes under its
    own logical name; an unresolved one under its module's base name
    with no file, which two Runs of the same binary still match on.
    """
    base = time_base(run)
    times: dict[tuple[str, str | None], list[float]] = {}
    detailed: dict = {}
    for detail in run.address_details:
        if detail.counter != base or not detail.frames:
            continue
        weights = detailed.setdefault(detail.hotspot, {})
        innermost = detail.frames[-1]
        key = (innermost.function, innermost.file)
        entry = weights.setdefault(key, [0.0, 0])
        entry[0] += detail.value
        entry[1] += detail.sample_count or 0
    total = [0.0, 0]
    for measurement in sampled_view(run):
        if measurement.counter != base or measurement.value is None:
            continue
        total[0] += measurement.value
        total[1] += measurement.sample_count or 0
        hotspot = measurement.hotspot
        ventilated = detailed.get(hotspot)
        if ventilated:
            weight = sum(entry[0] for entry in ventilated.values())
            for key, entry in ventilated.items():
                slot = times.setdefault(key, [0.0, 0])
                slot[0] += measurement.value * (entry[0] / weight)
                slot[1] += entry[1]
            continue
        name = hotspot.logical_identity.name
        if name is None:
            name = os.path.basename(hotspot.logical_identity.module)
            key = (name, None)
        else:
            key = (name, hotspot.logical_identity.source_file)
        slot = times.setdefault(key, [0.0, 0])
        slot[0] += measurement.value
        slot[1] += measurement.sample_count or 0
    entities = {
        key: Side(value=value[0], samples=value[1])
        for key, value in times.items()
    }
    return entities, Side(value=total[0], samples=total[1])


def _findings(before: Run, after: Run) -> list[Finding]:
    """What makes the two Runs not directly comparable, declared."""
    findings = []
    one = machine_identity.identity(before.machine)
    two = machine_identity.identity(after.machine)
    if one != two:
        findings.append(
            Finding(
                name="different-machines",
                message="the Runs were measured on different Machines "
                f"({before.machine.cpu_model or one} vs "
                f"{after.machine.cpu_model or two}): absolute times do not "
                "transfer between them",
            )
        )
    if before.command != after.command:
        findings.append(
            Finding(
                name="different-commands",
                message=f"the commands differ ({' '.join(before.command)} vs "
                f"{' '.join(after.command)}): the workloads may not be "
                "the same",
            )
        )
    ranks_before = _ranks(before)
    ranks_after = _ranks(after)
    if ranks_before != ranks_after:
        findings.append(
            Finding(
                name="different-topologies",
                message=f"the rank topologies differ ({ranks_before} vs "
                f"{ranks_after} ranks): per-entity times aggregate "
                "different worlds",
            )
        )
    base_before, base_after = time_base(before), time_base(after)
    if base_before != base_after:
        findings.append(
            Finding(
                name="different-time-bases",
                message=f"the time bases differ ({base_before} vs "
                f"{base_after}): the clocks do not count the same thing",
            )
        )
    return findings


def _unit(run: Run) -> str | None:
    """The single unit of the Run's time base, None when mixed."""
    base = time_base(run)
    units = {
        m.unit for m in sampled_view(run) if m.counter == base and m.value is not None
    }
    return units.pop() if len(units) == 1 else None


def _ranks(run: Run) -> int:
    """Distinct ranks among a Run's sampled Loci; 0 for a non-MPI Run."""
    return len(
        {
            m.locus.rank
            for m in run.measurements
            if m.locus.rank is not None
        }
    )
