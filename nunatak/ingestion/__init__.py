"""Ingestion: versioned parsers turning collector outputs into Measurements.

One parser per (tool, detected version) couple. This is where the
normalization into module offsets happens: no absolute address crosses
this boundary, so ASLR and library load order cannot split a Hotspot. A tool version the ingestion does not
recognize is declared as a degradation rather than parsed blindly - the
raw outputs stay in the Run for a later nunatak to ingest.
"""

from __future__ import annotations

from pathlib import Path

from nunatak.collect import events as counter_events
from nunatak.collect import perf as perf_adapter
from nunatak.ingestion import perf_script
from nunatak.ingestion.samples import Sample
from nunatak.pivot import (
    Degradation,
    Hotspot,
    LogicalIdentity,
    Locus,
    Measurement,
    PhysicalIdentity,
    Quality,
    ResolutionLevel,
    Stack,
    StackFrame,
)

__all__ = ["Sample", "ingest", "measurements_from_samples", "stacks_from_samples"]

# Sampling clocks report periods in nanoseconds; any other raw counter
# counts its own unit (cycles, instructions...). `wall-clock` is the
# temporal mode's clock: sample looks at every thread on an interval,
# blocked or running, so its periods are wall time, not cpu time.
_CLOCK_UNITS = {"cpu-clock": "ns", "task-clock": "ns", "wall-clock": "ns"}


def measurements_from_samples(
    samples: list[Sample],
    module_ids: dict[str, str],
    node: str,
    rank: int | None = None,
    pass_index: int = 0,
) -> list[Measurement]:
    """Aggregate samples into per-(Hotspot, Locus) Measurements.

    Hotspots are unresolved at this stage - `(module, offset)`, displayed
    `module+0x...` - and the attribution chain later gives them names.
    `module_ids` maps module paths to their build-id; a module without one
    gets no physical identity. Output is deterministic: sorted by
    decreasing value.
    """
    # Vendor events fold onto their canonical counter before aggregation,
    # so the local and remote DRAM fills of one address merge into a
    # single dram_bytes Measurement.
    groups: dict[tuple, list[int]] = {}
    vendor_by_counter: dict[str, object] = {}
    for sample in samples:
        vendor = counter_events.canonical(sample.counter)
        counter = vendor.canonical if vendor is not None else sample.counter
        vendor_by_counter[counter] = vendor
        key = (sample.module, sample.offset, sample.tid, counter)
        entry = groups.setdefault(key, [0, 0])
        entry[0] += sample.period
        entry[1] += 1

    measurements = []
    for (module, offset, tid, counter), (value, count) in groups.items():
        module_id = module_ids.get(module)
        physical = (
            PhysicalIdentity(module_id=module_id, offset=offset)
            if module_id is not None and offset is not None
            else None
        )
        vendor = vendor_by_counter.get(counter)
        measurements.append(
            Measurement(
                hotspot=Hotspot(
                    logical_identity=LogicalIdentity(module=module),
                    resolution_level=ResolutionLevel.UNRESOLVED,
                    physical_identity=physical,
                    offset=offset,
                ),
                locus=Locus(node=node, rank=rank, thread=tid),
                counter=counter,
                value=float(value) * (vendor.scale if vendor is not None else 1.0),
                unit=vendor.unit
                if vendor is not None
                else _CLOCK_UNITS.get(counter, counter),
                quality=vendor.quality if vendor is not None else Quality.MEASURED,
                reason=vendor.reason if vendor is not None else None,
                sample_count=count,
                pass_index=pass_index,
            )
        )
    measurements.sort(
        key=lambda m: (-m.value, m.hotspot.logical_identity.module, m.hotspot.offset or 0)
    )
    return measurements


def stacks_from_samples(
    samples: list[Sample],
    node: str,
    rank: int | None = None,
    pass_index: int = 0,
) -> list[Stack]:
    """Aggregate recorded call paths into per-(Locus, counter, path) Stacks.

    A sample without callers carries no path: a flat recording yields
    nothing, never a one-frame stack that would restate its Measurement.
    Counters fold onto their canonical name and unit exactly like the
    Measurements they accompany, so a path's weight stays comparable to
    the Hotspot's own value. Output is deterministic: sorted by
    decreasing value.
    """
    groups: dict[tuple, list] = {}
    for sample in samples:
        if not sample.callers:
            continue
        vendor = counter_events.canonical(sample.counter)
        counter = vendor.canonical if vendor is not None else sample.counter
        frames = (
            StackFrame(module=sample.module, offset=sample.offset),
            *(StackFrame(module=m, offset=o) for m, o in sample.callers),
        )
        entry = groups.setdefault((sample.tid, counter, frames), [0, 0, vendor])
        entry[0] += sample.period
        entry[1] += 1

    stacks = [
        Stack(
            locus=Locus(node=node, rank=rank, thread=tid),
            counter=counter,
            frames=frames,
            value=float(value) * (vendor.scale if vendor is not None else 1.0),
            unit=vendor.unit
            if vendor is not None
            else _CLOCK_UNITS.get(counter, counter),
            sample_count=count,
            pass_index=pass_index,
        )
        for (tid, counter, frames), (value, count, vendor) in groups.items()
    ]
    stacks.sort(
        key=lambda s: (
            -s.value,
            s.counter,
            tuple((f.module, f.offset or 0) for f in s.frames),
        )
    )
    return stacks


def ingest(
    tool: str,
    version: str,
    directory: Path,
    node: str,
    rank: int | None = None,
    pass_index: int = 0,
) -> tuple[list[Measurement], list[Stack], list[Degradation]]:
    """Turn the raw artifacts of one collection into Measurements and
    the call paths recorded with them.

    Returns (measurements, stacks, degradations); an empty Measurement
    list with a degradation is a valid outcome, and stacks are empty
    whenever the recording carried none.
    """
    if tool == "sample":
        return _ingest_sample(directory, node, rank, pass_index)
    if tool != "perf" or not perf_script.supports(version):
        return [], [], [
            Degradation(
                name="ingestion-unsupported",
                message=f"no parser for {tool} {version}; raw outputs kept in the Run",
                remedy="upgrade nunatak, or use perf 6.4 or newer",
            )
        ]

    script_path = directory / perf_adapter.SCRIPT_OUTPUT
    if not script_path.is_file():
        return [], [], [
            Degradation(
                name="perf-script-missing",
                message="perf script produced no output; no Measurement for this Run",
                remedy="check the perf messages above; perf.data is kept in the Run",
            )
        ]

    buildid_path = directory / perf_adapter.BUILDID_OUTPUT
    module_ids = (
        perf_script.parse_buildid_list(buildid_path.read_text())
        if buildid_path.is_file()
        else {}
    )
    samples, unparsed = perf_script.parse_samples(script_path.read_text())

    degradations = []
    if unparsed:
        degradations.append(
            Degradation(
                name="perf-script-unparsed",
                message=f"{len(unparsed)} of {len(samples) + len(unparsed)} sample lines "
                f"not recognized (first: {unparsed[0][:80]!r})",
                remedy="report this line format; the other samples are ingested",
            )
        )
    return (
        measurements_from_samples(samples, module_ids, node, rank, pass_index),
        stacks_from_samples(samples, node, rank, pass_index),
        degradations,
    )


def _ingest_sample(
    directory: Path, node: str, rank: int | None, pass_index: int
) -> tuple[list[Measurement], list[Stack], list[Degradation]]:
    """Ingestion of /usr/bin/sample's report - the macOS temporal mode.

    The report self-symbolicates, but the pivot still receives
    `(module, offset)` hits like perf's: attribution stays one pipeline,
    and the Mach-O UUIDs stand where ELF build-ids do.
    """
    import json

    from nunatak.collect import sample as sample_adapter
    from nunatak.ingestion import sample_report

    report_path = directory / sample_adapter.REPORT_OUTPUT
    if not report_path.is_file():
        return [], [], [
            Degradation(
                name="sample-report-missing",
                message="sample produced no report; no Measurement for this Run",
                remedy="check the messages above; sampling another user's "
                "process needs elevated rights",
            )
        ]
    target = None
    meta_path = directory / sample_adapter.TARGET_META
    if meta_path.is_file():
        target = json.loads(meta_path.read_text()).get("target")
    samples, identities, version, unparsed = sample_report.parse(
        report_path.read_text(), target
    )
    if version is not None and version not in sample_report.REPORT_VERSIONS:
        return [], [], [
            Degradation(
                name="ingestion-unsupported",
                message=f"no parser for sample report version {version}; "
                "the raw report is kept in the Run",
                remedy="upgrade nunatak",
            )
        ]
    degradations = []
    if samples and not identities:
        # Measured on the corpus machine: the very first launch of a
        # freshly built binary can leave sample unable to enumerate the
        # binary images (first-run code-signing and dyld closure work).
        # The hits then keep their module names but lose their offsets.
        degradations.append(
            Degradation(
                name="sample-images-unavailable",
                message="sample could not enumerate the binary images: "
                "hits are attributed to whole modules, not addresses",
                remedy="run again - a binary's very first launch is the "
                "typical cause",
            )
        )
    if unparsed:
        degradations.append(
            Degradation(
                name="sample-report-unparsed",
                message=f"{len(unparsed)} report line(s) not recognized "
                f"(first: {unparsed[0][:80]!r})",
                remedy="report this line format; the other samples are ingested",
            )
        )
    return (
        measurements_from_samples(samples, identities, node, rank, pass_index),
        stacks_from_samples(samples, node, rank, pass_index),
        degradations,
    )
