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

from nunatak.attribution.symbolizer import (
    AttributionChain,
    Frame,
    ModuleSymbolization,
    Symbolizer,
    locate,
)
from nunatak.collect.execution import Executor
from nunatak.pivot import (
    Degradation,
    Hotspot,
    LogicalIdentity,
    Measurement,
    PhysicalIdentity,
    ResolutionLevel,
)

__all__ = [
    "AttributionChain",
    "Frame",
    "ModuleSymbolization",
    "Symbolizer",
    "attribute",
    "locate",
]


def _symbolizable(module: str) -> bool:
    """Whether `module` is an on-disk object a symbolizer can open.

    Pseudo entries - `[vdso]`, `[kernel.kallsyms]`, `/proc/kcore` - name
    kernel or synthetic mappings with no object file behind them: their
    Hotspots stay unresolved by design, displayed `module+0x...`.
    """
    return module.startswith("/") and not module.startswith("/proc/")


def _named(hotspot: Hotspot, chain: AttributionChain) -> Hotspot:
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
        resolution_level=chain.resolution_level,
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


def attribute(
    measurements: list[Measurement],
    symbolizer: Symbolizer | None,
    executor: Executor,
) -> tuple[list[Measurement], list[Degradation]]:
    """Name the unresolved Hotspots of `measurements`.

    Returns the new Measurements and the degradations met on the way.
    Symbolization runs once per module, on its distinct sampled offsets.
    Without a symbolizer the Measurements come back untouched: doctor has
    already announced the missing capability. A module the symbolizer
    cannot read leaves its Hotspots unresolved and is declared, once, in a
    degradation.
    """
    if symbolizer is None or not measurements:
        return measurements, []

    offsets: dict[str, set[int]] = {}
    for measurement in measurements:
        hotspot = measurement.hotspot
        module = hotspot.logical_identity.module
        if (
            hotspot.resolution_level is ResolutionLevel.UNRESOLVED
            and hotspot.offset is not None
            and _symbolizable(module)
        ):
            offsets.setdefault(module, set()).add(hotspot.offset)

    chains: dict[tuple[str, int], AttributionChain] = {}
    errors: list[tuple[str, str]] = []
    for module in sorted(offsets):
        outcome = symbolizer.symbolize(executor, module, sorted(offsets[module]))
        if outcome.error is not None:
            errors.append((module, outcome.error))
        for offset, chain in outcome.chains.items():
            if chain.frames:
                chains[(module, offset)] = chain

    renamed = []
    for measurement in measurements:
        hotspot = measurement.hotspot
        chain = (
            chains.get((hotspot.logical_identity.module, hotspot.offset))
            if hotspot.resolution_level is ResolutionLevel.UNRESOLVED
            else None
        )
        renamed.append(
            measurement
            if chain is None
            else dataclasses.replace(measurement, hotspot=_named(hotspot, chain))
        )

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
    return _merged(renamed), degradations
