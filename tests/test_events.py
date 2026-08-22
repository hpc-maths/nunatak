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
        group = (events._TABLE["zen2"].sampling_set[0],)
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
            events=(events._TABLE["zen2"].sampling_set[0],),
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
            events=(events._TABLE["zen2"].sampling_set[0],),
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
    replicated in each - and `instructions` deliberately kept out of the
    Zen witness, the generic event being bistable (1x or exactly 16x) on
    the Zen 2 corpus machine's general counters. Intel's fixed counter
    is a different animal, and its own table says so."""

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

    def test_the_witness_is_the_retired_flop_event(self, tmp_path):
        (witness,) = events.witness(zen2_machine(), self._cpuinfo(tmp_path))
        assert witness.canonical == "flops"
        assert f"period={events.FLOP_PERIOD}" in witness.selector

    def test_the_witness_folds_back_through_ingestion(self):
        entry = events.canonical(
            f"fp_ret_sse_avx_ops.all/period={events.FLOP_PERIOD}/u"
        )
        assert entry is not None and entry.canonical == "flops"

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


def intel_machine(model: int, name: str) -> Machine:
    return Machine(
        system="Linux",
        kernel="6.14.0",
        architecture="x86_64",
        cpu_model=name,
        logical_cores=32,
        allocation=Allocation(visible_cores=32),
    )


def intel_cpuinfo(tmp_path, model: int):
    cpuinfo = tmp_path / "cpuinfo"
    cpuinfo.write_text(
        "processor\t: 0\n"
        "vendor_id\t: GenuineIntel\n"
        "cpu family\t: 6\n"
        f"model\t\t: {model}\n"
        "model name\t: Intel(R) Xeon(R)\n"
    )
    return cpuinfo


class TestIntelRegistry:
    """The Intel tables: split precisions, the L3-miss DRAM proxy, and
    single-execution sets bounded by what one SMT thread's four or eight
    general counters can hold without multiplexing."""

    def test_skylake_sp_single_execution_holds_the_complete_dp_group_only(
        self, tmp_path
    ):
        group = events.sampling_events(
            intel_machine(0x55, "Xeon Gold"), intel_cpuinfo(tmp_path, 0x55)
        )
        assert [e.canonical for e in group] == ["flops_dp"] * 4
        assert [e.scale for e in group] == [1, 2, 4, 8]

    def test_icelake_and_later_fit_memory_alongside(self, tmp_path):
        for model in (0x6A, 0x8F, 0xCF, 0xAD):
            group = events.sampling_events(
                intel_machine(model, "Xeon"), intel_cpuinfo(tmp_path, model)
            )
            assert [e.canonical for e in group] == ["flops_dp"] * 4 + ["dram_bytes"]

    def test_skylake_client_has_no_512_bit_and_fits_both_groups(self, tmp_path):
        group = events.sampling_events(
            intel_machine(0x5E, "Core i7"), intel_cpuinfo(tmp_path, 0x5E)
        )
        assert [e.canonical for e in group] == ["flops_dp"] * 3 + ["dram_bytes"]
        assert not any("512b" in e.event for e in group)

    def test_haswell_retired_its_flop_counters_and_attributes_memory_only(
        self, tmp_path
    ):
        group = events.sampling_events(
            intel_machine(0x3F, "Xeon E5 v3"), intel_cpuinfo(tmp_path, 0x3F)
        )
        assert [e.canonical for e in group] == ["dram_bytes"]
        assert "mem_load_uops_retired" in group[0].event

    def test_hybrid_client_parts_get_no_set_at_all(self, tmp_path):
        # Alder/Raptor Lake E-cores expose no FLOP event: a set counting
        # on half the cores would undercount silently under `measured`.
        assert (
            events.sampling_events(
                intel_machine(0x97, "Core i9"), intel_cpuinfo(tmp_path, 0x97)
            )
            == ()
        )

    def test_the_lane_scales_make_the_event_counts_flops(self):
        scalar = events.canonical(
            f"fp_arith_inst_retired.scalar_double/period={events.FLOP_PERIOD}/u"
        )
        wide_dp = events.canonical(
            f"fp_arith_inst_retired.512b_packed_double/period={events.FLOP_PERIOD}/"
        )
        wide_sp = events.canonical(
            f"fp_arith_inst_retired.512b_packed_single/period={events.FLOP_PERIOD}/"
        )
        assert (scalar.canonical, scalar.scale) == ("flops_dp", 1)
        assert (wide_dp.canonical, wide_dp.scale) == ("flops_dp", 8)
        assert (wide_sp.canonical, wide_sp.scale) == ("flops_sp", 16)
        assert all(
            e.quality is Quality.MEASURED for e in (scalar, wide_dp, wide_sp)
        )

    def test_the_dram_proxy_is_estimated_and_says_what_it_misses(self):
        proxy = events.canonical(
            f"mem_load_retired.l3_miss/period={events.FILL_PERIOD}/u"
        )
        assert proxy.canonical == "dram_bytes"
        assert proxy.scale == events.CACHELINE_BYTES
        assert proxy.quality is Quality.ESTIMATED
        assert "prefetched" in proxy.reason and "stores" in proxy.reason


class TestIntelPasses:
    def test_the_passes_split_by_meaning_with_single_precision_arriving(
        self, tmp_path
    ):
        groups = events.pass_groups(
            intel_machine(0x55, "Xeon Gold"), intel_cpuinfo(tmp_path, 0x55)
        )
        assert [label for label, _ in groups] == ["flops_dp", "flops_sp", "memory"]
        by_label = dict(groups)
        assert [e.scale for e in by_label["flops_sp"]] == [1, 4, 8, 16]

    def test_the_single_execution_set_is_whole_groups_of_the_pass_split(
        self, tmp_path
    ):
        cpuinfo = intel_cpuinfo(tmp_path, 0x6A)
        machine = intel_machine(0x6A, "Xeon")
        by_label = dict(events.pass_groups(machine, cpuinfo))
        single = events.sampling_events(machine, cpuinfo)
        assert list(single) == [*by_label["flops_dp"], *by_label["memory"]]

    def test_the_witness_is_retired_instructions_on_the_fixed_counter(
        self, tmp_path
    ):
        (witness,) = events.witness(
            intel_machine(0x55, "Xeon Gold"), intel_cpuinfo(tmp_path, 0x55)
        )
        assert witness.canonical == "instructions"
        assert f"instructions/period={events.INSTRUCTION_PERIOD}" in witness.selector

    def test_the_witness_folds_back_through_ingestion(self):
        entry = events.canonical(
            f"instructions/period={events.INSTRUCTION_PERIOD}/u"
        )
        assert entry is not None and entry.canonical == "instructions"


def neoverse_machine(name: str) -> Machine:
    return Machine(
        system="Linux",
        kernel="6.14.0",
        architecture="aarch64",
        cpu_model=name,
        logical_cores=64,
        allocation=Allocation(visible_cores=64),
    )


def neoverse_cpuinfo(tmp_path, part: int):
    cpuinfo = tmp_path / "cpuinfo"
    cpuinfo.write_text(
        "processor\t: 0\n"
        "BogoMIPS\t: 243.75\n"
        "CPU implementer\t: 0x41\n"
        "CPU architecture: 8\n"
        f"CPU part\t: {part:#x}\n"
    )
    return cpuinfo


class TestNeoverseRegistry:
    """The Neoverse tables: the speculative SVE/fixed FLOP pair scaled
    by the core's hardware vector length, last-level read misses as the
    DRAM proxy, and six programmable counters - both groups always fit
    the single execution."""

    def test_v1_scales_sve_operations_by_its_256_bit_vectors(self, tmp_path):
        group = events.sampling_events(
            neoverse_machine("Graviton 3"), neoverse_cpuinfo(tmp_path, 0xD40)
        )
        assert [e.canonical for e in group] == ["flops", "flops", "dram_bytes"]
        by_event = {e.event.split("/")[0]: e for e in group}
        assert by_event["fp_scale_ops_spec"].scale == 2.0
        assert by_event["fp_fixed_ops_spec"].scale == 1.0

    def test_v2_and_n2_vectors_are_128_bit_and_scale_to_one(self, tmp_path):
        for part in (0xD4F, 0xD49):
            group = events.sampling_events(
                neoverse_machine("Neoverse"), neoverse_cpuinfo(tmp_path, part)
            )
            by_event = {e.event.split("/")[0]: e for e in group}
            assert by_event["fp_scale_ops_spec"].scale == 1.0

    def test_the_flop_counts_are_speculative_hence_estimated(self, tmp_path):
        group = events.sampling_events(
            neoverse_machine("Graviton 3"), neoverse_cpuinfo(tmp_path, 0xD40)
        )
        flops = [e for e in group if e.canonical == "flops"]
        assert all(e.quality is Quality.ESTIMATED for e in flops)
        assert all("speculatively" in e.reason for e in flops)

    def test_n1_exposes_no_flop_event_and_attributes_memory_only(self, tmp_path):
        group = events.sampling_events(
            neoverse_machine("Graviton 2"), neoverse_cpuinfo(tmp_path, 0xD0C)
        )
        assert [e.canonical for e in group] == ["dram_bytes"]
        assert "ll_cache_miss_rd" in group[0].event

    def test_the_dram_proxy_counts_reads_only_and_says_so(self):
        proxy = events.canonical(
            f"ll_cache_miss_rd/period={events.FILL_PERIOD}/u"
        )
        assert proxy.canonical == "dram_bytes"
        assert proxy.scale == events.CACHELINE_BYTES
        assert proxy.quality is Quality.ESTIMATED
        assert "writes" in proxy.reason

    def test_the_witness_is_retired_instructions(self, tmp_path):
        (witness,) = events.witness(
            neoverse_machine("Graviton 3"), neoverse_cpuinfo(tmp_path, 0xD40)
        )
        assert witness.canonical == "instructions"

    def test_the_sve_pair_folds_back_through_ingestion(self):
        scale = events.canonical(
            f"fp_scale_ops_spec/period={events.FLOP_PERIOD}/u"
        )
        fixed = events.canonical(
            f"fp_fixed_ops_spec/period={events.FLOP_PERIOD}/"
        )
        assert scale.canonical == fixed.canonical == "flops"
