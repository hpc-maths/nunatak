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
from nunatak.pivot import AddressDetail, InlineFrame, SourceExtract
from tests.test_analysis import hotspot, measurement, run_with

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
        from tests.support import WORKLOAD_C

        from nunatak.cli import principal
        from nunatak.pivot import read_run

        (tmp_path / "nunatak.toml").write_text(
            '[tools]\nllvm-symbolizer = "/usr/lib/llvm-19/bin/llvm-symbolizer"\n'
        )
        (tmp_path / "workload.c").write_text(WORKLOAD_C)
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
