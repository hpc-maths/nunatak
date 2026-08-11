"""Counter groups: from vendor events to a measured roofline placement.

The end-to-end tests replay the workload-c-roofline corpus entry - a
complete first Run on the EPYC with calibration, the Zen 2 counter
group, attribution and source extraction - and hold the whole chain,
Diagnostic included, to what real PMUs recorded.
"""

import json
from pathlib import Path

import pytest

from nunatak import analysis
from nunatak.collect import events
from nunatak.collect.perf import PerfAdapter
from nunatak.pivot import Allocation, Machine, Quality
from tests.support import ScriptedExecutor
from tests.test_theory import EPYC_7702

ENTRY = (
    Path(__file__).resolve().parent.parent
    / "corpus"
    / "recordings"
    / "perf"
    / "6.14.11"
    / "linux-x86_64"
    / "workload-c-roofline"
)


def zen2_machine() -> Machine:
    return Machine(
        system="Linux",
        kernel="6.14.0-27-generic",
        architecture="x86_64",
        cpu_model="AMD EPYC 7702 64-Core Processor",
        logical_cores=32,
        allocation=Allocation(visible_cores=32),
    )


class TestRegistry:
    def test_the_corpus_machine_gets_the_zen2_group(self, tmp_path):
        cpuinfo = tmp_path / "cpuinfo"
        cpuinfo.write_text(EPYC_7702)
        group = events.sampling_events(zen2_machine(), cpuinfo)
        assert [entry.canonical for entry in group] == [
            "flops",
            "dram_bytes",
            "dram_bytes",
        ]
        assert all("/period=" in entry.selector for entry in group)

    def test_an_unknown_microarchitecture_gets_no_group(self, tmp_path):
        cpuinfo = tmp_path / "cpuinfo"
        cpuinfo.write_text(EPYC_7702.replace("AuthenticAMD", "CentaurHauls"))
        assert events.sampling_events(zen2_machine(), cpuinfo) == ()

    def test_canonical_strips_period_terms_and_modifiers(self):
        entry = events.canonical(
            "ls_refills_from_sys.ls_mabresp_lcl_dram/period=100003/u"
        )
        assert entry.canonical == "dram_bytes"
        assert entry.scale == 64
        assert entry.quality is Quality.ESTIMATED
        assert "prefetched" in entry.reason
        assert events.canonical("task-clock") is None
        # Local and remote DRAM fills fold onto the same counter.
        remote = events.canonical("ls_refills_from_sys.ls_mabresp_rmt_dram/period=100003/")
        assert remote.canonical == "dram_bytes"


class TestAdapter:
    def test_the_group_rides_along_with_task_clock_as_time_base(self, tmp_path):
        executor = (
            ScriptedExecutor()
            .on("perf", exit_code=0)
            .on("perf", stdout="lines\n")
            .on("perf", stdout="ids\n")
        )
        group = (events._ZEN2[0],)
        PerfAdapter().collect(
            ["./solver"], tmp_path / "c", executor, frequency=997, events=group
        )
        record = executor.calls[0]
        assert record[record.index("-e") + 1] == "task-clock"
        assert any("fp_ret_sse_avx_ops.all/period=" in part for part in record)

    def test_a_rejected_group_retries_time_only_without_rerunning_the_app(
        self, tmp_path
    ):
        executor = (
            ScriptedExecutor()
            .on("perf", exit_code=129)  # record refuses the events, no data file
            .on("perf", exit_code=0)  # time-only retry
            .on("perf", stdout="lines\n")
            .on("perf", stdout="ids\n")
        )
        exit_code, (degradation,) = PerfAdapter().collect(
            ["./solver"],
            tmp_path / "c",
            executor,
            frequency=997,
            events=(events._ZEN2[0],),
        )
        assert exit_code == 0
        assert degradation.name == "counter-events-rejected"
        first, second = executor.calls[0], executor.calls[1]
        assert "-e" in first and "-e" not in second
        assert second[second.index("--") + 1 :] == ["./solver"]


class TestReplayedRoofline:
    """The milestone Run end to end: calibration, counter group, naming,
    and a Diagnostic whose placement is real."""

    @pytest.fixture(autouse=True)
    def in_tmp_cwd(self, tmp_path, monkeypatch):
        (tmp_path / "nunatak.toml").write_text(
            '[tools]\nllvm-symbolizer = "/usr/lib/llvm-19/bin/llvm-symbolizer"\n'
        )
        monkeypatch.chdir(tmp_path)

    def replayed(self, capsys):
        from nunatak.cli import principal
        from nunatak.pivot import read_run

        assert (
            principal(["run", "--replay", str(ENTRY), "--json", "--", "./workload"])
            == 0
        )
        return read_run(json.loads(capsys.readouterr().out)["run"])

    def test_the_canonical_counters_reach_the_pivot(self, capsys):
        run = self.replayed(capsys)
        main = {
            m.counter: m
            for m in run.measurements
            if m.hotspot.display_name == "main"
        }
        assert main["flops"].value == 503 * events.FLOP_PERIOD
        assert main["flops"].quality is Quality.MEASURED
        assert main["flops"].unit == "flop"
        assert main["dram_bytes"].unit == "byte"
        assert main["dram_bytes"].value % events.CACHELINE_BYTES == 0
        assert main["dram_bytes"].quality is Quality.ESTIMATED
        assert "prefetched" in main["dram_bytes"].reason
        assert main["task-clock"].unit == "ns"

    def test_the_diagnostic_places_the_hotspot_on_the_roofline(self, capsys):
        run = self.replayed(capsys)
        diagnostic = analysis.diagnose(run)[0]
        assert diagnostic.hotspot.display_name == "main"
        # 600 sweeps over 2^21 doubles, 2 FLOPs each: the sampled total
        # sits within a period of the arithmetic truth.
        assert diagnostic.share.value > 0.9
        assert 2.4e9 < 503 * events.FLOP_PERIOD < 2.6e9
        assert diagnostic.dram_intensity.value == pytest.approx(1.209, rel=0.01)
        assert diagnostic.dram_intensity.quality is Quality.ESTIMATED
        assert "prefetched" in diagnostic.dram_intensity.reason
        assert diagnostic.attainable.value is not None
        assert diagnostic.envelope_fraction.value < 0.05
        assert diagnostic.classification == "latency-bound"
