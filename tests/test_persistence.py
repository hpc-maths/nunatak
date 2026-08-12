"""Persistence of a Run: Parquet round-trip and standalone JSON manifest."""

import json

import pyarrow.parquet as pq
import pytest

from nunatak.pivot import (
    AddressDetail,
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
    read_run,
    write_run,
)


def sample_run() -> Run:
    machine = Machine(
        system="Linux 6.8",
        kernel="6.8.0-41-generic",
        architecture="x86_64",
        cpu_model="AMD EPYC 9354",
        logical_cores=64,
        ceilings=(
            Ceiling(
                name="dram_bandwidth",
                value=460e9,
                unit="byte/s",
                quality=Quality.ESTIMATED,
                reason="theoretical fallback: calibration not run yet",
            ),
        ),
    )
    hotspot = Hotspot(
        logical_identity=LogicalIdentity(module="/opt/app/solver"),
        resolution_level=ResolutionLevel.UNRESOLVED,
        physical_identity=PhysicalIdentity(module_id="deadbeef", offset=0x1A2B),
        offset=0x1A2B,
    )
    locus = Locus(node="n0", rank=None, thread=4242)
    return Run(
        name="solver-20260809-142233",
        created="2026-08-09T14:22:33+02:00",
        command=["./solver", "--steps", "100"],
        exit_code=0,
        machine=machine,
        provenance=Provenance(
            commit="354e145",
            dirty_tree=False,
            dependencies={"libm.so.6": "buildid:1234"},
            effective_configuration={"thresholds.coverage": 0.8, "runs_dir": ".nunatak"},
        ),
        passes=[Pass(index=0, exit_code=0, collectors=(Collector(tool="perf", version="6.12"),))],
        degradations=[
            Degradation(
                name="explanation-unavailable",
                message="no route to the provider from this node",
                remedy="rerun `nunatak explain` from a login node",
            )
        ],
        measurements=[
            Measurement(
                hotspot=hotspot,
                locus=locus,
                counter="cpu-clock",
                value=2.5e9,
                unit="ns",
                quality=Quality.MEASURED,
                sample_count=10000,
            ),
            Measurement(
                hotspot=hotspot,
                locus=locus,
                counter="flops_dp",
                value=None,
                unit="flop",
                quality=Quality.UNAVAILABLE,
                reason="no FLOP raw counter on this microarchitecture",
            ),
        ],
        events=[
            Event(
                locus=locus,
                kind="mpi_call",
                name="MPI_Allreduce",
                start_ns=120_000,
                duration_ns=4_000,
                attributes=(("bytes", "8192"),),
            )
        ],
    )


def test_round_trip_preserves_the_run(tmp_path):
    directory = write_run(tmp_path / "run", sample_run())
    assert read_run(directory) == sample_run()


def test_round_trip_preserves_a_named_hotspot(tmp_path):
    # A named Hotspot carries the function start in its physical identity
    # and no display offset; both must survive persistence unchanged.
    run = sample_run()
    named = Hotspot(
        logical_identity=LogicalIdentity(
            module="/opt/app/solver", name="main", source_file="/src/solver.c"
        ),
        resolution_level=ResolutionLevel.LINE,
        physical_identity=PhysicalIdentity(module_id="deadbeef", offset=0x10C0),
    )
    run.measurements = [
        Measurement(
            hotspot=named,
            locus=run.measurements[0].locus,
            counter="cycles",
            value=1.0e9,
            unit="cycles",
            quality=Quality.MEASURED,
            sample_count=1000,
        )
    ]
    directory = write_run(tmp_path / "run", run)
    (measurement,) = read_run(directory).measurements
    assert measurement.hotspot == named


def test_a_run_is_a_single_directory(tmp_path):
    # Everything the Run needs lives under its directory.
    directory = write_run(tmp_path / "run", sample_run())
    written = {p for p in directory.rglob("*") if p.is_file()}
    assert written == {
        directory / "manifest.json",
        directory / "pivot" / "hotspots.parquet",
        directory / "pivot" / "loci.parquet",
        directory / "pivot" / "measurements.parquet",
        directory / "pivot" / "events.parquet",
        directory / "pivot" / "addresses.parquet",
        directory / "pivot" / "frames.parquet",
        directory / "pivot" / "extracts.parquet",
    }


def test_manifest_is_readable_without_nunatak(tmp_path):
    directory = write_run(tmp_path / "run", sample_run())
    manifest = json.loads((directory / "manifest.json").read_text())
    # The complete Machine snapshot is embedded: a Run stripped of any cache
    # remains analyzable.
    assert manifest["machine"]["ceilings"][0]["name"] == "dram_bandwidth"
    assert manifest["provenance"]["effective_configuration"]["thresholds.coverage"] == 0.8
    assert manifest["degradations"][0]["name"] == "explanation-unavailable"
    assert manifest["run"]["exit_code"] == 0
    assert manifest["files"]["measurements"] == "pivot/measurements.parquet"


def test_pivot_stores_no_conclusion(tmp_path):
    # The measured pivot carries no classification, no roofline placement,
    # no advice - and no absolute address: only module-relative offsets.
    directory = write_run(tmp_path / "run", sample_run())
    assert set(pq.read_schema(directory / "pivot" / "measurements.parquet").names) == {
        "hotspot",
        "locus",
        "pass_index",
        "counter",
        "value",
        "unit",
        "quality",
        "reason",
        "sample_count",
        "coverage",
    }
    assert set(pq.read_schema(directory / "pivot" / "hotspots.parquet").names) == {
        "id",
        "module",
        "name",
        "source_file",
        "resolution_level",
        "module_id",
        "offset",
    }


def test_unavailable_round_trips_as_null_not_zero(tmp_path):
    directory = write_run(tmp_path / "run", sample_run())
    rows = pq.read_table(directory / "pivot" / "measurements.parquet").to_pylist()
    unavailable = [r for r in rows if r["quality"] == "unavailable"]
    assert unavailable and all(r["value"] is None for r in unavailable)


def test_newer_schema_is_refused(tmp_path):
    directory = write_run(tmp_path / "run", sample_run())
    manifest = json.loads((directory / "manifest.json").read_text())
    manifest["format"]["schema"] = 999
    (directory / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="newer"):
        read_run(directory)


def test_a_directory_without_manifest_is_not_a_run(tmp_path):
    with pytest.raises(ValueError, match="not a Run"):
        read_run(tmp_path)


def named_hotspot() -> Hotspot:
    return Hotspot(
        logical_identity=LogicalIdentity(
            module="/opt/app/solver", name="main", source_file="/src/solver.c"
        ),
        resolution_level=ResolutionLevel.LINE,
        physical_identity=PhysicalIdentity(module_id="deadbeef", offset=0x10C0),
    )


def test_round_trip_preserves_the_attribution_detail(tmp_path):
    # The inlining chain and per-address weights must survive persistence:
    # they are what a report ventilates a Hotspot by line with, on a
    # machine where the binary no longer exists.
    run = sample_run()
    hotspot = named_hotspot()
    run.measurements = []
    run.address_details = [
        AddressDetail(
            hotspot=hotspot,
            offset=0x10F4,
            counter="cycles",
            value=800.0,
            sample_count=8,
            frames=(
                InlineFrame(
                    function="axpy",
                    file="/src/axpy.h",
                    line=12,
                    declaration_line=10,
                ),
                InlineFrame(
                    function="main",
                    file="/src/solver.c",
                    line=40,
                    declaration_line=35,
                ),
            ),
        ),
        AddressDetail(
            hotspot=hotspot,
            offset=0x10F4,
            counter="instructions",
            value=3200.0,
            sample_count=8,
            frames=(
                InlineFrame(
                    function="axpy",
                    file="/src/axpy.h",
                    line=12,
                    declaration_line=10,
                ),
                InlineFrame(
                    function="main",
                    file="/src/solver.c",
                    line=40,
                    declaration_line=35,
                ),
            ),
        ),
    ]
    directory = write_run(tmp_path / "run", run)
    read = read_run(directory)
    assert read.address_details == run.address_details

    # The chain is stored once per address, not once per counter.
    frames = pq.read_table(directory / "pivot" / "frames.parquet").to_pylist()
    assert len(frames) == 2


def test_a_run_written_before_the_detail_tables_reads_back(tmp_path):
    # The manifest says which tables a Run carries: dropping the new files
    # and their manifest entries reproduces a Run written by an older
    # nunatak, and it must read back without them.
    directory = write_run(tmp_path / "run", sample_run())
    manifest = json.loads((directory / "manifest.json").read_text())
    for name in ("addresses", "frames"):
        (directory / manifest["files"].pop(name)).unlink()
    (directory / "manifest.json").write_text(json.dumps(manifest))

    run = read_run(directory)
    assert run.address_details == []
    assert run.measurements == sample_run().measurements


def test_round_trip_preserves_source_extracts(tmp_path):
    run = sample_run()
    run.source_extracts = [
        SourceExtract(
            hotspot=named_hotspot(),
            file="/src/solver.c",
            resolved_path="/home/me/solver.c",
            start_line=12,
            end_line=40,
            text="double s = 0.0;\nfor (...) {}\n",
        ),
        SourceExtract(
            hotspot=named_hotspot(),
            file="/build/mystery.c",
            reason="source file not found on this machine",
        ),
    ]
    directory = write_run(tmp_path / "run", run)
    assert read_run(directory).source_extracts == run.source_extracts


def test_round_trip_preserves_a_locus_level_aggregate(tmp_path):
    run = sample_run()
    aggregate = Measurement(
        hotspot=None,
        locus=Locus(node="n1", rank=3),
        counter="task-clock",
        value=2.5e9,
        unit="ns",
        quality=Quality.MEASURED,
    )
    run.measurements.append(aggregate)
    directory = write_run(tmp_path / "run", run)
    back = read_run(directory)
    assert aggregate in back.measurements
    # The counting layer adds no Hotspot row: there is nothing to attribute.
    hotspots = pq.read_table(directory / "pivot" / "hotspots.parquet").to_pylist()
    assert len(hotspots) == 1
