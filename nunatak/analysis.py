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

from dataclasses import dataclass

from nunatak.pivot import Ceiling, Hotspot, Measurement, Quality, Run

# A Hotspot below the statistical floor is noise wearing the look of a
# diagnosis: its Measurements stay in the pivot, the Diagnostic skips it.
STATISTICAL_FLOOR_SAMPLES = 30
# Below this fraction of the envelope, neither bound explains the
# performance: the regime is latency.
LATENCY_FRACTION = 0.5
# Above this most-loaded/least-loaded ratio, the imbalance is the story.
IMBALANCE_RATIO = 2.0

# Canonical counter names the engine consumes; the collection side owns
# the mapping from vendor events to these.
FLOP_COUNTERS = ("flops_dp",)
BYTE_COUNTERS = ("dram_bytes",)
CLOCK_COUNTERS = ("task-clock", "cpu-clock")


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
) -> tuple[float, tuple[str, ...], Quality] | None:
    """The roofline: `min(compute peak, bandwidth x intensity)`.

    The memory diagonal stops at the break point, it never crosses it -
    that formula is a testable invariant. Returns (value, lineage,
    quality), or None when either Ceiling is missing.
    """
    peak = ceilings.get("flops_dp")
    bandwidth = ceilings.get("dram_bandwidth")
    if peak is None or bandwidth is None:
        return None
    return (
        min(peak.value, bandwidth.value * intensity),
        ("flops_dp", "dram_bandwidth"),
        Quality.worst(peak.quality, bandwidth.quality),
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


def _sum(measurements: list[Measurement]) -> tuple[float, Quality] | None:
    """Total value over Loci and Passes, with the worst input Quality."""
    values = [m for m in measurements if m.value is not None]
    if not values:
        return None
    return (
        sum(m.value for m in values),
        Quality.worst(*(m.quality for m in values)),
    )


def _first_counter(by_counter: dict, names: tuple[str, ...]) -> str | None:
    """The first of `names` this Run actually measured."""
    for name in names:
        if name in by_counter:
            return name
    return None


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

    by_hotspot: dict[Hotspot, list[Measurement]] = {}
    for measurement in run.measurements:
        by_hotspot.setdefault(measurement.hotspot, []).append(measurement)

    diagnostics = []
    totals: dict[str, float] = {}
    for measurement in run.measurements:
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
    value, quality = summed
    return Derived(
        name="share",
        value=value / total,
        unit="fraction",
        quality=quality,
        lineage=(time_base,),
        formula=f"{time_base} of the Hotspot / {time_base} of the Run",
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
    return Derived(
        name="dram_intensity",
        value=flop_sum[0] / byte_sum[0],
        unit="flop/byte",
        quality=Quality.worst(flop_sum[1], byte_sum[1]),
        lineage=(flops, bytes_),
        formula=f"{flops} / {bytes_}",
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
    return Derived(
        name="achieved",
        value=flop_sum[0] / wall_seconds,
        unit="flop/s",
        quality=Quality.worst(flop_sum[1], clock_quality),
        lineage=(flops, clock),
        formula=f"{flops} / max {clock} over Loci",
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
    value, lineage, ceiling_quality = bound
    attainable = Derived(
        name="attainable",
        value=value,
        unit="flop/s",
        quality=Quality.worst(intensity.quality, ceiling_quality),
        lineage=intensity.lineage + lineage,
        formula="min(flops_dp, dram_bandwidth x dram_intensity)",
    )
    if achieved.value is None:
        return attainable, _unavailable(
            "envelope_fraction", "fraction", achieved.reason
        )
    return attainable, Derived(
        name="envelope_fraction",
        value=achieved.value / value,
        unit="fraction",
        quality=Quality.worst(achieved.quality, attainable.quality),
        lineage=achieved.lineage + attainable.lineage,
        formula="achieved / attainable",
    )
