"""Ingestion: versioned parsers turning collector outputs into Measurements.

One parser per (tool, detected version) couple. This is where the
normalization into module offsets happens: no absolute address crosses
this boundary, so ASLR and library load order cannot split a Hotspot. A tool version the ingestion does not
recognize is declared as a degradation rather than parsed blindly - the
raw outputs stay in the Run for a later nunatak to ingest.
"""

from __future__ import annotations

import os
import re
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


# What counts as the interpreter itself: CPython's binary or its shared
# library. Only these fold - a native extension is an application
# module like any other.
_INTERPRETER_MODULE = re.compile(r"^(python(\d+(\.\d+)*)?|libpython[\w.]*)$")


def _python_identity(sample: Sample) -> tuple[str, str] | None:
    """The Python function this sample's time belongs to, or None.

    The attribution chapter's rule: a hit in the interpreter folds onto
    the innermost Python frame above it - the time of interpreting a
    function belongs to that function, its exact sense - and a hit
    inside a trampoline is that function directly. A native extension
    leaf keeps its native identity, the Python caller staying visible
    in the recorded stack: interpreter frames are never Hotspots,
    extension Hotspots never stop being native.
    """
    if not sample.python_frames:
        return None
    position, function, file = min(sample.python_frames)
    if position == 0:
        return function, file
    if _INTERPRETER_MODULE.match(os.path.basename(sample.module)):
        return function, file
    return None


def _python_hotspot(function: str, file: str) -> Hotspot:
    """A Hotspot at the Python grain: `(file, function)`, the identity
    that survives everything an interpreter does to addresses. No
    physical identity - only native code has one."""
    return Hotspot(
        logical_identity=LogicalIdentity(
            module=file, name=function, source_file=file
        ),
        resolution_level=ResolutionLevel.FUNCTION,
    )


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
        python = _python_identity(sample)
        if python is not None:
            key = (python[1], None, sample.tid, counter, python[0])
        else:
            key = (sample.module, sample.offset, sample.tid, counter, None)
        entry = groups.setdefault(key, [0, 0])
        entry[0] += sample.period
        entry[1] += 1

    measurements = []
    for (module, offset, tid, counter, python_name), (value, count) in groups.items():
        module_id = module_ids.get(module)
        physical = (
            PhysicalIdentity(module_id=module_id, offset=offset)
            if module_id is not None and offset is not None
            else None
        )
        vendor = vendor_by_counter.get(counter)
        measurements.append(
            Measurement(
                hotspot=_python_hotspot(python_name, module)
                if python_name is not None
                else Hotspot(
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
        # A map frame's name arrives with the sample and nowhere else:
        # it is written on the frame now, where the attribution pass -
        # which skips pseudo modules - will leave it standing.
        named = {position: function for position, function, _ in sample.python_frames}
        frames = (
            StackFrame(
                module=sample.module, offset=sample.offset,
                function=named.get(0),
            ),
            *(
                StackFrame(module=m, offset=o, function=named.get(index + 1))
                for index, (m, o) in enumerate(sample.callers)
            ),
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
    if tool == "xctrace":
        return _ingest_xctrace(directory, node, rank, pass_index)
    if tool == "py-spy":
        return _ingest_pyspy(directory, version, node, rank, pass_index)
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


def _ingest_pyspy(
    directory: Path, version: str, node: str, rank: int | None, pass_index: int
) -> tuple[list[Measurement], list[Stack], list[Degradation]]:
    """Ingestion of py-spy's raw collapsed stacks - the temporal
    fallback where the trampolines do not exist.

    Every frame is Python, so the lines become Samples whose folding
    yields the same `(file, function)` Hotspots the trampoline path
    does; the recorded rate turns hit counts back into time.
    """
    import json

    from nunatak.collect import pyspy as pyspy_adapter
    from nunatak.ingestion import pyspy_raw

    if not pyspy_raw.supports(version):
        return [], [], [
            Degradation(
                name="ingestion-unsupported",
                message=f"no parser for py-spy {version}; raw outputs kept in the Run",
                remedy="upgrade nunatak",
            )
        ]
    raw_path = directory / pyspy_adapter.RAW_OUTPUT
    if not raw_path.is_file():
        return [], [], [
            Degradation(
                name="python-sampling-missing",
                message="py-spy produced no stacks; no Measurement for this Run",
                remedy="check the py-spy messages above",
            )
        ]
    rate = 100
    meta_path = directory / pyspy_adapter.META_OUTPUT
    if meta_path.is_file():
        rate = int(json.loads(meta_path.read_text()).get("rate", rate))
    samples, unparsed = pyspy_raw.parse_samples(raw_path.read_text(), rate)
    degradations = []
    if unparsed:
        degradations.append(
            Degradation(
                name="python-sampling-unparsed",
                message=f"{len(unparsed)} py-spy line(s) not recognized "
                f"(first: {unparsed[0][:80]!r})",
                remedy="report this line format; the other stacks are ingested",
            )
        )
    return (
        measurements_from_samples(samples, {}, node, rank, pass_index),
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


def _ingest_xctrace(
    directory: Path, node: str, rank: int | None, pass_index: int
) -> tuple[list[Measurement], list[Stack], list[Degradation]]:
    """Ingestion of xctrace's exported time-profile table.

    Per-address weights and exact leaf PCs: the macOS nominal grain,
    through the same pipeline as everything else."""
    from nunatak.collect import xctrace as xctrace_adapter
    from nunatak.ingestion import xctrace_profile

    profile_path = directory / xctrace_adapter.PROFILE_OUTPUT
    if not profile_path.is_file():
        return [], [], [
            Degradation(
                name="xctrace-export-missing",
                message="xctrace exported no time-profile table; "
                "no Measurement for this Run",
                remedy="check the messages above; the .trace bundle is "
                "kept in the Run",
            )
        ]
    samples, identities, unparsed = xctrace_profile.parse(profile_path.read_text())
    degradations = []
    if unparsed:
        degradations.append(
            Degradation(
                name="xctrace-export-unparsed",
                message=f"{len(unparsed)} export row(s) not recognized "
                f"(first: {unparsed[0][:80]!r})",
                remedy="report this export format; the other samples "
                "are ingested",
            )
        )
    return (
        measurements_from_samples(samples, identities, node, rank, pass_index),
        stacks_from_samples(samples, node, rank, pass_index),
        degradations,
    )
