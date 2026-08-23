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

The single execution's set is bounded by the general counters one
thread actually gets - four on Skylake-generation cores with SMT, eight
from Ice Lake on, and always enough on Zen - because a fixed-period
event that the kernel rotates off its counter undercounts silently,
which is worse than not counting. When the budget cannot hold a whole
semantic group, the group is absent from the single execution and
arrives with `--multi-pass`: absence with a remedy, never a truncated
group wearing `measured`.
"""

from __future__ import annotations

from dataclasses import dataclass

from nunatak.calibration import theory
from nunatak.pivot import Machine, Quality

# ~1 kHz of interrupts per core at realistic HPC rates: FLOP rates of a
# few 1e9/s per core, demand-fill rates of a few 1e8/s, instruction
# rates of a few 1e9/s. Periods are prime, so no harmonic of a loop can
# hide from the sampler.
FLOP_PERIOD = 4_999_999
FILL_PERIOD = 100_003
INSTRUCTION_PERIOD = 9_999_991
CACHELINE_BYTES = 64

DRAM_REASON = (
    "demand fills only: hardware-prefetched traffic is not counted"
)
L3_MISS_REASON = (
    "retired loads missing L3, one cacheline each: stores, prefetched "
    "and speculative traffic are not counted"
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


def _flops_split(event: str, precision: str, lanes: int) -> SampledEvent:
    """One Intel per-width retired-FLOP event, folded onto the split
    canonical counter (`flops_dp` or `flops_sp`) the analysis prefers to
    the all-precision one.

    The scale is the lane count alone: the hardware already counts an
    FM(N)ADD/SUB twice per element, so lanes x count is FLOPs with no
    FMA factor of ours. AVX-512 masked lanes count at full width - one
    of the documented reasons a count can exceed the algorithm's truth.
    """
    return SampledEvent(
        event=f"{event}/period={FLOP_PERIOD}/",
        canonical=f"flops_{precision}",
        unit="flop",
        scale=lanes,
        quality=Quality.MEASURED,
    )


def _l3_miss_loads(event: str) -> SampledEvent:
    """Retired loads that missed L3, scaled to bytes: the per-core DRAM
    proxy Intel offers without uncore counters - which count per socket
    and cannot be attributed to a Hotspot - hence estimated, with what
    it does not see in the reason."""
    return SampledEvent(
        event=f"{event}/period={FILL_PERIOD}/",
        canonical="dram_bytes",
        unit="byte",
        scale=CACHELINE_BYTES,
        quality=Quality.ESTIMATED,
        reason=L3_MISS_REASON,
    )


def _instructions() -> SampledEvent:
    """Retired instructions as a witness: on Intel and ARM they ride a
    dedicated counter, costing none of the general counters the groups
    are budgeted against."""
    return SampledEvent(
        event=f"instructions/period={INSTRUCTION_PERIOD}/",
        canonical="instructions",
        unit="instruction",
        quality=Quality.MEASURED,
    )


def _intel_flops(precision: str, widths: tuple[int, ...]) -> tuple[SampledEvent, ...]:
    """The complete per-width quartet (or trio) of one precision, in
    Intel's `fp_arith_inst_retired` naming."""
    suffix = "double" if precision == "dp" else "single"
    element = 8 if precision == "dp" else 4
    events = [_flops_split(f"fp_arith_inst_retired.scalar_{suffix}", precision, 1)]
    events += [
        _flops_split(
            f"fp_arith_inst_retired.{width}b_packed_{suffix}",
            precision,
            width // 8 // element,
        )
        for width in widths
    ]
    return tuple(events)


@dataclass(frozen=True)
class EventTable:
    """The counter architecture of one microarchitecture.

    `groups` are the semantic splits of a multi-pass run - one
    measurement concern per Pass, each small enough that no counter is
    ever multiplexed, so the split is by meaning, never by packing.
    `single` names the groups that together fit the single execution's
    general-counter budget. `witness` is the work-proportional counter
    replicated in every Pass of a multi-pass run.
    """

    groups: tuple[tuple[str, tuple[SampledEvent, ...]], ...]
    single: tuple[str, ...]
    witness: tuple[SampledEvent, ...]

    @property
    def sampling_set(self) -> tuple[SampledEvent, ...]:
        """The single execution's events: whole named groups, nothing
        partial - a truncated group would undercount under `measured`."""
        by_label = dict(self.groups)
        return tuple(
            entry for label in self.single for entry in by_label[label]
        )


def _zen(fills: tuple[SampledEvent, ...]) -> EventTable:
    """A Zen table: one all-precision FLOP event, demand DRAM fills, and
    the FLOP event doubling as witness.

    The witness is the retired-FLOP event because the two intuitive
    candidates are out for measured reasons, never feared ones.
    `instructions` is bistable on the Zen 2 corpus machine: 842e6
    retired instructions read back as exactly 16x that (an IPC of 21)
    whenever the kernel programs it on a general counter next to
    cycles. `cycles` counts time-at-frequency, not work: back to back
    on the memory-bound triad, the same run costs 4.8e9 then 6.9e9
    cycles - stall cycles scale with the governor's ramp while DRAM
    latency does not - where the FLOP count comes back identical to the
    unit. A witness that lies about reproducibility would poison every
    fusion verdict it guards; an application without floating point
    gets a vacuous witness, which is the honest amount of evidence
    available.
    """
    flops = _flops("fp_ret_sse_avx_ops.all")
    return EventTable(
        groups=(("flops", (flops,)), ("memory", fills)),
        single=("flops", "memory"),
        witness=(flops,),
    )


def _intel(widths: tuple[int, ...], memory: str, single: tuple[str, ...]) -> EventTable:
    """An Intel table: per-width retired-FLOP events folded onto split
    precisions, the L3-miss DRAM proxy, and retired instructions as
    witness - they ride the dedicated fixed counter, so replicating them
    in every Pass costs none of the general counters the groups need.
    Zen's bistability argument does not transfer: it was measured on
    Zen's general counters, and Intel's fixed counter never competes for
    one. The single-precision group exists for `--multi-pass` only: no
    single-execution budget holds both precisions and the memory proxy.
    """
    return EventTable(
        groups=(
            ("flops_dp", _intel_flops("dp", widths)),
            ("flops_sp", _intel_flops("sp", widths)),
            ("memory", (_l3_miss_loads(memory),)),
        ),
        single=single,
        witness=(_instructions(),),
    )


# Event names follow the kernel's per-microarchitecture tables. The
# Zen 2 set is validated on real PMUs (the corpus machine); the Zen 3/4
# and Intel names are the kernel's for those parts, unvalidated on real
# PMUs yet, and degrade cleanly if a kernel does not know them.
#
# Intel absences are choices, not oversights. Haswell/Broadwell retired
# their FLOP counters (they returned with Skylake): memory traffic is
# what those cores can attribute. Hybrid client parts (Alder/Raptor
# Lake) get no table at all: their E-cores expose no FLOP event, so a
# set that counts on half the cores would undercount silently under
# `measured` - time-only sampling is the honest default there.
#
# Skylake-generation cores give one SMT thread 4 general counters, so
# their single execution cannot hold FLOPs and the memory proxy at
# once: the server table keeps the complete double-precision group and
# leaves memory to --multi-pass; the client table, without 512-bit
# events, fits both.
_ZEN34_FILLS = (
    _dram_fills("ls_dmnd_fills_from_sys.mem_io_local"),
    _dram_fills("ls_dmnd_fills_from_sys.mem_io_remote"),
)
_TABLE = {
    "zen2": _zen(
        (
            _dram_fills("ls_refills_from_sys.ls_mabresp_lcl_dram"),
            _dram_fills("ls_refills_from_sys.ls_mabresp_rmt_dram"),
        )
    ),
    "zen3": _zen(_ZEN34_FILLS),
    "zen4": _zen(_ZEN34_FILLS),
    "skylake": _intel(
        (128, 256), "mem_load_retired.l3_miss", ("flops_dp", "memory")
    ),
    "skylake-sp": _intel(
        (128, 256, 512), "mem_load_retired.l3_miss", ("flops_dp",)
    ),
    "icelake-sp": _intel(
        (128, 256, 512), "mem_load_retired.l3_miss", ("flops_dp", "memory")
    ),
    "sapphire-rapids": _intel(
        (128, 256, 512), "mem_load_retired.l3_miss", ("flops_dp", "memory")
    ),
    "emerald-rapids": _intel(
        (128, 256, 512), "mem_load_retired.l3_miss", ("flops_dp", "memory")
    ),
    "granite-rapids": _intel(
        (128, 256, 512), "mem_load_retired.l3_miss", ("flops_dp", "memory")
    ),
    "haswell/broadwell": EventTable(
        groups=(("memory", (_l3_miss_loads("mem_load_uops_retired.l3_miss"),)),),
        single=("memory",),
        witness=(_instructions(),),
    ),
}
# Reverse map: base event name (no period term, no modifiers) to its
# SampledEvent, for the ingestion side.
_BY_EVENT = {
    entry.event.split("/")[0]: entry
    for table in _TABLE.values()
    for group in [*(events for _, events in table.groups), table.witness]
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
    table = _TABLE.get(microarchitecture.name)
    return table.sampling_set if table is not None else ()


def groups_for(name: str) -> tuple[tuple[str, tuple[SampledEvent, ...]], ...]:
    """The semantic groups of one microarchitecture, by table name."""
    table = _TABLE.get(name)
    return table.groups if table is not None else ()


def witness_for(name: str) -> tuple[SampledEvent, ...]:
    """The witness of one microarchitecture, by table name."""
    table = _TABLE.get(name)
    return table.witness if table is not None else ()


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
