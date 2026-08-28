"""Calibration kernel driver, replayed from a corpus entry recorded on
real hardware (AMD EPYC 7702, 32 allocated cores, gcc, AVX2 build).

The format fixtures are verbatim kernel output from that machine; the
pollution-threshold tests feed the parser controlled variations of that
format, because the thresholds are ours, not the tool's.
"""

import json
from pathlib import Path

import pytest

from nunatak import corpus
from nunatak.calibration import kernel
from nunatak.config import Config
from nunatak.pivot import Allocation, Ceiling, Machine, Quality
from tests.support import ScriptedExecutor

ENTRY = (
    Path(__file__).resolve().parent.parent
    / "corpus"
    / "recordings"
    / "calibration"
    / "v1"
    / "linux-x86_64"
    / "epyc-7702"
)

FMA_DP = """\
kernel fma_dp
isa avx2
threads 32
load 4.00
rep 0 3.349368e+11
rep 1 3.347366e+11
rep 2 3.355571e+11
"""

CC_VERSION = "cc (Ubuntu 14.2.0-19ubuntu2) 14.2.0\n"


def runner_machine() -> Machine:
    return Machine(
        system="Linux",
        kernel="6.14.0-27-generic",
        architecture="x86_64",
        cpu_model="AMD EPYC 7702 64-Core Processor",
        logical_cores=32,
        allocation=Allocation(visible_cores=32, affinity_mask=tuple(range(32))),
    )


def executor_with(*kernel_outputs, compile_exit=0):
    executor = ScriptedExecutor().on("cc", stdout=CC_VERSION)
    executor.on("cc", exit_code=compile_exit)
    for output in kernel_outputs:
        executor.on("kernel", stdout=output)
    return executor


class TestParse:
    def test_the_recorded_output_parses_field_by_field(self):
        run = kernel.parse(FMA_DP)
        assert run.kernel == "fma_dp"
        assert run.isa == "avx2"
        assert run.threads == 32
        assert run.load == 4.0
        assert run.rates == (3.349368e11, 3.347366e11, 3.355571e11)

    def test_a_negative_load_means_unknown_not_a_value(self):
        run = kernel.parse("kernel triad\nload -1.00\nrep 0 1e10\n")
        assert run.load is None

    def test_foreign_output_is_not_mistaken_for_a_kernel(self):
        assert kernel.parse("Segmentation fault\n") is None


class TestCalibrate:
    def test_a_ceiling_is_the_maximum_of_its_repetitions(self, tmp_path):
        executor = executor_with(FMA_DP)
        (ceiling,) = kernel.calibrate(
            executor, runner_machine(), Config(), directory=tmp_path
        )
        assert ceiling.value == 3.355571e11
        assert ceiling.quality is Quality.MEASURED
        assert ceiling.reason is None

    def test_ceilings_come_in_priority_order(self, tmp_path):
        outputs = [
            FMA_DP.replace("fma_dp", name) for name in ("triad", "fma_dp", "fma_sp")
        ]
        executor = executor_with(*outputs)
        names = [
            c.name
            for c in kernel.calibrate(
                executor, runner_machine(), Config(), directory=tmp_path
            )
        ]
        assert names == ["dram_bandwidth", "flops_dp", "flops_sp"]

    def test_the_budget_cuts_from_the_tail(self, tmp_path):
        ticks = iter([0.0, 1.0, 100.0, 100.0])
        executor = executor_with(FMA_DP.replace("fma_dp", "triad"))
        ceilings = kernel.calibrate(
            executor,
            runner_machine(),
            Config(),
            directory=tmp_path,
            clock=lambda: next(ticks),
        )
        assert [c.name for c in ceilings] == ["dram_bandwidth"]

    def test_without_a_compiler_there_is_no_measured_ceiling(self, tmp_path):
        executor = ScriptedExecutor()
        for _ in range(3):
            executor.on("cc", exit_code=127).on("gcc", exit_code=127).on(
                "clang", exit_code=127
            )
        assert (
            kernel.calibrate(executor, runner_machine(), Config(), directory=tmp_path)
            == ()
        )

    def test_a_failing_build_falls_back_to_mcpu_native(self, tmp_path):
        executor = (
            ScriptedExecutor()
            .on("cc", stdout=CC_VERSION)
            .on("cc", stderr="unknown option -march=native", exit_code=1)
            .on("cc", exit_code=0)
            .on("kernel", stdout=FMA_DP.replace("fma_dp", "triad"))
        )
        kernel.calibrate(executor, runner_machine(), Config(), directory=tmp_path)
        flags = [argv[2] for argv in executor.calls if argv[0] == "cc" and len(argv) > 2]
        assert flags == ["-march=native", "-mcpu=native"]

    def test_an_existing_binary_is_reused_not_rebuilt(self, tmp_path):
        binary = tmp_path / "kernel" / "v1" / "kernel"
        binary.parent.mkdir(parents=True)
        binary.write_bytes(b"\x7fELF")
        executor = (
            ScriptedExecutor()
            .on("cc", stdout=CC_VERSION)
            .on("kernel", stdout=FMA_DP.replace("fma_dp", "triad"))
        )
        kernel.calibrate(executor, runner_machine(), Config(), directory=tmp_path)
        assert ["cc", "--version"] in executor.calls
        assert not any("-O3" in argv for argv in executor.calls)


class TestPollution:
    def polluted(self, output, tmp_path, theoretical=None):
        executor = executor_with(output)
        ceilings = kernel.calibrate(
            executor,
            runner_machine(),
            Config(),
            directory=tmp_path,
            theoretical=theoretical,
        )
        return ceilings[0]

    def test_dispersed_repetitions_downgrade_with_the_reason(self, tmp_path):
        dispersed = FMA_DP.replace("rep 1 3.347366e+11", "rep 1 2.000000e+11")
        ceiling = self.polluted(dispersed, tmp_path)
        assert ceiling.quality is Quality.ESTIMATED
        assert "disperse" in ceiling.reason
        assert ceiling.value == 3.355571e11

    def test_concurrent_load_downgrades_with_the_reason(self, tmp_path):
        loaded = FMA_DP.replace("load 4.00", "load 31.00")
        ceiling = self.polluted(loaded, tmp_path)
        assert ceiling.quality is Quality.ESTIMATED
        assert "concurrent load" in ceiling.reason

    def test_a_scalar_build_never_passes_for_a_peak(self, tmp_path):
        scalar = FMA_DP.replace("isa avx2", "isa scalar")
        ceiling = self.polluted(scalar, tmp_path)
        assert ceiling.quality is Quality.ESTIMATED
        assert "without SIMD" in ceiling.reason

    def test_a_scalar_triad_stays_measured_bandwidth_needs_no_simd(self, tmp_path):
        scalar = FMA_DP.replace("isa avx2", "isa scalar").replace(
            "kernel fma_dp", "kernel triad"
        )
        assert self.polluted(scalar, tmp_path).quality is Quality.MEASURED

    def test_far_above_theory_downgrades_with_the_reason(self, tmp_path):
        ceiling = self.polluted(
            FMA_DP, tmp_path, theoretical={"dram_bandwidth": 1.0e11}
        )
        assert ceiling.quality is Quality.ESTIMATED
        assert "theoretical peak" in ceiling.reason

    def test_a_boost_induced_excess_is_not_an_anomaly(self, tmp_path):
        # Measured 15% above an observed-frequency estimate: expected.
        ceiling = self.polluted(
            FMA_DP, tmp_path, theoretical={"dram_bandwidth": 3.0e11}
        )
        assert ceiling.quality is Quality.MEASURED

    def test_load_is_judged_against_the_kernel_reported_threads(self, tmp_path):
        # The kernel ran with 32 threads under a load of 4.00 - calm. A
        # replaying machine with 2 visible cores must not turn that
        # recorded calm into pollution: the measurement is judged in the
        # context it was recorded in, never the replaying machine's.
        two_cores = Machine(
            system="Linux",
            kernel="6.8.0",
            architecture="x86_64",
            cpu_model="whatever the CI runner is",
            logical_cores=2,
            allocation=Allocation(visible_cores=2),
        )
        executor = executor_with(FMA_DP)
        (ceiling,) = kernel.calibrate(
            executor, two_cores, Config(), directory=tmp_path
        )
        assert ceiling.quality is Quality.MEASURED

    def test_the_anomaly_reference_follows_the_kernel_threads(self, tmp_path):
        # Same principle for the theoretical reference: it arrives scaled
        # to the caller's 2-core allocation, but the recorded kernel ran
        # 32 threads - a rate legitimate for 32 threads is not an anomaly
        # on the replaying machine.
        two_cores = Machine(
            system="Linux",
            kernel="6.8.0",
            architecture="x86_64",
            cpu_model="whatever the CI runner is",
            logical_cores=2,
            allocation=Allocation(visible_cores=2),
        )
        executor = executor_with(FMA_DP)
        (ceiling,) = kernel.calibrate(
            executor,
            two_cores,
            Config(),
            directory=tmp_path,
            theoretical={"dram_bandwidth": 2.1e10},
        )
        assert ceiling.quality is Quality.MEASURED


class TestReplayedCalibration:
    """The recorded EPYC entry end to end: probe, build, three kernels."""

    def test_the_recorded_calibration_replays_into_measured_ceilings(self, tmp_path):
        executor = corpus.ReplayExecutor(ENTRY)
        ceilings = kernel.calibrate(
            executor, runner_machine(), Config(), directory=tmp_path
        )
        assert [c.name for c in ceilings] == [
            "dram_bandwidth",
            "flops_dp",
            "flops_sp",
        ]
        assert all(c.quality is Quality.MEASURED for c in ceilings)
        dram, dp, sp = ceilings
        assert dram.value == 1.443587e11
        assert dram.unit == "byte/s"
        assert dp.value == 1.171278e12
        assert sp.value == 2.341047e12

    def test_the_replayed_maxima_match_the_recorded_repetitions(self, tmp_path):
        rates = {}
        for record in sorted((ENTRY / "invocations").glob("*.json")):
            argv = json.loads(record.read_text())["argv"]
            if "kernel" in argv[0]:
                run = kernel.parse(record.with_suffix(".stdout").read_text())
                rates[run.kernel] = max(run.rates)
        executor = corpus.ReplayExecutor(ENTRY)
        ceilings = kernel.calibrate(
            executor, runner_machine(), Config(), directory=tmp_path
        )
        assert {c.value for c in ceilings} == set(rates.values())


class TestMergedCeilings:
    def test_measured_wins_and_theory_fills_the_rest(self):
        from nunatak.calibration import merged_ceilings

        measured = (
            Ceiling(
                name="dram_bandwidth",
                value=1.0e11,
                unit="byte/s",
                quality=Quality.MEASURED,
            ),
        )
        theoretical = (
            Ceiling(
                name="dram_bandwidth",
                value=9.9e99,
                unit="byte/s",
                quality=Quality.ESTIMATED,
                reason="theory",
            ),
            Ceiling(
                name="flops_dp",
                value=1.0e12,
                unit="flop/s",
                quality=Quality.ESTIMATED,
                reason="theory",
            ),
        )
        merged = merged_ceilings(measured, theoretical)
        assert [(c.name, c.quality) for c in merged] == [
            ("dram_bandwidth", Quality.MEASURED),
            ("flops_dp", Quality.ESTIMATED),
        ]


class TestCalibrateVerb:
    """`nunatak calibrate` against the recorded EPYC entry: measure,
    cache, short-circuit, --force."""

    def test_the_replayed_calibration_caches_then_short_circuits(self, capsys):
        from nunatak.cli import principal

        assert principal(["calibrate", "--replay", str(ENTRY), "--json"]) == 0
        report = json.loads(capsys.readouterr().out)
        assert report["cached"] is False
        values = {c["name"]: c["value"] for c in report["ceilings"]}
        assert values["dram_bandwidth"] == 1.443587e11
        assert values["flops_dp"] == 1.171278e12
        assert values["flops_sp"] == 2.341047e12

        # Same Machine, fresh replay: the cached profile answers and no
        # recording is consumed.
        assert principal(["calibrate", "--replay", str(ENTRY), "--json"]) == 0
        second = json.loads(capsys.readouterr().out)
        assert second["cached"] is True
        assert {c["name"]: c["value"] for c in second["ceilings"]} == values

    def test_force_takes_back_control_over_the_cache(self, capsys):
        from nunatak.cli import principal

        assert principal(["calibrate", "--replay", str(ENTRY), "--json"]) == 0
        capsys.readouterr()
        assert principal(["calibrate", "--replay", str(ENTRY), "--force", "--json"]) == 0
        report = json.loads(capsys.readouterr().out)
        assert report["cached"] is False


FULL_ENTRY = (
    Path(__file__).resolve().parent.parent
    / "corpus"
    / "recordings"
    / "perf"
    / "6.14.11"
    / "linux-x86_64"
    / "workload-c-calibrated"
)


class TestFirstRunCalibration:
    """The recorded first Run on an unknown Machine: calibration before
    the launch, then the usual perf pipeline, all in one entry."""

    @pytest.fixture(autouse=True)
    def in_tmp_cwd(self, tmp_path, monkeypatch):
        from tests.support import WORKLOAD_C

        (tmp_path / "nunatak.toml").write_text(
            '[tools]\nllvm-symbolizer = "/usr/lib/llvm-19/bin/llvm-symbolizer"\n'
        )
        (tmp_path / "workload.c").write_text(WORKLOAD_C)
        monkeypatch.chdir(tmp_path)

    def recorded_maxima(self):
        maxima = {}
        for record in sorted((FULL_ENTRY / "invocations").glob("*.json")):
            argv = json.loads(record.read_text())["argv"]
            if Path(argv[0]).name == "kernel":
                run = kernel.parse(record.with_suffix(".stdout").read_text())
                maxima[run.kernel] = max(run.rates)
        return maxima

    def test_the_first_run_embeds_the_measured_ceilings(self, capsys):
        from nunatak.cli import principal
        from nunatak.pivot import read_run

        assert (
            principal(["run", "--replay", str(FULL_ENTRY), "--json", "--", "./workload"])
            == 0
        )
        summary = json.loads(capsys.readouterr().out)
        assert summary["degradations"] == []
        assert summary["resolved_hotspots"] >= 1

        run = read_run(summary["run"])
        by_name = {c.name: c for c in run.machine.ceilings}
        maxima = self.recorded_maxima()
        assert by_name["dram_bandwidth"].value == maxima["triad"]
        assert by_name["flops_dp"].value == maxima["fma_dp"]
        assert by_name["flops_sp"].value == maxima["fma_sp"]

    def test_the_second_run_reuses_the_cached_profile(self, capsys):
        from nunatak.cli import principal
        from nunatak.pivot import read_run

        assert (
            principal(["run", "--replay", str(FULL_ENTRY), "--json", "--", "./workload"])
            == 0
        )
        first = json.loads(capsys.readouterr().out)
        assert (
            principal(["run", "--replay", str(FULL_ENTRY), "--json", "--", "./workload"])
            == 0
        )
        second = json.loads(capsys.readouterr().out)
        maxima = set(self.recorded_maxima().values())
        for summary in (first, second):
            ceilings = read_run(summary["run"]).machine.ceilings
            assert maxima <= {c.value for c in ceilings}

    def test_no_calibrate_leaves_only_theoretical_ceilings(self, capsys):
        from nunatak.cli import principal
        from nunatak.pivot import read_run

        assert (
            principal(
                [
                    "run",
                    "--replay",
                    str(FULL_ENTRY),
                    "--no-calibrate",
                    "--json",
                    "--",
                    "./workload",
                ]
            )
            == 0
        )
        summary = json.loads(capsys.readouterr().out)
        run = read_run(summary["run"])
        assert all(
            c.quality is not Quality.MEASURED for c in run.machine.ceilings
        )


DARWIN_ENTRY = (
    Path(__file__).resolve().parent.parent
    / "corpus"
    / "recordings"
    / "calibration"
    / "v1"
    / "darwin-arm64"
    / "apple-m5-max"
)


def laptop_machine() -> Machine:
    return Machine(
        system="Darwin",
        kernel="25.5.0",
        architecture="arm64",
        cpu_model="Apple M5 Max",
        logical_cores=18,
        allocation=Allocation(visible_cores=18),
    )


class TestReplayedDarwinCalibration:
    """The recorded Apple M5 Max entry end to end: the same driver, the
    same kernel source, Apple clang and NEON - the microbenchmark path
    the spec promises on every platform.

    Two facts of the platform travel with the recording: Xcode 16's
    clang accepts `-march=native` (one build attempt, not two), and
    the load signal now reaches macOS through getloadavg(3) - the
    pollution channel the /proc-less platforms were missing."""

    def test_the_recorded_calibration_replays_into_measured_ceilings(
        self, tmp_path
    ):
        executor = corpus.ReplayExecutor(DARWIN_ENTRY)
        ceilings = kernel.calibrate(
            executor, laptop_machine(), Config(), directory=tmp_path
        )
        assert [c.name for c in ceilings] == [
            "dram_bandwidth",
            "flops_dp",
            "flops_sp",
        ]
        assert all(c.quality is Quality.MEASURED for c in ceilings)
        dram, dp, sp = ceilings
        assert dram.value == 3.655209e11
        assert dp.value == 6.064984e11
        assert sp.value == 1.264527e12

    def test_the_kernel_self_reports_a_neon_build_with_a_load(self):
        for record in sorted((DARWIN_ENTRY / "invocations").glob("*.json")):
            argv = json.loads(record.read_text())["argv"]
            if "kernel" in argv[0]:
                run = kernel.parse(record.with_suffix(".stdout").read_text())
                assert run.isa == "neon"
                assert run.threads == 18
                assert run.load is not None and run.load > 0
