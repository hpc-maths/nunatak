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
        group = (events._SETS["zen2"][0],)
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
            .on("perf", exit_code=129)  # record refuses the events, fails fast
            .on("perf", exit_code=1)  # script has no data to read: the witness
            .on("perf", exit_code=0)  # time-only retry
            .on("perf", stdout="lines\n")
            .on("perf", stdout="ids\n")
        )
        exit_code, (degradation,) = PerfAdapter().collect(
            ["./solver"],
            tmp_path / "c",
            executor,
            frequency=997,
            events=(events._SETS["zen2"][0],),
        )
        assert exit_code == 0
        assert degradation.name == "counter-events-rejected"
        first, retry = executor.calls[0], executor.calls[2]
        assert "-e" in first and "-e" not in retry
        assert retry[retry.index("--") + 1 :] == ["./solver"]

    def test_an_application_failure_is_not_mistaken_for_a_rejection(self, tmp_path):
        # perf propagates the application's own failure, and the data
        # file it wrote reads fine: one record, no retry - and a replay,
        # whose disk holds no data file at all, reaches the same verdict
        # from the recorded script invocation.
        executor = (
            ScriptedExecutor()
            .on("perf", exit_code=5)
            .on("perf", stdout="lines\n")
            .on("perf", stdout="ids\n")
        )
        exit_code, degradations = PerfAdapter().collect(
            ["./solver"],
            tmp_path / "c",
            executor,
            frequency=997,
            events=(events._SETS["zen2"][0],),
        )
        assert exit_code == 5
        assert degradations == []
        records = [argv for argv in executor.calls if argv[1] == "record"]
        assert len(records) == 1


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


class TestPassGroups:
    """The multi-pass split: one measurement concern per Pass, a witness
    replicated in each - and `instructions` deliberately kept out of it,
    the generic event being bistable (1x or exactly 16x) on the Zen 2
    corpus machine."""

    def _cpuinfo(self, tmp_path):
        cpuinfo = tmp_path / "cpuinfo"
        cpuinfo.write_text(EPYC_7702)
        return cpuinfo

    def test_the_zen2_set_splits_by_meaning(self, tmp_path):
        groups = events.pass_groups(zen2_machine(), self._cpuinfo(tmp_path))
        assert [label for label, _ in groups] == ["flops", "memory"]
        flops, memory = (entries for _, entries in groups)
        assert [e.canonical for e in flops] == ["flops"]
        assert sorted({e.canonical for e in memory}) == ["dram_bytes"]

    def test_the_groups_and_the_flat_set_are_the_same_events(self, tmp_path):
        cpuinfo = self._cpuinfo(tmp_path)
        grouped = [
            e.event
            for _, entries in events.pass_groups(zen2_machine(), cpuinfo)
            for e in entries
        ]
        assert grouped == [e.event for e in events.sampling_events(zen2_machine(), cpuinfo)]

    def test_the_witness_is_cycles_with_a_fixed_period(self, tmp_path):
        (cycles,) = events.witness(zen2_machine(), self._cpuinfo(tmp_path))
        assert cycles.canonical == "cycles"
        assert cycles.unit == "cycles"
        assert f"period={events.CYCLE_PERIOD}" in cycles.selector

    def test_the_witness_folds_back_through_ingestion(self):
        entry = events.canonical(f"cycles/period={events.CYCLE_PERIOD}/u")
        assert entry is not None and entry.canonical == "cycles"

    def test_an_unknown_microarchitecture_gets_no_passes_and_no_witness(
        self, tmp_path
    ):
        # The cpuinfo is injected: reading the host's would make this
        # test's verdict depend on the machine running the suite.
        cpuinfo = tmp_path / "cpuinfo"
        cpuinfo.write_text("model name\t: Mystery CPU\n")
        unknown = Machine(
            system="Linux", kernel="6.14", architecture="x86_64",
            cpu_model="Mystery CPU", logical_cores=4,
        )
        assert events.pass_groups(unknown, cpuinfo) == ()
        assert events.witness(unknown, cpuinfo) == ()
