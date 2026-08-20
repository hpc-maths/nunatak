"""Deterministic analysis engine: a pure function of (pivot, Machine).

Nothing here is persisted - the Diagnostic is recomputed on demand from
the measured pivot and the Machine snapshot, which is what keeps a Run
analyzable years later and the engine testable without hardware. Its
reproducibility is the counterpart of the non-reproducible Explanation:
these are the facts.

Every derived quantity carries its lineage and its Quality, propagated
as the worst of its inputs and never short-circuited: a number displayed
`measured` is measured end to end. Where a source counter does not
exist, the fact is `unavailable` with the reason, rather than
approximate: unavailable is not zero.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from nunatak.pivot import Ceiling, Hotspot, Measurement, Quality, Run, hotspot_level

# A Hotspot below the statistical floor is noise wearing the look of a
# diagnosis: its Measurements stay in the pivot, the Diagnostic skips it.
STATISTICAL_FLOOR_SAMPLES = 30
# Below this fraction of the envelope, neither bound explains the
# performance: the regime is latency.
LATENCY_FRACTION = 0.5
# Above this most-loaded/least-loaded ratio, the imbalance is the story.
IMBALANCE_RATIO = 2.0

# Canonical counter names the engine consumes; the collection side owns
# the mapping from vendor events to these. "flops" is the all-precision
# fallback of microarchitectures that do not split by precision: usable,
# but only as an estimate against the double-precision peak.
FLOP_COUNTERS = ("flops_dp", "flops")
BYTE_COUNTERS = ("dram_bytes",)
CLOCK_COUNTERS = ("task-clock", "cpu-clock")

PRECISION_REASON = (
    "FLOPs not split by precision on this microarchitecture; "
    "compared against the double-precision peak"
)


@dataclass(frozen=True)
class Derived:
    """A quantity computed from raw counters and Ceilings by a formula.

    It remembers where it came from: `lineage` names its inputs,
    `formula` states the computation, and its Quality is the worst of
    its inputs - never set by hand. `unavailable` carries no value and
    always says why.
    """

    name: str
    value: float | None
    unit: str
    quality: Quality
    lineage: tuple[str, ...] = ()
    formula: str | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.quality is Quality.UNAVAILABLE:
            if self.value is not None:
                raise ValueError("'unavailable' is not a value, not even zero")
            if self.reason is None:
                raise ValueError("an unavailable derived metric always says why")
        elif self.value is None:
            raise ValueError(f"a {self.quality.value} derived metric needs a value")
        elif self.quality is Quality.ESTIMATED and self.reason is None:
            raise ValueError("a downgrade to 'estimated' is always motivated")


@dataclass(frozen=True)
class Diagnostic:
    """The deterministic verdict for one Hotspot: its share of the run,
    its roofline placement, and the regime it states.

    A classification states a regime, never a cause; when the placement
    cannot be computed, `classification` is None and
    `classification_reason` says why.
    """

    hotspot: Hotspot
    share: Derived
    dram_intensity: Derived
    achieved: Derived
    attainable: Derived
    envelope_fraction: Derived
    imbalance: Derived
    classification: str | None
    classification_reason: str | None = None


def envelope(
    intensity: float, ceilings: dict[str, Ceiling]
) -> tuple[float, tuple[str, ...], Quality, str | None] | None:
    """The roofline: `min(compute peak, bandwidth x intensity)`.

    The memory diagonal stops at the break point, it never crosses it -
    that formula is a testable invariant. Returns (value, lineage,
    quality, downgrade reason), or None when either Ceiling is missing.
    """
    peak = ceilings.get("flops_dp")
    bandwidth = ceilings.get("dram_bandwidth")
    if peak is None or bandwidth is None:
        return None
    return (
        min(peak.value, bandwidth.value * intensity),
        ("flops_dp", "dram_bandwidth"),
        Quality.worst(peak.quality, bandwidth.quality),
        peak.reason or bandwidth.reason,
    )


def _unavailable(name: str, unit: str, reason: str, lineage=()) -> Derived:
    """An absent quantity that says why it is absent."""
    return Derived(
        name=name,
        value=None,
        unit=unit,
        quality=Quality.UNAVAILABLE,
        lineage=tuple(lineage),
        reason=reason,
    )


def _sum(
    measurements: list[Measurement],
) -> tuple[float, Quality, str | None] | None:
    """Total value over Loci and Passes, with the worst input Quality and
    the reason of the first downgraded input - a motivated downgrade
    travels with its motive."""
    values = [m for m in measurements if m.value is not None]
    if not values:
        return None
    return (
        sum(m.value for m in values),
        Quality.worst(*(m.quality for m in values)),
        next((m.reason for m in values if m.reason is not None), None),
    )


def _first_counter(measured: dict | set, names: tuple[str, ...]) -> str | None:
    """The first of `names` this Run actually measured."""
    for name in names:
        if name in measured:
            return name
    return None


def sampled_view(run: Run) -> list[Measurement]:
    """The sampling layer's Measurements, one Pass per counter.

    A multi-pass run replicates its time base and its witness in every
    Pass: summed across Passes they would double the seconds and halve
    every rate. A counter sampled by several Passes therefore only
    contributes its reference Pass - the first that sampled it - while
    a counter exclusive to one Pass passes through, and a single-pass
    Run comes back unchanged. Every Hotspot-grained reader goes through
    this view; reading `hotspot_level` raw would reintroduce the double
    count.
    """
    sampled = hotspot_level(run.measurements)
    passes: dict[str, set[int]] = {}
    for measurement in sampled:
        passes.setdefault(measurement.counter, set()).add(measurement.pass_index)
    reference = {
        counter: min(indices)
        for counter, indices in passes.items()
        if len(indices) > 1
    }
    return [
        m
        for m in sampled
        if m.counter not in reference or m.pass_index == reference[m.counter]
    ]


# Witness counters: work-proportional counts replicated in every Pass
# of a multi-pass run. Neither the time base nor cycles qualifies,
# measured on the corpus machine: the same work took 69% more
# cpu-seconds on a first pass - the frequency governor ramping up - and
# a memory-bound run costs 4.8e9 then 6.9e9 cycles back to back, stall
# cycles scaling with frequency while DRAM latency does not. The
# retired-FLOP count came back identical to the unit.
WITNESS_COUNTERS = ("flops",)
WITNESS_THRESHOLD = 0.05


@dataclass(frozen=True)
class WitnessVerdict:
    """What the witness says about a multi-pass run's reproducibility.

    `totals` is the witness counter summed per Pass; `spread` their
    max-minus-min over their mean. Beyond `threshold`, the application
    did different work in different Passes - convergence criterion,
    dynamic scheduling - and cross-pass fusion is estimated, never
    silently exact.
    """

    counter: str
    totals: tuple[tuple[int, float], ...]
    spread: float
    threshold: float

    @property
    def consistent(self) -> bool:
        """Whether the Passes agree within the threshold."""
        return self.spread <= self.threshold


def witness_check(
    measurements: list[Measurement], threshold: float = WITNESS_THRESHOLD
) -> WitnessVerdict | None:
    """The witness verdict over raw Measurements, None when fewer than
    two Passes sampled a witness counter - nothing to compare."""
    for counter in WITNESS_COUNTERS:
        totals: dict[int, float] = {}
        for m in hotspot_level(measurements):
            if m.counter == counter and m.value is not None:
                totals[m.pass_index] = totals.get(m.pass_index, 0.0) + m.value
        if len(totals) >= 2:
            values = list(totals.values())
            mean = sum(values) / len(values)
            spread = (max(values) - min(values)) / mean if mean > 0 else 0.0
            return WitnessVerdict(
                counter=counter,
                totals=tuple(sorted(totals.items())),
                spread=spread,
                threshold=threshold,
            )
    return None


def witness_verdict(run: Run) -> WitnessVerdict | None:
    """The witness verdict of a Run, its threshold taken from the Run's
    own effective configuration: a threshold can be tuned, it cannot be
    tuned silently - and the Run carries the tuning that judged it."""
    threshold = run.provenance.effective_configuration.get(
        "passes.witness", WITNESS_THRESHOLD
    )
    return witness_check(run.measurements, float(threshold))


def time_base(run: Run) -> str | None:
    """The counter Hotspot shares of time are stated against: the first
    clock this Run measured, cycles as last resort."""
    counters = {measurement.counter for measurement in sampled_view(run)}
    return _first_counter(counters, CLOCK_COUNTERS + ("cycles",))


def _imbalance(measurements: list[Measurement], counter: str) -> Derived:
    """Most-loaded over least-loaded Locus for `counter`, on demand."""
    per_locus: dict = {}
    for measurement in measurements:
        if measurement.counter == counter and measurement.value is not None:
            per_locus[measurement.locus] = (
                per_locus.get(measurement.locus, 0.0) + measurement.value
            )
    loaded = [value for value in per_locus.values() if value > 0]
    if not loaded:
        return _unavailable(
            "imbalance", "ratio", f"no {counter} value on any Locus"
        )
    return Derived(
        name="imbalance",
        value=max(loaded) / min(loaded),
        unit="ratio",
        quality=Quality.MEASURED,
        lineage=(counter,),
        formula="max over Loci / min over Loci",
    )


def _classify(
    intensity: Derived,
    fraction: Derived,
    imbalance: Derived,
    ceilings: dict[str, Ceiling],
    latency_fraction: float,
    imbalance_ratio: float,
) -> tuple[str | None, str | None]:
    """The regime this Hotspot is in, or the reason none can be stated.

    Imbalance speaks first - a lopsided Hotspot must be rebalanced before
    its roofline placement means anything - then the envelope fraction
    tells latency from the two bounds, and the ridge point tells the
    bounds apart.
    """
    if imbalance.value is not None and imbalance.value >= imbalance_ratio:
        return "imbalance", None
    if intensity.value is None:
        return None, intensity.reason
    if fraction.value is None:
        return None, fraction.reason
    if fraction.value < latency_fraction:
        return "latency-bound", None
    peak, bandwidth = ceilings["flops_dp"], ceilings["dram_bandwidth"]
    ridge = peak.value / bandwidth.value
    return ("memory-bound" if intensity.value < ridge else "compute-bound"), None


@dataclass(frozen=True)
class RankBalance:
    """One rank of the execution topology, as both layers saw it.

    `time` is the rank's cpu time: exact when the counting layer
    counted it, the sum of the rank's own samples when the rank was
    sampled instead - the two sources never mix on one rank. `mpi_time`
    comes from mpiP and is unavailable without it.
    """

    rank: int
    node: str
    time: Derived
    mpi_time: Derived
    sampled: bool


@dataclass(frozen=True)
class Balance:
    """The run-level balance verdict, recomputed on demand - never
    persisted, like every aggregate across Loci.

    `unsampled` names the ranks whose Hotspot-level Measurements are
    unavailable by design (the sampling subset excluded them): the
    admission the report owes the reader, never an extrapolation.
    """

    ranks: tuple[RankBalance, ...]
    imbalance: Derived
    mpi_fraction: Derived
    unsampled: tuple[int, ...]


def _rank_time(
    rank: int, counted: dict[int, float], sampled: dict[int, float]
) -> Derived:
    """The cpu time of one rank, from whichever layer covered it."""
    if rank in counted:
        return Derived(
            name="time",
            value=counted[rank],
            unit="ns",
            quality=Quality.MEASURED,
            lineage=("task-clock",),
            formula="counted over the whole rank",
        )
    if rank in sampled:
        return Derived(
            name="time",
            value=sampled[rank],
            unit="ns",
            quality=Quality.MEASURED,
            lineage=("task-clock",),
            formula="sum of this rank's samples",
        )
    return _unavailable("time", "ns", "this rank left no time measurement")


def balance(run: Run) -> Balance | None:
    """The per-rank balance of `run`, None without a rank topology.

    A pure function of the pivot: the ranks are those the Measurements
    name, sampled ranks are those with Hotspot-level Measurements, and
    every aggregate is computed here, on demand.
    """
    aggregates = [m for m in run.measurements if m.hotspot is None]
    sampled_rows = [
        m for m in sampled_view(run) if m.locus.rank is not None
    ]
    counted: dict[int, float] = {}
    mpi_times: dict[int, float] = {}
    nodes: dict[int, str] = {}
    for measurement in aggregates:
        rank = measurement.locus.rank
        if rank is None or measurement.value is None:
            continue
        nodes.setdefault(rank, measurement.locus.node)
        if measurement.counter in CLOCK_COUNTERS:
            counted[rank] = counted.get(rank, 0.0) + measurement.value
        elif measurement.counter == "mpi_time":
            mpi_times[rank] = mpi_times.get(rank, 0.0) + measurement.value
    sampled: dict[int, float] = {}
    for measurement in sampled_rows:
        rank = measurement.locus.rank
        nodes.setdefault(rank, measurement.locus.node)
        if measurement.counter in CLOCK_COUNTERS and measurement.value is not None:
            sampled[rank] = sampled.get(rank, 0.0) + measurement.value

    everyone = sorted(nodes)
    if not everyone:
        return None

    ranks = []
    for rank in everyone:
        mpi_time = (
            Derived(
                name="mpi_time",
                value=mpi_times[rank],
                unit="ns",
                quality=Quality.MEASURED,
                lineage=("mpi_time",),
                formula="mpiP's wall-clock MPI time of this rank",
            )
            if rank in mpi_times
            else _unavailable("mpi_time", "ns", "mpiP was not preloaded")
        )
        ranks.append(
            RankBalance(
                rank=rank,
                node=nodes[rank],
                time=_rank_time(rank, counted, sampled),
                mpi_time=mpi_time,
                sampled=rank in sampled,
            )
        )

    times = [r.time.value for r in ranks if r.time.value]
    if times and len(times) == len(ranks):
        imbalance = Derived(
            name="imbalance",
            value=max(times) / (sum(times) / len(times)),
            unit="ratio",
            quality=Quality.worst(*(r.time.quality for r in ranks)),
            lineage=("task-clock",),
            formula="max over ranks / mean over ranks",
        )
    elif times:
        imbalance = _unavailable(
            "imbalance", "ratio", "some ranks left no time measurement"
        )
    else:
        imbalance = _unavailable("imbalance", "ratio", "no time on any rank")

    app_times = {
        m.locus.rank: m.value
        for m in aggregates
        if m.counter == "app_time" and m.value is not None and m.locus.rank is not None
    }
    total_app = sum(app_times.values())
    if mpi_times and total_app > 0:
        mpi_fraction = Derived(
            name="mpi_fraction",
            value=sum(mpi_times.values()) / total_app,
            unit="fraction",
            quality=Quality.MEASURED,
            lineage=("mpi_time", "app_time"),
            formula="sum of MPI time / sum of application time, over ranks",
        )
    else:
        mpi_fraction = _unavailable(
            "mpi_fraction", "fraction", "mpiP was not preloaded"
        )

    return Balance(
        ranks=tuple(ranks),
        imbalance=imbalance,
        mpi_fraction=mpi_fraction,
        unsampled=tuple(rank for rank in everyone if rank not in sampled),
    )


def diagnose(
    run: Run,
    floor_samples: int = STATISTICAL_FLOOR_SAMPLES,
    latency_fraction: float = LATENCY_FRACTION,
    imbalance_ratio: float = IMBALANCE_RATIO,
) -> list[Diagnostic]:
    """The Diagnostics of every Hotspot above the statistical floor,
    ordered by decreasing share.

    Placement aggregates the Measurements of all Loci before comparing:
    same scope on both sides, or one rank's performance would face one
    node's Ceiling. The wall time of a Hotspot is approximated by its
    most-loaded Locus - Loci run concurrently.
    """
    ceilings = {ceiling.name: ceiling for ceiling in run.machine.ceilings}
    witness = witness_verdict(run)

    # The counting layer's Locus-level aggregates are whole-process
    # counts: mixed into these totals they would drown the sampled sums
    # and shrink every share - and a replicated counter only counts its
    # reference Pass.
    sampled = sampled_view(run)
    by_hotspot: dict[Hotspot, list[Measurement]] = {}
    for measurement in sampled:
        by_hotspot.setdefault(measurement.hotspot, []).append(measurement)

    diagnostics = []
    totals: dict[str, float] = {}
    for measurement in sampled:
        if measurement.value is not None:
            totals[measurement.counter] = (
                totals.get(measurement.counter, 0.0) + measurement.value
            )

    for hotspot, measurements in by_hotspot.items():
        by_counter: dict[str, list[Measurement]] = {}
        samples = 0
        for measurement in measurements:
            by_counter.setdefault(measurement.counter, []).append(measurement)
            samples += measurement.sample_count or 0
        if samples < floor_samples:
            continue

        time_base = _first_counter(by_counter, CLOCK_COUNTERS + ("cycles",))
        share = _share(by_counter, time_base, totals)
        flops = _first_counter(by_counter, FLOP_COUNTERS)
        bytes_ = _first_counter(by_counter, BYTE_COUNTERS)

        intensity = _intensity(by_counter, flops, bytes_)
        achieved = _achieved(by_counter, flops)
        intensity = _fused(intensity, by_counter, (flops, bytes_), witness)
        achieved = _fused(achieved, by_counter, (flops, time_base), witness)
        attainable, fraction = _placement(intensity, achieved, ceilings)
        imbalance = (
            _imbalance(measurements, time_base)
            if time_base is not None
            else _unavailable("imbalance", "ratio", "no time-base counter in this Run")
        )
        classification, why_not = _classify(
            intensity, fraction, imbalance, ceilings, latency_fraction, imbalance_ratio
        )
        diagnostics.append(
            Diagnostic(
                hotspot=hotspot,
                share=share,
                dram_intensity=intensity,
                achieved=achieved,
                attainable=attainable,
                envelope_fraction=fraction,
                imbalance=imbalance,
                classification=classification,
                classification_reason=why_not,
            )
        )

    diagnostics.sort(key=lambda d: -(d.share.value or 0.0))
    return diagnostics


def _share(by_counter: dict, time_base: str | None, totals: dict) -> Derived:
    """This Hotspot's fraction of everything the time base sampled."""
    if time_base is None:
        return _unavailable(
            "share", "fraction", "no time-base counter in this Run"
        )
    summed = _sum(by_counter[time_base])
    total = totals.get(time_base, 0.0)
    if summed is None or total <= 0:
        return _unavailable("share", "fraction", f"no {time_base} value")
    value, quality, reason = summed
    return Derived(
        name="share",
        value=value / total,
        unit="fraction",
        quality=quality,
        lineage=(time_base,),
        formula=f"{time_base} of the Hotspot / {time_base} of the Run",
        reason=reason,
    )


def _fused(
    quantity: Derived,
    by_counter: dict,
    counters: tuple[str | None, ...],
    witness: WitnessVerdict | None,
) -> Derived:
    """A Derived downgraded when it fuses Passes that disagree.

    Fusing values measured in different executions is only exact if the
    executions did the same work; when the witness says they did not,
    the quantity is estimated with the reason - silently exact would be
    the worst possible outcome for a user who paid for several runs.
    """
    if quantity.value is None or witness is None or witness.consistent:
        return quantity
    passes = {
        m.pass_index
        for counter in counters
        if counter is not None
        for m in by_counter.get(counter, ())
    }
    if len(passes) < 2:
        return quantity
    reason = (
        f"fused across passes that disagree: the witness "
        f"({witness.counter}) moved by {witness.spread:.0%} between "
        f"passes, beyond the {witness.threshold:.0%} threshold"
    )
    reasons = [r for r in (quantity.reason, reason) if r]
    return dataclasses.replace(
        quantity,
        quality=Quality.worst(quantity.quality, Quality.ESTIMATED),
        reason="; ".join(dict.fromkeys(reasons)),
    )


def _intensity(by_counter: dict, flops: str | None, bytes_: str | None) -> Derived:
    """DRAM arithmetic intensity: FLOPs per byte actually exchanged with
    main memory - sensitive to cache reuse, never interchangeable with
    the L1 intensity of the static loop analysis."""
    if flops is None or bytes_ is None:
        missing = FLOP_COUNTERS[0] if flops is None else BYTE_COUNTERS[0]
        return _unavailable(
            "dram_intensity",
            "flop/byte",
            f"no {missing} raw counter in this Run",
        )
    flop_sum, byte_sum = _sum(by_counter[flops]), _sum(by_counter[bytes_])
    if flop_sum is None or byte_sum is None or byte_sum[0] <= 0:
        return _unavailable(
            "dram_intensity", "flop/byte", "no usable flop or byte value"
        )
    quality = Quality.worst(flop_sum[1], byte_sum[1])
    reasons = [r for r in (flop_sum[2], byte_sum[2]) if r is not None]
    if flops == "flops":
        quality = Quality.worst(quality, Quality.ESTIMATED)
        reasons.append(PRECISION_REASON)
    return Derived(
        name="dram_intensity",
        value=flop_sum[0] / byte_sum[0],
        unit="flop/byte",
        quality=quality,
        lineage=(flops, bytes_),
        formula=f"{flops} / {bytes_}",
        reason="; ".join(dict.fromkeys(reasons)) if reasons else None,
    )


def _achieved(by_counter: dict, flops: str | None) -> Derived:
    """Achieved performance: total FLOPs over the Hotspot's wall time,
    the wall time being its most-loaded Locus's clock."""
    if flops is None:
        return _unavailable(
            "achieved", "flop/s", f"no {FLOP_COUNTERS[0]} raw counter in this Run"
        )
    clock = _first_counter(by_counter, CLOCK_COUNTERS)
    if clock is None:
        return _unavailable(
            "achieved",
            "flop/s",
            "no clock counter in this Run: flop/s needs a time base in seconds",
        )
    per_locus: dict = {}
    for measurement in by_counter[clock]:
        if measurement.value is not None:
            per_locus[measurement.locus] = (
                per_locus.get(measurement.locus, 0.0) + measurement.value
            )
    flop_sum = _sum(by_counter[flops])
    if flop_sum is None or not per_locus or max(per_locus.values()) <= 0:
        return _unavailable("achieved", "flop/s", "no usable flop or clock value")
    wall_seconds = max(per_locus.values()) / 1e9
    clock_quality = Quality.worst(
        *(m.quality for m in by_counter[clock] if m.value is not None)
    )
    quality = Quality.worst(flop_sum[1], clock_quality)
    reasons = [r for r in (flop_sum[2],) if r is not None]
    if flops == "flops":
        quality = Quality.worst(quality, Quality.ESTIMATED)
        reasons.append(PRECISION_REASON)
    return Derived(
        name="achieved",
        value=flop_sum[0] / wall_seconds,
        unit="flop/s",
        quality=quality,
        lineage=(flops, clock),
        formula=f"{flops} / max {clock} over Loci",
        reason="; ".join(dict.fromkeys(reasons)) if reasons else None,
    )


def _placement(
    intensity: Derived, achieved: Derived, ceilings: dict[str, Ceiling]
) -> tuple[Derived, Derived]:
    """The envelope at this intensity, and the fraction of it achieved."""
    if intensity.value is None:
        reason = intensity.reason
        return (
            _unavailable("attainable", "flop/s", reason),
            _unavailable("envelope_fraction", "fraction", reason),
        )
    bound = envelope(intensity.value, ceilings)
    if bound is None:
        reason = "the Machine carries no flops_dp or dram_bandwidth Ceiling"
        return (
            _unavailable("attainable", "flop/s", reason),
            _unavailable("envelope_fraction", "fraction", reason),
        )
    value, lineage, ceiling_quality, ceiling_reason = bound
    attainable_reason = intensity.reason or ceiling_reason
    attainable = Derived(
        name="attainable",
        value=value,
        unit="flop/s",
        quality=Quality.worst(intensity.quality, ceiling_quality),
        lineage=intensity.lineage + lineage,
        formula="min(flops_dp, dram_bandwidth x dram_intensity)",
        reason=attainable_reason
        if Quality.worst(intensity.quality, ceiling_quality) is Quality.ESTIMATED
        else None,
    )
    if achieved.value is None:
        return attainable, _unavailable(
            "envelope_fraction", "fraction", achieved.reason
        )
    fraction_quality = Quality.worst(achieved.quality, attainable.quality)
    return attainable, Derived(
        name="envelope_fraction",
        value=achieved.value / value,
        unit="fraction",
        quality=fraction_quality,
        lineage=achieved.lineage + attainable.lineage,
        formula="achieved / attainable",
        reason=(achieved.reason or attainable.reason)
        if fraction_quality is Quality.ESTIMATED
        else None,
    )
