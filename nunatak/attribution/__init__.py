"""Attribution: from module-relative addresses to named Hotspots.

Where the measured pivot records that time was spent at `(module, offset)`,
attribution says what that address is: the physical function, its source
position, and the frames inlined into it - kept as internal detail of the
Hotspot, never as units of analysis. It works on the distinct addresses
left by the aggregation, never on the sample stream.

When attribution fails, the Measurement stays exact - that time really was
spent at that address - and it is the identity that degrades, not the
value: an unresolved Hotspot keeps its `module+0x...` display and its
measured numbers.
"""

from __future__ import annotations

import dataclasses

from nunatak.attribution import inspection
from nunatak.attribution.addr2line import Addr2Line
from nunatak.attribution.symbolizer import (
    AttributionChain,
    Frame,
    ModuleSymbolization,
    Symbolizer,
    locate,
)
from nunatak.collect.execution import Executor
from nunatak.pivot import (
    AddressDetail,
    Degradation,
    Hotspot,
    InlineFrame,
    LogicalIdentity,
    Measurement,
    PhysicalIdentity,
    ResolutionLevel,
    Stack,
    StackFrame,
    hotspot_level,
    locus_level,
)

__all__ = [
    "Addr2Line",
    "AttributionChain",
    "Frame",
    "ModuleSymbolization",
    "Symbolizer",
    "attribute",
    "locate",
    "locate_any",
]


def locate_any(executor: Executor, config) -> Symbolizer | Addr2Line | None:
    """The symbolizer this machine offers: the LLVM driver when one
    answers, else GNU addr2line - same contract, declared second-choice
    by doctor. The fallback is only probed when LLVM is absent, so a
    machine with LLVM never spends the extra invocation."""
    from nunatak.attribution import addr2line

    return locate(executor, config) or addr2line.locate(executor, config)


def _symbolizable(module: str) -> bool:
    """Whether `module` is an on-disk object a symbolizer can open.

    Pseudo entries - `[vdso]`, `[kernel.kallsyms]`, `/proc/kcore` - name
    kernel or synthetic mappings with no object file behind them: their
    Hotspots stay unresolved by design, displayed `module+0x...`.
    """
    return module.startswith("/") and not module.startswith("/proc/")


def _named(
    hotspot: Hotspot, chain: AttributionChain, level: ResolutionLevel
) -> Hotspot:
    """The same Hotspot carrying the identity the chain established.

    The physical identity moves from the sampled address to the symbol's
    start address, so every sampled address of one function shares one
    identity; without a start address there is no canonical anchor, and
    claiming one per sampled address would split the function into as many
    Hotspots, so none is kept. The sampled offset itself goes away: it
    only ever disambiguated unresolved Hotspots.
    """
    physical = hotspot.physical_identity
    if physical is not None:
        start = chain.physical.start_address
        physical = (
            PhysicalIdentity(module_id=physical.module_id, offset=start)
            if start is not None
            else None
        )
    return Hotspot(
        logical_identity=LogicalIdentity(
            module=hotspot.logical_identity.module,
            name=chain.physical.function,
            source_file=chain.physical.file,
        ),
        resolution_level=level,
        physical_identity=physical,
    )


def _merged(measurements: list[Measurement]) -> list[Measurement]:
    """Aggregate Measurements that naming fused onto one Hotspot.

    Ingestion aggregates by sampled address, so several addresses of one
    physical function arrive as several Measurements: their values and
    sample counts add up. Everything reaching this point is a measured raw
    counter straight from ingestion, which is what makes plain addition
    sufficient.
    """
    groups: dict[tuple, list[Measurement]] = {}
    for measurement in measurements:
        key = (measurement.hotspot, measurement.locus, measurement.counter,
               measurement.pass_index)
        groups.setdefault(key, []).append(measurement)

    merged = []
    for parts in groups.values():
        if len(parts) == 1:
            merged.append(parts[0])
            continue
        counts = [p.sample_count for p in parts if p.sample_count is not None]
        merged.append(
            dataclasses.replace(
                parts[0],
                value=sum(p.value for p in parts),
                sample_count=sum(counts) if counts else None,
            )
        )
    merged.sort(
        key=lambda m: (
            -m.value,
            m.hotspot.logical_identity.module,
            m.hotspot.display_name,
        )
    )
    return merged


def _inline_frames(chain: AttributionChain) -> tuple[InlineFrame, ...]:
    """The persisted form of a chain: names and source positions only, the
    symbol start already lives in the physical identity."""
    return tuple(
        InlineFrame(
            function=frame.function,
            file=frame.file,
            line=frame.line,
            declaration_line=frame.declaration_line,
        )
        for frame in chain.frames
    )


def attribute(
    measurements: list[Measurement],
    symbolizer: Symbolizer | None,
    executor: Executor,
    environment: dict[str, str] | None = None,
    stacks: list[Stack] | None = None,
) -> tuple[list[Measurement], list[AddressDetail], list[Stack], list[Degradation]]:
    """Name the unresolved Hotspots of `measurements` and the frames of
    `stacks`.

    Returns the new Measurements, the internal detail of the named
    Hotspots - the inlining chain and the weight of each sampled address,
    what a report needs to ventilate a Hotspot by line on a machine where
    the binary no longer exists - the stacks with their frames named, and
    the degradations met on the way.

    Symbolization runs once per module, on the union of its distinct
    sampled offsets and its distinct stack-frame addresses: naming a
    caller costs no extra invocation. A caller is named after the
    physical function covering its address - the extent rule applies to
    callers exactly as to leaves, so a return address in a gap stays
    `module+0x...` rather than borrowing its neighbour's name. Modules
    that only yield bare names are then inspected once to tell
    `function` (a `.symtab` name) from `symbol` (a `.dynsym`-only
    module). `symbolizer` is the located LLVM driver or the addr2line
    fallback - same contract, so nothing here knows which one answered.
    Without any symbolizer everything comes back untouched: doctor has
    already announced the missing capability. A module the symbolizer
    cannot read leaves its Hotspots unresolved and is declared, once, in
    a degradation.
    """
    stacks = stacks or []
    if symbolizer is None or not measurements:
        return measurements, [], stacks, []

    # The counting layer's Locus-level aggregates carry no Hotspot: there
    # is nothing to name, they ride through unchanged.
    aggregates = locus_level(measurements)
    sampled = hotspot_level(measurements)

    offsets: dict[str, set[int]] = {}
    for measurement in sampled:
        hotspot = measurement.hotspot
        module = hotspot.logical_identity.module
        if (
            hotspot.resolution_level is ResolutionLevel.UNRESOLVED
            and hotspot.offset is not None
            and _symbolizable(module)
        ):
            offsets.setdefault(module, set()).add(hotspot.offset)
    for stack in stacks:
        for frame in stack.frames:
            if frame.offset is not None and _symbolizable(frame.module):
                offsets.setdefault(frame.module, set()).add(frame.offset)

    chains: dict[tuple[str, int], AttributionChain] = {}
    errors: list[tuple[str, str]] = []
    for module in sorted(offsets):
        outcome = symbolizer.symbolize(
            executor, module, sorted(offsets[module]), env=environment
        )
        if outcome.error is not None:
            errors.append((module, outcome.error))
        for offset, chain in outcome.chains.items():
            if chain.frames:
                chains[(module, offset)] = chain

    # A bare name may come from .symtab (level `function`) or from a
    # .dynsym-only module (level `symbol`): only the section inventory can
    # tell, so it is taken once per module that needs the distinction.
    needing_inspection = {
        module
        for (module, _), chain in chains.items()
        if chain.resolution_level is ResolutionLevel.FUNCTION
    }
    symbol_only = set()
    readelf = symbolizer.readelf
    for module in sorted(needing_inspection):
        sections = inspection.inspect(executor, readelf, module)
        if sections is not None and sections.dynsym and not sections.symtab:
            symbol_only.add(module)

    renamed = []
    frames_by_address: dict[tuple[str, int], tuple[InlineFrame, ...]] = {}
    weights: dict[tuple, list] = {}
    for measurement in sampled:
        hotspot = measurement.hotspot
        module = hotspot.logical_identity.module
        chain = (
            chains.get((module, hotspot.offset))
            if hotspot.resolution_level is ResolutionLevel.UNRESOLVED
            else None
        )
        if chain is None:
            renamed.append(measurement)
            continue
        level = chain.resolution_level
        if level is ResolutionLevel.FUNCTION and module in symbol_only:
            level = ResolutionLevel.SYMBOL
        named = _named(hotspot, chain, level)
        renamed.append(dataclasses.replace(measurement, hotspot=named))

        # The detail aggregates over Loci: the per-line view says where
        # time goes inside a function, imbalance stays at the Measurement
        # grain.
        address = (module, hotspot.offset)
        if address not in frames_by_address:
            frames_by_address[address] = _inline_frames(chain)
        key = (named, hotspot.offset, measurement.counter, measurement.pass_index)
        entry = weights.setdefault(key, [0.0, 0, False, frames_by_address[address]])
        entry[0] += measurement.value
        if measurement.sample_count is not None:
            entry[1] += measurement.sample_count
            entry[2] = True

    details = [
        AddressDetail(
            hotspot=named,
            offset=offset,
            counter=counter,
            value=value,
            sample_count=count if counted else None,
            frames=frames,
            pass_index=pass_index,
        )
        for (named, offset, counter, pass_index), (value, count, counted, frames)
        in weights.items()
    ]
    details.sort(
        key=lambda d: (
            d.hotspot.logical_identity.module,
            d.hotspot.display_name,
            d.counter,
            d.pass_index,
            d.offset,
        )
    )

    named_stacks = [
        dataclasses.replace(
            stack,
            frames=tuple(
                dataclasses.replace(
                    frame,
                    function=(
                        chain.physical.function
                        if frame.offset is not None
                        and (chain := chains.get((frame.module, frame.offset)))
                        else None
                    ),
                )
                for frame in stack.frames
            ),
        )
        for stack in stacks
    ]

    degradations = []
    if errors:
        module, error = errors[0]
        degradations.append(
            Degradation(
                name="symbolization-failed",
                message=f"{len(errors)} module(s) could not be symbolized "
                f"(first: {module}: {error})",
                remedy="the Hotspots of these modules stay unresolved; their "
                "files must be readable at analysis time",
            )
        )
    return _merged(renamed) + aggregates, details, named_stacks, degradations
