"""Counter groups per microarchitecture: what sampling attributes to
Hotspots beyond time.

Every auxiliary event carries a fixed period rather than a frequency:
each sample is then worth exactly its period, so the sum of periods
counts the events - validated at 99.9% of `perf stat` on the corpus
machine - and the interrupt rate stays bounded by construction, which
is the only overhead lever sampling has. The time base is `task-clock`,
a software event that consumes no hardware counter and gives every
Hotspot its seconds.

Hardware-prefetch fill events are deliberately absent: sampling them
inflates what they measure - the interrupt handler's own memory traffic
triggers prefetches, an observer effect measured at 20x on Zen 2 - and
doubles the run time. DRAM traffic is therefore demand fills only, and
every Measurement built from it says so.

An unknown microarchitecture gets no counter group: the run samples
time alone, exactly as before, and the roofline placement stays
`unavailable` with its reason.
"""

from __future__ import annotations

from dataclasses import dataclass

from nunatak.calibration import theory
from nunatak.pivot import Machine, Quality

# ~1 kHz of interrupts per core at realistic HPC rates: FLOP rates of a
# few 1e9/s per core, demand-fill rates of a few 1e8/s.
FLOP_PERIOD = 4_999_999
FILL_PERIOD = 100_003
CACHELINE_BYTES = 64

DRAM_REASON = (
    "demand fills only: hardware-prefetched traffic is not counted"
)
PRECISION_REASON = (
    "FLOPs not split by precision on this microarchitecture; "
    "compared against the double-precision peak"
)


@dataclass(frozen=True)
class SampledEvent:
    """One vendor event sampled alongside time, and what it becomes in
    the pivot: a canonical counter name, a unit, a scale, and the Quality
    its Measurements deserve - `estimated` when the event is an honest
    proxy rather than the quantity itself."""

    event: str
    canonical: str
    unit: str
    scale: float = 1.0
    quality: Quality = Quality.MEASURED
    reason: str | None = None

    @property
    def selector(self) -> str:
        """The `perf record -e` argument, fixed period included."""
        return self.event


def _flops(event: str) -> SampledEvent:
    """An all-precision FLOP count: Zen does not split by precision."""
    return SampledEvent(
        event=f"{event}/period={FLOP_PERIOD}/",
        canonical="flops",
        unit="flop",
        quality=Quality.MEASURED,
    )


def _dram_fills(event: str) -> SampledEvent:
    """Demand cacheline fills from DRAM, scaled to bytes - a proxy that
    undercounts prefetched traffic, hence estimated with the reason."""
    return SampledEvent(
        event=f"{event}/period={FILL_PERIOD}/",
        canonical="dram_bytes",
        unit="byte",
        scale=CACHELINE_BYTES,
        quality=Quality.ESTIMATED,
        reason=DRAM_REASON,
    )


# Event names follow the kernel's per-microarchitecture tables; the Zen 2
# set is validated on real PMUs (the corpus machine), the Zen 3/4 names
# are the kernel's for those parts and degrade cleanly if a kernel does
# not know them.
_ZEN2 = (
    _flops("fp_ret_sse_avx_ops.all"),
    _dram_fills("ls_refills_from_sys.ls_mabresp_lcl_dram"),
    _dram_fills("ls_refills_from_sys.ls_mabresp_rmt_dram"),
)
_ZEN34 = (
    _flops("fp_ret_sse_avx_ops.all"),
    _dram_fills("ls_dmnd_fills_from_sys.mem_io_local"),
    _dram_fills("ls_dmnd_fills_from_sys.mem_io_remote"),
)

_SETS = {
    "zen2": _ZEN2,
    "zen3": _ZEN34,
    "zen4": _ZEN34,
}

# Reverse map: base event name (no period term, no modifiers) to its
# SampledEvent, for the ingestion side.
_BY_EVENT = {
    entry.event.split("/")[0]: entry
    for group in _SETS.values()
    for entry in group
}


def sampling_events(machine: Machine, cpuinfo=None) -> tuple[SampledEvent, ...]:
    """The counter group for this Machine, empty when its
    microarchitecture has none - time-only sampling, never a guess."""
    microarchitecture = (
        theory.detect(machine) if cpuinfo is None else theory.detect(machine, cpuinfo)
    )
    if microarchitecture is None:
        return ()
    return _SETS.get(microarchitecture.name, ())


def canonical(counter: str) -> SampledEvent | None:
    """The pivot-side meaning of a sampled event name as `perf script`
    prints it (`ls_refills_from_sys.ls_mabresp_lcl_dram/period=100003/u`),
    None for anything that is not a mapped vendor event."""
    return _BY_EVENT.get(counter.split("/")[0])
