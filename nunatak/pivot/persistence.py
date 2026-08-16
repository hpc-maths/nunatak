"""Persistence of a Run: Parquet for the measured pivot, JSON for the manifest.

The manifest is readable without nunatak - plain JSON carrying the complete
Machine snapshot, the Provenance, the Passes, the effective configuration
and the degradations. That is what makes a Run archivable at ten years.
"""

from __future__ import annotations

import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

import nunatak
from nunatak.pivot.model import (
    AddressDetail,
    Allocation,
    Ceiling,
    Collector,
    Degradation,
    Event,
    Hotspot,
    InlineFrame,
    LogicalIdentity,
    Locus,
    Machine,
    Measurement,
    Pass,
    PhysicalIdentity,
    Provenance,
    Quality,
    ResolutionLevel,
    Run,
    SourceExtract,
    Stack,
    StackFrame,
)

MANIFEST = "manifest.json"
PIVOT_DIR = "pivot"
# Schema 2: the hotspot column of measurements became nullable - a null
# hotspot is a Locus-level aggregate from the counting layer. Readers of
# schema 1 would look the null up in the hotspots table, hence the bump.
SCHEMA = 2

_HOTSPOTS = pa.schema(
    [
        ("id", pa.int32()),
        ("module", pa.string()),
        ("name", pa.string()),
        ("source_file", pa.string()),
        ("resolution_level", pa.string()),
        ("module_id", pa.string()),
        ("offset", pa.int64()),
    ]
)

_LOCI = pa.schema(
    [
        ("id", pa.int32()),
        ("node", pa.string()),
        ("rank", pa.int32()),
        ("thread", pa.int64()),
        ("device", pa.int32()),
        ("stream", pa.int64()),
    ]
)

_MEASUREMENTS = pa.schema(
    [
        ("hotspot", pa.int32()),
        ("locus", pa.int32()),
        ("pass_index", pa.int32()),
        ("counter", pa.string()),
        ("value", pa.float64()),
        ("unit", pa.string()),
        ("quality", pa.string()),
        ("reason", pa.string()),
        ("sample_count", pa.int64()),
        ("coverage", pa.float64()),
    ]
)

_EVENTS = pa.schema(
    [
        ("locus", pa.int32()),
        ("pass_index", pa.int32()),
        ("kind", pa.string()),
        ("name", pa.string()),
        ("start_ns", pa.int64()),
        ("duration_ns", pa.int64()),
        ("attributes", pa.string()),
    ]
)

# The internal detail of named Hotspots, normalized in two tables joined
# by (hotspot, offset): the weight of each sampled address, and its
# inlining chain one frame per row.
_ADDRESSES = pa.schema(
    [
        ("hotspot", pa.int32()),
        ("offset", pa.int64()),
        ("pass_index", pa.int32()),
        ("counter", pa.string()),
        ("value", pa.float64()),
        ("sample_count", pa.int64()),
    ]
)

_FRAMES = pa.schema(
    [
        ("hotspot", pa.int32()),
        ("offset", pa.int64()),
        ("depth", pa.int32()),
        ("function", pa.string()),
        ("file", pa.string()),
        ("line", pa.int64()),
        ("declaration_line", pa.int64()),
    ]
)

# Call paths in two tables joined by the stack id, like the attribution
# detail: the weight of each aggregated path, and its frames one row per
# depth - the hit at depth 0, callers outward.
_STACKS = pa.schema(
    [
        ("id", pa.int32()),
        ("locus", pa.int32()),
        ("pass_index", pa.int32()),
        ("counter", pa.string()),
        ("value", pa.float64()),
        ("unit", pa.string()),
        ("sample_count", pa.int64()),
    ]
)

_STACK_FRAMES = pa.schema(
    [
        ("stack", pa.int32()),
        ("depth", pa.int32()),
        ("module", pa.string()),
        ("offset", pa.int64()),
    ]
)

# Source extracts are the one non-measured content of the pivot: they are
# raw material for the report and the Explanation, embedded so the Run
# stays self-sufficient, never a conclusion.
_EXTRACTS = pa.schema(
    [
        ("hotspot", pa.int32()),
        ("file", pa.string()),
        ("resolved_path", pa.string()),
        ("start_line", pa.int64()),
        ("end_line", pa.int64()),
        ("text", pa.string()),
        ("truncated", pa.bool_()),
        ("reason", pa.string()),
    ]
)

_FILES = {
    "hotspots": f"{PIVOT_DIR}/hotspots.parquet",
    "loci": f"{PIVOT_DIR}/loci.parquet",
    "measurements": f"{PIVOT_DIR}/measurements.parquet",
    "events": f"{PIVOT_DIR}/events.parquet",
    "addresses": f"{PIVOT_DIR}/addresses.parquet",
    "frames": f"{PIVOT_DIR}/frames.parquet",
    "extracts": f"{PIVOT_DIR}/extracts.parquet",
    "stacks": f"{PIVOT_DIR}/stacks.parquet",
    "stack_frames": f"{PIVOT_DIR}/stack-frames.parquet",
}


def _hotspot_key(hotspot: Hotspot) -> object:
    """Deduplication key: the physical identity when the Hotspot has one,
    else the logical identity plus the display offset."""
    return hotspot.physical_identity or (hotspot.logical_identity, hotspot.offset)


def write_run(directory: Path, run: Run) -> Path:
    """Write `run` as a self-sufficient directory and return its path.

    Parameters: `directory` is the Run directory (created if needed), `run`
    the in-memory Run. Layout: `manifest.json` at the root, columnar data
    under `pivot/`.
    """
    directory = Path(directory)
    (directory / PIVOT_DIR).mkdir(parents=True, exist_ok=True)

    hotspots: dict[object, tuple[int, Hotspot]] = {}
    loci: dict[Locus, int] = {}
    for measurement in run.measurements:
        if measurement.hotspot is not None:
            hotspots.setdefault(
                _hotspot_key(measurement.hotspot), (len(hotspots), measurement.hotspot)
            )
        loci.setdefault(measurement.locus, len(loci))
    for detail in run.address_details:
        hotspots.setdefault(_hotspot_key(detail.hotspot), (len(hotspots), detail.hotspot))
    for extract in run.source_extracts:
        hotspots.setdefault(_hotspot_key(extract.hotspot), (len(hotspots), extract.hotspot))
    for event in run.events:
        loci.setdefault(event.locus, len(loci))
    for stack in run.stacks:
        loci.setdefault(stack.locus, len(loci))

    # One offset column serves both identities: an unresolved Hotspot keys
    # its physical identity with the same sampled address it displays, and
    # a named one only carries the function start in its physical identity.
    hotspot_rows = [
        {
            "id": index,
            "module": h.logical_identity.module,
            "name": h.logical_identity.name,
            "source_file": h.logical_identity.source_file,
            "resolution_level": h.resolution_level.value,
            "module_id": h.physical_identity.module_id if h.physical_identity else None,
            "offset": h.physical_identity.offset if h.physical_identity else h.offset,
        }
        for index, h in hotspots.values()
    ]
    locus_rows = [
        {
            "id": index,
            "node": locus.node,
            "rank": locus.rank,
            "thread": locus.thread,
            "device": locus.device,
            "stream": locus.stream,
        }
        for locus, index in loci.items()
    ]
    measurement_rows = [
        {
            "hotspot": hotspots[_hotspot_key(m.hotspot)][0] if m.hotspot is not None else None,
            "locus": loci[m.locus],
            "pass_index": m.pass_index,
            "counter": m.counter,
            "value": m.value,
            "unit": m.unit,
            "quality": m.quality.value,
            "reason": m.reason,
            "sample_count": m.sample_count,
            "coverage": m.coverage,
        }
        for m in run.measurements
    ]
    event_rows = [
        {
            "locus": loci[e.locus],
            "pass_index": e.pass_index,
            "kind": e.kind,
            "name": e.name,
            "start_ns": e.start_ns,
            "duration_ns": e.duration_ns,
            "attributes": json.dumps(dict(e.attributes)),
        }
        for e in run.events
    ]
    address_rows = [
        {
            "hotspot": hotspots[_hotspot_key(d.hotspot)][0],
            "offset": d.offset,
            "pass_index": d.pass_index,
            "counter": d.counter,
            "value": d.value,
            "sample_count": d.sample_count,
        }
        for d in run.address_details
    ]
    # The chain is a property of the address, shared by every counter
    # measured there: one set of frame rows per (hotspot, offset).
    chains = {
        (hotspots[_hotspot_key(d.hotspot)][0], d.offset): d.frames
        for d in run.address_details
    }
    frame_rows = [
        {
            "hotspot": hotspot_id,
            "offset": offset,
            "depth": depth,
            "function": frame.function,
            "file": frame.file,
            "line": frame.line,
            "declaration_line": frame.declaration_line,
        }
        for (hotspot_id, offset), frames in chains.items()
        for depth, frame in enumerate(frames)
    ]

    stack_rows = [
        {
            "id": index,
            "locus": loci[s.locus],
            "pass_index": s.pass_index,
            "counter": s.counter,
            "value": s.value,
            "unit": s.unit,
            "sample_count": s.sample_count,
        }
        for index, s in enumerate(run.stacks)
    ]
    stack_frame_rows = [
        {
            "stack": index,
            "depth": depth,
            "module": frame.module,
            "offset": frame.offset,
        }
        for index, s in enumerate(run.stacks)
        for depth, frame in enumerate(s.frames)
    ]

    extract_rows = [
        {
            "hotspot": hotspots[_hotspot_key(e.hotspot)][0],
            "file": e.file,
            "resolved_path": e.resolved_path,
            "start_line": e.start_line,
            "end_line": e.end_line,
            "text": e.text,
            "truncated": e.truncated,
            "reason": e.reason,
        }
        for e in run.source_extracts
    ]

    for name, schema, rows in (
        ("hotspots", _HOTSPOTS, hotspot_rows),
        ("loci", _LOCI, locus_rows),
        ("measurements", _MEASUREMENTS, measurement_rows),
        ("events", _EVENTS, event_rows),
        ("addresses", _ADDRESSES, address_rows),
        ("frames", _FRAMES, frame_rows),
        ("extracts", _EXTRACTS, extract_rows),
        ("stacks", _STACKS, stack_rows),
        ("stack_frames", _STACK_FRAMES, stack_frame_rows),
    ):
        pq.write_table(pa.Table.from_pylist(rows, schema=schema), directory / _FILES[name])

    (directory / MANIFEST).write_text(
        json.dumps(manifest(run), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return directory


def machine_to_dict(machine: Machine) -> dict:
    """The plain-JSON form of a Machine, shared by the Run manifest and
    the profile cache so the two never drift apart."""
    return {
        "system": machine.system,
        "kernel": machine.kernel,
        "architecture": machine.architecture,
        "cpu_model": machine.cpu_model,
        "logical_cores": machine.logical_cores,
        "allocation": {
            "visible_cores": machine.allocation.visible_cores,
            "affinity_mask": list(machine.allocation.affinity_mask)
            if machine.allocation.affinity_mask is not None
            else None,
            "cpu_quota": machine.allocation.cpu_quota,
            "memory_limit_bytes": machine.allocation.memory_limit_bytes,
        },
        "ceilings": [
            {
                "name": c.name,
                "value": c.value,
                "unit": c.unit,
                "quality": c.quality.value,
                "reason": c.reason,
            }
            for c in machine.ceilings
        ],
    }


def machine_from_dict(data: dict) -> Machine:
    """Rebuild a Machine from its plain-JSON form.

    A snapshot written before the allocation shape existed reads back
    with an empty Allocation: absent is not zero.
    """
    allocation = data.get("allocation") or {}
    mask = allocation.get("affinity_mask")
    return Machine(
        system=data["system"],
        kernel=data["kernel"],
        architecture=data["architecture"],
        cpu_model=data["cpu_model"],
        logical_cores=data["logical_cores"],
        allocation=Allocation(
            visible_cores=allocation.get("visible_cores"),
            affinity_mask=tuple(mask) if mask is not None else None,
            cpu_quota=allocation.get("cpu_quota"),
            memory_limit_bytes=allocation.get("memory_limit_bytes"),
        ),
        ceilings=tuple(
            Ceiling(
                name=c["name"],
                value=c["value"],
                unit=c["unit"],
                quality=Quality(c["quality"]),
                reason=c["reason"],
            )
            for c in data["ceilings"]
        ),
    )


def manifest(run: Run) -> dict:
    """The manifest content: plain JSON, readable without nunatak.

    Also the trunk of the report payload, so the two never drift apart.
    """
    return {
        "format": {
            "name": "nunatak-run",
            "schema": SCHEMA,
            "generated_by": f"nunatak {nunatak.__version__}",
        },
        "run": {
            "name": run.name,
            "created": run.created,
            "command": run.command,
            "exit_code": run.exit_code,
        },
        "machine": machine_to_dict(run.machine),
        "provenance": {
            "commit": run.provenance.commit,
            "dirty_tree": run.provenance.dirty_tree,
            "dependencies": run.provenance.dependencies,
            "effective_configuration": run.provenance.effective_configuration,
        },
        "passes": [
            {
                "index": p.index,
                "exit_code": p.exit_code,
                "start": p.start,
                "end": p.end,
                "collectors": [{"tool": c.tool, "version": c.version} for c in p.collectors],
            }
            for p in run.passes
        ],
        "degradations": [
            {"name": d.name, "message": d.message, "remedy": d.remedy}
            for d in run.degradations
        ],
        "files": _FILES,
    }


def read_run(directory: Path) -> Run:
    """Read a Run directory written by `write_run` and return the Run.

    Raises `ValueError` when the directory is not a Run or was written by a
    newer schema than this version understands.
    """
    directory = Path(directory)
    manifest_path = directory / MANIFEST
    if not manifest_path.is_file():
        raise ValueError(f"{directory} is not a Run: no {MANIFEST}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    fmt = manifest.get("format", {})
    if fmt.get("name") != "nunatak-run":
        raise ValueError(f"{manifest_path} is not a nunatak Run manifest")
    if fmt.get("schema", 0) > SCHEMA:
        raise ValueError(
            f"Run written with schema {fmt['schema']}, newer than the supported {SCHEMA}; "
            "upgrade nunatak to read it"
        )

    # The manifest says which tables this Run carries: a Run written before
    # a table existed simply reads back without it.
    tables = {
        name: pq.read_table(directory / path).to_pylist()
        for name, path in manifest["files"].items()
    }

    hotspots = {}
    for row in tables["hotspots"]:
        physical = (
            PhysicalIdentity(module_id=row["module_id"], offset=row["offset"])
            if row["module_id"] is not None
            else None
        )
        resolution_level = ResolutionLevel(row["resolution_level"])
        hotspots[row["id"]] = Hotspot(
            logical_identity=LogicalIdentity(
                module=row["module"], name=row["name"], source_file=row["source_file"]
            ),
            resolution_level=resolution_level,
            physical_identity=physical,
            # The display offset only exists on unresolved Hotspots; on a
            # named one the offset column holds the function start, which
            # already lives in the physical identity above.
            offset=row["offset"]
            if resolution_level is ResolutionLevel.UNRESOLVED
            else None,
        )
    loci = {
        row["id"]: Locus(
            node=row["node"],
            rank=row["rank"],
            thread=row["thread"],
            device=row["device"],
            stream=row["stream"],
        )
        for row in tables["loci"]
    }

    measurements = [
        Measurement(
            hotspot=hotspots[row["hotspot"]] if row["hotspot"] is not None else None,
            locus=loci[row["locus"]],
            counter=row["counter"],
            value=row["value"],
            unit=row["unit"],
            quality=Quality(row["quality"]),
            reason=row["reason"],
            sample_count=row["sample_count"],
            coverage=row["coverage"],
            pass_index=row["pass_index"],
        )
        for row in tables["measurements"]
    ]
    events = [
        Event(
            locus=loci[row["locus"]],
            kind=row["kind"],
            name=row["name"],
            start_ns=row["start_ns"],
            duration_ns=row["duration_ns"],
            pass_index=row["pass_index"],
            attributes=tuple(sorted(json.loads(row["attributes"]).items())),
        )
        for row in tables["events"]
    ]

    chains: dict[tuple[int, int], dict[int, InlineFrame]] = {}
    for row in tables.get("frames", []):
        chains.setdefault((row["hotspot"], row["offset"]), {})[row["depth"]] = InlineFrame(
            function=row["function"],
            file=row["file"],
            line=row["line"],
            declaration_line=row["declaration_line"],
        )
    address_details = [
        AddressDetail(
            hotspot=hotspots[row["hotspot"]],
            offset=row["offset"],
            counter=row["counter"],
            value=row["value"],
            sample_count=row["sample_count"],
            pass_index=row["pass_index"],
            frames=tuple(
                frame
                for _, frame in sorted(
                    chains.get((row["hotspot"], row["offset"]), {}).items()
                )
            ),
        )
        for row in tables.get("addresses", [])
    ]

    stack_chains: dict[int, dict[int, StackFrame]] = {}
    for row in tables.get("stack_frames", []):
        stack_chains.setdefault(row["stack"], {})[row["depth"]] = StackFrame(
            module=row["module"], offset=row["offset"]
        )
    stacks = [
        Stack(
            locus=loci[row["locus"]],
            counter=row["counter"],
            frames=tuple(
                frame for _, frame in sorted(stack_chains.get(row["id"], {}).items())
            ),
            value=row["value"],
            unit=row["unit"],
            sample_count=row["sample_count"],
            pass_index=row["pass_index"],
        )
        for row in tables.get("stacks", [])
    ]

    machine = machine_from_dict(manifest["machine"])
    provenance_data = manifest["provenance"]
    provenance = Provenance(
        commit=provenance_data["commit"],
        dirty_tree=provenance_data["dirty_tree"],
        dependencies=provenance_data["dependencies"],
        effective_configuration=provenance_data["effective_configuration"],
    )
    run_data = manifest["run"]
    return Run(
        name=run_data["name"],
        created=run_data["created"],
        command=run_data["command"],
        exit_code=run_data["exit_code"],
        machine=machine,
        provenance=provenance,
        passes=[
            Pass(
                index=p["index"],
                exit_code=p["exit_code"],
                collectors=tuple(
                    Collector(tool=c["tool"], version=c["version"]) for c in p["collectors"]
                ),
                start=p["start"],
                end=p["end"],
            )
            for p in manifest["passes"]
        ],
        degradations=[
            Degradation(name=d["name"], message=d["message"], remedy=d["remedy"])
            for d in manifest["degradations"]
        ],
        measurements=measurements,
        events=events,
        address_details=address_details,
        stacks=stacks,
        source_extracts=[
            SourceExtract(
                hotspot=hotspots[row["hotspot"]],
                file=row["file"],
                resolved_path=row["resolved_path"],
                start_line=row["start_line"],
                end_line=row["end_line"],
                text=row["text"],
                truncated=row["truncated"],
                reason=row["reason"],
            )
            for row in tables.get("extracts", [])
        ],
    )
