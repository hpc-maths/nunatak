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
# few 1e9/s per core, demand-fill rates of a few 1e8/s, cycle rates of a
# few 1e9/s.
FLOP_PERIOD = 4_999_999
FILL_PERIOD = 100_003
CYCLE_PERIOD = 2_000_003
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
# Multi-pass runs split the set into semantic groups - one measurement
# concern per Pass, each pass small enough that no counter is ever
# multiplexed - so the split is by meaning, never by packing.
_ZEN2_GROUPS = (
    ("flops", (_flops("fp_ret_sse_avx_ops.all"),)),
    (
        "memory",
        (
            _dram_fills("ls_refills_from_sys.ls_mabresp_lcl_dram"),
            _dram_fills("ls_refills_from_sys.ls_mabresp_rmt_dram"),
        ),
    ),
)
_ZEN34_GROUPS = (
    ("flops", (_flops("fp_ret_sse_avx_ops.all"),)),
    (
        "memory",
        (
            _dram_fills("ls_dmnd_fills_from_sys.mem_io_local"),
            _dram_fills("ls_dmnd_fills_from_sys.mem_io_remote"),
        ),
    ),
)

_GROUPED = {
    "zen2": _ZEN2_GROUPS,
    "zen3": _ZEN34_GROUPS,
    "zen4": _ZEN34_GROUPS,
}
_SETS = {
    name: tuple(entry for _, events in groups for entry in events)
    for name, groups in _GROUPED.items()
}

# The witness: a stable global counter replicated in every Pass of a
# multi-pass run and compared at the end - the reproducibility check
# that makes cross-pass fusion honest. `instructions` is deliberately
# absent: on the Zen 2 corpus machine the generic event is bistable -
# 842e6 retired instructions read back as exactly 16x that (an IPC of
# 21) whenever the kernel programs it on a general counter next to
# cycles, and `ex_ret_instr` shows the same 16x - a witness that lies
# about reproducibility would poison every fusion verdict it guards.
_CYCLES = SampledEvent(
    event=f"cycles/period={CYCLE_PERIOD}/",
    canonical="cycles",
    unit="cycles",
    quality=Quality.MEASURED,
)
_WITNESS = {
    "zen2": (_CYCLES,),
    "zen3": (_CYCLES,),
    "zen4": (_CYCLES,),
}

# Reverse map: base event name (no period term, no modifiers) to its
# SampledEvent, for the ingestion side.
_BY_EVENT = {
    entry.event.split("/")[0]: entry
    for group in [*_SETS.values(), *_WITNESS.values()]
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


def groups_for(name: str) -> tuple[tuple[str, tuple[SampledEvent, ...]], ...]:
    """The semantic groups of one microarchitecture, by table name."""
    return _GROUPED.get(name, ())


def witness_for(name: str) -> tuple[SampledEvent, ...]:
    """The witness of one microarchitecture, by table name."""
    return _WITNESS.get(name, ())


def pass_groups(
    machine: Machine, cpuinfo=None
) -> tuple[tuple[str, tuple[SampledEvent, ...]], ...]:
    """The semantic event groups of a multi-pass run, `(label, events)`
    per Pass, empty when the microarchitecture has none.

    One measurement concern per Pass: each group is small enough that no
    counter is ever multiplexed, which is the exactness a user paying
    for several executions asked for.
    """
    microarchitecture = (
        theory.detect(machine) if cpuinfo is None else theory.detect(machine, cpuinfo)
    )
    if microarchitecture is None:
        return ()
    return groups_for(microarchitecture.name)


def witness(machine: Machine, cpuinfo=None) -> tuple[SampledEvent, ...]:
    """The witness counters replicated in every Pass of a multi-pass
    run, empty when the microarchitecture has none validated.

    The time base is always a witness on top of these: it rides every
    Pass by construction.
    """
    microarchitecture = (
        theory.detect(machine) if cpuinfo is None else theory.detect(machine, cpuinfo)
    )
    if microarchitecture is None:
        return ()
    return witness_for(microarchitecture.name)


def canonical(counter: str) -> SampledEvent | None:
    """The pivot-side meaning of a sampled event name as `perf script`
    prints it (`ls_refills_from_sys.ls_mabresp_lcl_dram/period=100003/u`),
    None for anything that is not a mapped vendor event."""
    return _BY_EVENT.get(counter.split("/")[0])
