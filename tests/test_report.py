"""The report payload: the contract between the core and the mini-app.

Synthetic pivots pin each section's shape; the replayed milestone corpus
entry is held as a snapshot, so any change to what the report sees
becomes a diff read in review - the same discipline the test strategy
imposes on the LLM prompt.
"""

import io
import json
import os
from contextlib import redirect_stdout
from pathlib import Path

from nunatak import analysis, report
from nunatak.pivot import AddressDetail, InlineFrame, Locus, SourceExtract, Stack, StackFrame
from tests.test_analysis import aggregate, balanced, hotspot, measurement, ranked, run_with

SNAPSHOT = Path(__file__).parent / "snapshots" / "report-payload-workload-c-roofline.json"
ENTRY = (
    Path(__file__).resolve().parent.parent
    / "corpus"
    / "recordings"
    / "perf"
    / "6.14.11"
    / "linux-x86_64"
    / "workload-c-roofline"
)


def frame(function, line=None, declaration_line=None):
    return InlineFrame(
        function=function, file="/src/app.c", line=line, declaration_line=declaration_line
    )


def detail(spot, offset, value, frames, counter="task-clock"):
    return AddressDetail(
        hotspot=spot, offset=offset, counter=counter, value=value, frames=tuple(frames)
    )


def payload_of(measurements, **run_fields):
    run = run_with(measurements)
    for name, value in run_fields.items():
        setattr(run, name, value)
    return report.build(run, analysis.diagnose(run))


class TestShape:
    def test_the_payload_is_json_serializable(self):
        spot = hotspot()
        payload = payload_of(
            [measurement(spot, "task-clock", 2e9, "ns")],
            address_details=[detail(spot, 0x10, 90.0, [frame("main", line=12)])],
            source_extracts=[
                SourceExtract(hotspot=spot, file="/src/app.c", text="int main()")
            ],
        )
        json.dumps(payload)

    def test_a_derived_metric_keeps_its_lineage_and_reason(self):
        payload = payload_of([measurement(hotspot(), "task-clock", 2e9, "ns")])
        share = payload["hotspots"][0]["share"]
        assert share == {
            "value": 1.0,
            "unit": "fraction",
            "quality": "measured",
            "lineage": ["task-clock"],
            "formula": "task-clock of the Hotspot / task-clock of the Run",
            "reason": None,
        }
        intensity = payload["hotspots"][0]["dram_intensity"]
        assert intensity["value"] is None
        assert intensity["quality"] == "unavailable"
        assert intensity["reason"] == "no flops_dp raw counter in this Run"

    def test_the_trunk_is_the_manifest(self):
        payload = payload_of([measurement(hotspot(), "task-clock", 2e9, "ns")])
        assert payload["format"]["name"] == "nunatak-report"
        assert payload["format"]["schema"] == report.payload.SCHEMA
        assert payload["run"]["command"] == ["./solver"]
        assert payload["machine"]["ceilings"][0]["name"] == "dram_bandwidth"


class TestCoverage:
    def test_samples_seconds_and_loci(self):
        spot = hotspot()
        payload = payload_of(
            [
                measurement(spot, "task-clock", 2e9, "ns", thread=1),
                measurement(spot, "task-clock", 1e9, "ns", thread=2),
            ]
        )
        assert payload["coverage"] == {
            "time_base": "task-clock",
            "samples": 200,
            "seconds": 3.0,
            "loci": 2,
        }

    def test_a_cycles_time_base_has_no_seconds(self):
        payload = payload_of([measurement(hotspot(), "cycles", 4e9, "cycle")])
        assert payload["coverage"]["time_base"] == "cycles"
        assert payload["coverage"]["seconds"] is None


class TestLines:
    def test_samples_are_distributed_over_the_physical_lines(self):
        # Two addresses on line 12 - one of them through an inline chain -
        # and one on line 14: the physical frame is the last of the chain.
        spot = hotspot()
        payload = payload_of(
            [measurement(spot, "task-clock", 2e9, "ns")],
            address_details=[
                detail(spot, 0x10, 60.0, [frame("main", line=12)]),
                detail(
                    spot,
                    0x14,
                    20.0,
                    [frame("axpy", line=4, declaration_line=3), frame("main", line=12)],
                ),
                detail(spot, 0x20, 20.0, [frame("main", line=14)]),
            ],
        )
        assert payload["hotspots"][0]["lines"] == [
            {"line": 12, "share": 0.8},
            {"line": 14, "share": 0.2},
        ]

    def test_an_address_without_a_line_is_left_out(self):
        # Absent is not line zero: the address still weighs in the total,
        # so the named lines admit what they do not cover.
        spot = hotspot()
        payload = payload_of(
            [measurement(spot, "task-clock", 2e9, "ns")],
            address_details=[
                detail(spot, 0x10, 75.0, [frame("main", line=12)]),
                detail(spot, 0x18, 25.0, [frame("main")]),
            ],
        )
        assert payload["hotspots"][0]["lines"] == [{"line": 12, "share": 0.75}]

    def test_the_distribution_reads_the_time_base_counter(self):
        spot = hotspot()
        payload = payload_of(
            [measurement(spot, "task-clock", 2e9, "ns")],
            address_details=[
                detail(spot, 0x10, 90.0, [frame("main", line=12)]),
                detail(spot, 0x10, 500.0, [frame("main", line=12)], counter="flops"),
                detail(spot, 0x20, 10.0, [frame("main", line=14)]),
            ],
        )
        assert payload["hotspots"][0]["lines"] == [
            {"line": 12, "share": 0.9},
            {"line": 14, "share": 0.1},
        ]


class TestInlineFrames:
    def test_ventilation_by_innermost_frame_sums_to_one(self):
        spot = hotspot()
        payload = payload_of(
            [measurement(spot, "task-clock", 2e9, "ns")],
            address_details=[
                detail(
                    spot,
                    0x10,
                    70.0,
                    [frame("axpy", line=4, declaration_line=3), frame("main", line=12)],
                ),
                detail(
                    spot,
                    0x14,
                    10.0,
                    [frame("axpy", line=5, declaration_line=3), frame("main", line=12)],
                ),
                detail(spot, 0x20, 20.0, [frame("main", line=14)]),
            ],
        )
        frames = payload["hotspots"][0]["inline_frames"]
        assert frames == [
            {"function": "axpy", "file": "/src/app.c", "line": 3, "share": 0.8},
            {"function": "main", "file": "/src/app.c", "line": None, "share": 0.2},
        ]
        assert sum(f["share"] for f in frames) == 1.0

    def test_without_address_details_the_detail_views_are_empty(self):
        payload = payload_of([measurement(hotspot(), "task-clock", 2e9, "ns")])
        assert payload["hotspots"][0]["lines"] == []
        assert payload["hotspots"][0]["inline_frames"] == []
        assert payload["hotspots"][0]["source"] is None


class TestOthers:
    def test_skipped_hotspots_are_counted_with_their_share(self):
        payload = payload_of(
            [
                measurement(hotspot(), "task-clock", 3e9, "ns"),
                measurement(hotspot("tiny"), "task-clock", 1e9, "ns", samples=3),
            ]
        )
        assert payload["others"] == {"count": 1, "share": 0.25}

    def test_no_aggregate_when_every_hotspot_is_diagnosed(self):
        payload = payload_of([measurement(hotspot(), "task-clock", 2e9, "ns")])
        assert payload["others"] is None

    def test_without_a_time_base_the_share_stays_null(self):
        payload = payload_of(
            [
                measurement(hotspot(), "flops_dp", 3e9, "flop"),
                measurement(hotspot("tiny"), "flops_dp", 1e9, "flop", samples=3),
            ]
        )
        assert payload["others"] == {"count": 1, "share": None}


class TestReplayedSnapshot:
    """The payload of the milestone Run, frozen. On a legitimate change,
    regenerate with NUNATAK_UPDATE_SNAPSHOTS=1 and read the diff."""

    def normalized(self, payload):
        data = json.loads(json.dumps(payload))
        data["format"]["generated_by"] = "nunatak"
        data["run"]["name"] = "workload"
        data["run"]["created"] = "TIMESTAMP"
        for pass_ in data["passes"]:
            pass_["start"] = pass_["end"] = "TIMESTAMP"
        # A replayed Run borrows the identity of the replaying host; the
        # ceilings, replayed from the recorded calibration, are the truth.
        for key in ("system", "kernel", "architecture", "cpu_model", "logical_cores"):
            data["machine"][key] = "REPLAY-HOST"
        data["machine"]["allocation"] = "REPLAY-HOST"
        for entry in data["hotspots"]:
            if entry["source"] and entry["source"]["resolved_path"]:
                entry["source"]["resolved_path"] = "RESOLVED"
        return data

    def test_the_milestone_payload_is_frozen(self, tmp_path, monkeypatch, capsys):
        from tests.support import ROOFLINE_WORKLOAD_C

        from nunatak.cli import principal
        from nunatak.pivot import read_run

        (tmp_path / "nunatak.toml").write_text(
            '[tools]\nllvm-symbolizer = "/usr/lib/llvm-19/bin/llvm-symbolizer"\n'
        )
        # The exact source the roofline entry was compiled from: on the
        # capture machine the recorded DWARF path resolves directly, on
        # every other machine the basename search finds this copy - both
        # embed the same text or the snapshot would be machine-dependent.
        (tmp_path / "workload.c").write_text(ROOFLINE_WORKLOAD_C)
        monkeypatch.chdir(tmp_path)
        out = io.StringIO()
        with redirect_stdout(out):
            assert (
                principal(["run", "--replay", str(ENTRY), "--json", "--", "./workload"])
                == 0
            )
        capsys.readouterr()
        run = read_run(json.loads(out.getvalue())["run"])

        payload = report.build(run, analysis.diagnose(run))
        rendered = (
            json.dumps(self.normalized(payload), indent=2, ensure_ascii=False, sort_keys=True)
            + "\n"
        )
        if os.environ.get("NUNATAK_UPDATE_SNAPSHOTS"):
            SNAPSHOT.parent.mkdir(exist_ok=True)
            SNAPSHOT.write_text(rendered, encoding="utf-8")
        assert rendered == SNAPSHOT.read_text(encoding="utf-8")


class TestWithoutSource:
    def test_the_variant_withholds_text_and_keeps_the_distribution(self):
        spot = hotspot()
        original = payload_of(
            [measurement(spot, "task-clock", 2e9, "ns")],
            address_details=[detail(spot, 0x10, 90.0, [frame("main", line=12)])],
            source_extracts=[
                SourceExtract(
                    hotspot=spot,
                    file="/src/app.c",
                    text="double proprietary_kernel(void);",
                    start_line=12,
                    end_line=12,
                )
            ],
        )
        stripped = report.payload.without_source(original)
        source = stripped["hotspots"][0]["source"]
        assert source["text"] is None
        assert source["reason"] == report.payload.WITHHELD
        assert source["start_line"] == 12
        assert stripped["hotspots"][0]["lines"] == original["hotspots"][0]["lines"]
        assert "proprietary_kernel" not in json.dumps(stripped)

    def test_the_input_payload_is_not_modified(self):
        spot = hotspot()
        original = payload_of(
            [measurement(spot, "task-clock", 2e9, "ns")],
            source_extracts=[
                SourceExtract(hotspot=spot, file="/src/app.c", text="code();")
            ],
        )
        report.payload.without_source(original)
        assert original["hotspots"][0]["source"]["text"] == "code();"


class TestCountingLayer:
    def test_coverage_and_admissions_stand_on_the_sampling_layer(self):
        from nunatak.pivot import Locus, Measurement, Quality

        spot = hotspot()
        sampled = measurement(spot, "task-clock", 1e8, "ns", samples=400)
        aggregates = [
            Measurement(
                hotspot=None,
                locus=Locus(node="n0", rank=rank),
                counter="task-clock",
                value=1e12,
                unit="ns",
                quality=Quality.MEASURED,
            )
            for rank in range(4)
        ]
        with_counting = payload_of([sampled] + aggregates)
        without = payload_of([sampled])
        assert with_counting["coverage"] == without["coverage"]
        assert with_counting["others"] == without["others"]


class TestRanksSection:
    def test_an_mpi_run_carries_its_balance(self):
        spot = hotspot()
        built = payload_of(
            [ranked(spot, "task-clock", 1e9, "ns", rank=0),
             aggregate("task-clock", 2e9, rank=1)]
        )
        section = built["ranks"]
        assert [row["rank"] for row in section["rows"]] == [0, 1]
        assert section["rows"][0]["sampled"] is True
        assert section["rows"][0]["time"]["formula"] == "sum of this rank's samples"
        assert section["rows"][1]["time"]["formula"] == "counted over the whole rank"
        assert section["unsampled"] == [1]
        assert section["imbalance"]["value"] == 2e9 / 1.5e9
        assert section["mpi_fraction"]["value"] is None
        assert section["mpi_fraction"]["reason"] == "mpiP was not preloaded"

    def test_a_single_process_run_has_no_ranks_section(self):
        built = payload_of(
            balanced(hotspot(), flops=1.6e10, bytes_=8.0e9, seconds=0.1)
        )
        assert built["ranks"] is None


class TestInlineView:
    """The transverse view: time by innermost inline frame, all Hotspots
    combined - keyed by (function, file), stable across recompilation."""

    def _frame(self, function, file="/src/kernels.h", declaration_line=3):
        return InlineFrame(
            function=function, file=file, declaration_line=declaration_line
        )

    def test_a_frame_inlined_in_two_hotspots_is_one_row(self):
        a, b = hotspot(), hotspot("other")
        payload = payload_of(
            [
                measurement(a, "task-clock", 3e9, "ns"),
                measurement(b, "task-clock", 1e9, "ns", samples=200),
            ],
            address_details=[
                detail(a, 0x10, 60.0, [self._frame("axpy_element"), frame("main")]),
                detail(b, 0x20, 20.0, [self._frame("axpy_element"), frame("other")]),
                detail(b, 0x28, 20.0, [frame("other")]),
            ],
        )
        rows = payload["inline_view"]
        assert [r["function"] for r in rows] == ["axpy_element", "other"]
        assert rows[0]["share"] == 0.8
        assert rows[0]["sites"] == 2
        assert rows[0]["file"] == "/src/kernels.h"
        assert rows[1]["sites"] == 1

    def test_without_any_inlining_the_view_does_not_exist(self):
        spot = hotspot()
        payload = payload_of(
            [measurement(spot, "task-clock", 2e9, "ns")],
            address_details=[detail(spot, 0x10, 90.0, [frame("main", line=12)])],
        )
        assert payload["inline_view"] is None

    def test_without_a_time_base_the_view_does_not_exist(self):
        spot = hotspot()
        payload = payload_of(
            [measurement(spot, "flops_dp", 3e9, "flop")],
            address_details=[
                detail(spot, 0x10, 30.0,
                       [self._frame("axpy_element"), frame("main")],
                       counter="flops_dp"),
            ],
        )
        assert payload["inline_view"] is None


class TestCallersAndInclusive:
    """The recorded paths consumed: a library leaf names its callers,
    and the inclusive share says how much of the time a function was
    somewhere on the path."""

    def _stack(self, frames, value, counter="task-clock"):
        return Stack(
            locus=Locus(node="n0", thread=1),
            counter=counter,
            frames=tuple(StackFrame(module=m, offset=o, function=f) for m, o, f in frames),
            value=value,
            unit="ns",
            sample_count=int(value / 1e7),
        )

    def test_a_library_leaf_names_its_callers(self):
        leaf = hotspot("dgemm_kernel")
        payload = payload_of(
            [measurement(leaf, "task-clock", 2e9, "ns")],
            stacks=[
                self._stack(
                    [("/app/solver", 0x100, "dgemm_kernel"),
                     ("/app/solver", 0x900, "assemble_matrix")],
                    1.4e9,
                ),
                self._stack(
                    [("/app/solver", 0x110, "dgemm_kernel"),
                     ("/app/solver", 0xA00, "solve_pressure")],
                    0.6e9,
                ),
            ],
        )
        entry = payload["hotspots"][0]
        assert entry["callers"] == [
            {"name": "assemble_matrix", "share": 0.7},
            {"name": "solve_pressure", "share": 0.3},
        ]

    def test_an_unnamed_caller_keeps_its_honest_display(self):
        leaf = hotspot()
        payload = payload_of(
            [measurement(leaf, "task-clock", 2e9, "ns")],
            stacks=[
                self._stack(
                    [("/app/solver", 0x100, "main"),
                     ("/usr/lib/libfoo.so", 0x3A1C, None)],
                    1e9,
                ),
            ],
        )
        assert payload["hotspots"][0]["callers"] == [
            {"name": "libfoo.so+0x3a1c", "share": 1.0}
        ]

    def test_inclusive_counts_a_function_anywhere_on_the_path_once(self):
        # main executes 25% of the time but is on the path always -
        # recursion through helper counts it once per path.
        spot = hotspot()
        helper = hotspot("helper")
        payload = payload_of(
            [
                measurement(spot, "task-clock", 1e9, "ns"),
                measurement(helper, "task-clock", 3e9, "ns", samples=300),
            ],
            stacks=[
                self._stack([("/app/solver", 0x100, "main")], 1e9),
                self._stack(
                    [("/app/solver", 0x200, "helper"),
                     ("/app/solver", 0x120, "main"),
                     ("/app/solver", 0x110, "main")],
                    3e9,
                ),
            ],
        )
        by_name = {h["name"]: h for h in payload["hotspots"]}
        assert by_name["main"]["inclusive"] == 1.0
        assert by_name["helper"]["inclusive"] == 0.75

    def test_without_recorded_paths_the_answer_is_unknown_not_zero(self):
        payload = payload_of([measurement(hotspot(), "task-clock", 2e9, "ns")])
        entry = payload["hotspots"][0]
        assert entry["callers"] == []
        assert entry["inclusive"] is None



class TestLoopFacts:
    """The hot loop's facts in the payload: static, estimated, honest
    about absent bounds."""

    def _run_with_loop(self, **bounds):
        from nunatak.pivot import LoopAnalysis

        spot = hotspot()
        run = run_with([measurement(spot, "task-clock", 2e9, "ns")])
        run.loop_analyses = [
            LoopAnalysis(
                hotspot=spot, start_offset=0x1420, end_offset=0x1437,
                instructions=5, flops_per_iteration=8.0, vector_fp=1,
                scalar_fp=0, vector_width_bits=256, loaded_bytes=64,
                stored_bytes=32, gathers=0, **bounds,
            )
        ]
        return run

    def test_the_facts_are_estimated_with_the_static_reason(self):
        run = self._run_with_loop(
            cycles_ports=1.3, cycles_effective=1.41, scheduling_model="znver2"
        )
        payload = report.build(run, analysis.diagnose(run))
        loop = payload["hotspots"][0]["loop"]
        assert loop["vector_ratio"] == 1.0
        assert abs(loop["l1_intensity"]["value"] - 8 / 96) < 1e-12
        assert loop["l1_intensity"]["quality"] == "estimated"
        assert "cache reuse" in loop["l1_intensity"]["reason"]
        assert loop["cycle_bounds"]["ports"] == 1.3
        assert "znver2" in loop["cycle_bounds"]["reason"]

    def test_absent_bounds_carry_their_reason(self):
        run = self._run_with_loop(
            bounds_reason="LLVM 17 does not know znver4; install LLVM 19 or newer"
        )
        payload = report.build(run, analysis.diagnose(run))
        loop = payload["hotspots"][0]["loop"]
        assert loop["cycle_bounds"] is None
        assert "install LLVM 19" in loop["bounds_reason"]

    def test_without_an_analysis_the_field_is_null(self):
        payload = payload_of([measurement(hotspot(), "task-clock", 2e9, "ns")])
        assert payload["hotspots"][0]["loop"] is None
