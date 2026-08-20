"""The multi-pass loop: explicit, exact, honest about what it skips.

The replayed entry is a complete --multi-pass Run recorded on the EPYC:
two passes (flops, memory), the witness in each, one Run.
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from nunatak import analysis, machine
from nunatak.cli import principal
from nunatak.cli.run import _pass_plan
from nunatak.collect import events
from nunatak.console import Console
from nunatak.pivot import Quality, read_run
from tests.support import ScriptedExecutor
from tests.test_events import zen2_machine
from tests.test_theory import EPYC_7702

ENTRY = (
    Path(__file__).resolve().parent.parent
    / "corpus"
    / "recordings"
    / "perf"
    / "6.14.11"
    / "linux-x86_64"
    / "workload-c-multipass"
)


class TestPassPlan:
    def test_without_the_flag_one_anonymous_pass(self, monkeypatch):
        # The anonymous pass keeps the live sampling_events path: the
        # detection itself is patched, /proc/cpuinfo being bound as a
        # default argument.
        from nunatak.calibration.theory import x86_microarchitecture

        monkeypatch.setattr(
            "nunatak.calibration.theory.detect",
            lambda machine, cpuinfo=None: x86_microarchitecture(EPYC_7702),
        )
        plan = _pass_plan(
            SimpleNamespace(multi_pass=False), zen2_machine(),
            ScriptedExecutor(), Console(),
        )
        assert len(plan) == 1
        label, entries = plan[0]
        assert label is None
        assert [e.canonical for e in entries] == ["flops", "dram_bytes", "dram_bytes"]

    def test_the_flag_keys_the_passes_on_the_executors_identification(self):
        # The executor's cpuinfo decides - never the live host: a replay
        # must build the same passes the recording ran.
        plan = _pass_plan(
            SimpleNamespace(multi_pass=True), zen2_machine(),
            ScriptedExecutor(cpuinfo=EPYC_7702), Console(),
        )
        assert [label for label, _ in plan] == ["flops", "memory"]
        for _, entries in plan:
            assert entries[0].canonical == "flops"
        # The witness IS the flops pass's own event: never asked twice.
        flops_pass = plan[0][1]
        assert len(flops_pass) == 1

    def test_an_unknown_identification_has_nothing_to_split(self):
        unknown = ScriptedExecutor(cpuinfo="model name\t: Mystery CPU\n")
        assert _pass_plan(
            SimpleNamespace(multi_pass=True), zen2_machine(), unknown, Console()
        ) is None
        assert _pass_plan(
            SimpleNamespace(multi_pass=True), zen2_machine(),
            ScriptedExecutor(), Console(),
        ) is None


class TestSampledView:
    def test_a_replicated_counter_only_counts_its_reference_pass(self):
        from tests.test_analysis import hotspot, measurement, run_with
        import dataclasses

        spot = hotspot()
        base = measurement(spot, "task-clock", 2e9, "ns")
        run = run_with(
            [
                base,
                dataclasses.replace(base, pass_index=1),
                dataclasses.replace(
                    base, counter="flops", unit="flop", value=3e9, pass_index=1
                ),
            ]
        )
        view = analysis.sampled_view(run)
        assert [(m.counter, m.pass_index) for m in view] == [
            ("task-clock", 0),
            ("flops", 1),
        ]

    def test_a_single_pass_run_comes_back_unchanged(self):
        from tests.test_analysis import hotspot, measurement, run_with

        run = run_with([measurement(hotspot(), "task-clock", 2e9, "ns")])
        assert analysis.sampled_view(run) == run.measurements


class TestReplayedMultiPass:
    """The recorded --multi-pass Run, replayed without perf installed."""

    @pytest.fixture(autouse=True)
    def in_tmp_cwd(self, tmp_path, monkeypatch):
        from tests.support import WORKLOAD_C

        (tmp_path / "nunatak.toml").write_text(
            '[tools]\nllvm-symbolizer = "/usr/lib/llvm-19/bin/llvm-symbolizer"\n'
        )
        (tmp_path / "workload.c").write_text(WORKLOAD_C)
        monkeypatch.chdir(tmp_path)

    def _replayed(self, capsys):
        assert (
            principal(
                ["run", "--multi-pass", "--replay", str(ENTRY), "--json",
                 "--no-calibrate", "--", "./workload"]
            )
            == 0
        )
        summary = json.loads(capsys.readouterr().out)
        return summary, read_run(summary["run"])

    def test_one_run_two_passes_each_measurement_remembers_its_pass(self, capsys):
        summary, run = self._replayed(capsys)
        assert [p.index for p in run.passes] == [0, 1]
        assert all(p.exit_code == 0 for p in run.passes)
        indices = {m.pass_index for m in run.measurements}
        assert indices == {0, 1}

    def test_the_witness_rides_every_pass(self, capsys):
        _, run = self._replayed(capsys)
        witness_passes = {
            m.pass_index for m in run.measurements if m.counter == "flops"
        }
        assert witness_passes == {0, 1}

    def test_exclusive_counters_live_in_their_own_pass(self, capsys):
        _, run = self._replayed(capsys)
        by_counter = {}
        for m in run.measurements:
            if m.counter == "dram_bytes":
                by_counter.setdefault(m.counter, set()).add(m.pass_index)
        assert by_counter.get("dram_bytes", {1}) == {1}

    def test_the_view_keeps_seconds_single_and_rates_whole(self, capsys):
        _, run = self._replayed(capsys)
        view = analysis.sampled_view(run)
        clocked = [m for m in view if m.counter == "task-clock"]
        assert {m.pass_index for m in clocked} == {0}
        # The raw pivot holds both passes' clocks; the view halves the
        # seconds back to one execution's worth.
        raw = sum(
            m.value for m in run.measurements if m.counter == "task-clock"
        )
        assert sum(m.value for m in clocked) < raw

    def test_no_multipass_noise_in_the_degradations(self, capsys):
        summary, _ = self._replayed(capsys)
        names = {d["name"] for d in summary["degradations"]}
        assert "multi-pass-unavailable" not in names
        assert "passes-skipped" not in names
        assert "perf-script-unparsed" not in names


class TestWitnessVerdict:
    def _two_pass_run(self, cycles_by_pass, extra=None):
        import dataclasses

        from tests.test_analysis import hotspot, measurement, run_with

        spot = hotspot()
        base = measurement(spot, "task-clock", 2e9, "ns")
        rows = [base, dataclasses.replace(base, pass_index=1)]
        for index, value in enumerate(cycles_by_pass):
            rows.append(
                dataclasses.replace(
                    base, counter="flops", unit="flop",
                    value=value, pass_index=index,
                )
            )
        rows += extra or []
        return run_with(rows)

    def test_agreeing_passes_are_consistent(self):
        run = self._two_pass_run([1.00e9, 1.02e9])
        verdict = analysis.witness_verdict(run)
        assert verdict.consistent
        assert verdict.counter == "flops"
        assert verdict.spread == pytest.approx(0.0198, abs=1e-3)

    def test_diverging_passes_are_named_with_their_numbers(self):
        run = self._two_pass_run([1.0e9, 1.3e9])
        verdict = analysis.witness_verdict(run)
        assert not verdict.consistent
        assert verdict.totals == ((0, 1.0e9), (1, 1.3e9))

    def test_the_threshold_travels_with_the_run(self):
        run = self._two_pass_run([1.0e9, 1.06e9])
        assert not analysis.witness_verdict(run).consistent  # ~5.8% > 5%
        run.provenance.effective_configuration["passes.witness"] = 0.10
        assert analysis.witness_verdict(run).consistent

    def test_a_single_pass_run_has_no_verdict(self):
        from tests.test_analysis import hotspot, measurement, run_with

        run = run_with([measurement(hotspot(), "flops", 1e9, "flop")])
        assert analysis.witness_verdict(run) is None


class TestFusionDowngrade:
    def _run(self, cycles_pass_1):
        import dataclasses

        from tests.test_analysis import hotspot, machine, measurement, run_with

        spot = hotspot()
        clock = measurement(spot, "task-clock", 2e9, "ns")
        rows = [
            clock,
            dataclasses.replace(clock, pass_index=1),
            measurement(spot, "flops", 1.0e9, "flop"),
            dataclasses.replace(
                clock, counter="flops", unit="flop",
                value=cycles_pass_1, pass_index=1,
            ),
            measurement(spot, "flops_dp", 3.2e9, "flop"),
            dataclasses.replace(
                clock, counter="dram_bytes", unit="byte",
                value=1.6e9, pass_index=1,
            ),
        ]
        return run_with(rows, machine())

    def test_consistent_passes_fuse_exactly(self):
        (diagnostic,) = analysis.diagnose(self._run(1.01e9))
        assert diagnostic.dram_intensity.quality is Quality.MEASURED
        assert diagnostic.dram_intensity.value == 2.0

    def test_diverging_passes_estimate_the_fusion_with_the_reason(self):
        (diagnostic,) = analysis.diagnose(self._run(1.4e9))
        intensity = diagnostic.dram_intensity
        assert intensity.quality is Quality.ESTIMATED
        assert "witness" in intensity.reason and "33%" in intensity.reason
        # achieved never left pass 0: it stays exact.
        assert diagnostic.achieved.quality is Quality.MEASURED


class TestRunDeclarations:
    def test_a_recompiled_module_is_an_invalidity_not_an_uncertainty(self):
        import dataclasses

        from nunatak.cli.run import _pass_consistency
        from tests.test_analysis import hotspot, measurement
        from nunatak.pivot import PhysicalIdentity

        spot = hotspot()
        one = dataclasses.replace(
            spot, physical_identity=PhysicalIdentity(module_id="aaaa", offset=0x10)
        )
        two = dataclasses.replace(
            spot, physical_identity=PhysicalIdentity(module_id="bbbb", offset=0x10)
        )
        rows = [
            measurement(one, "task-clock", 2e9, "ns"),
            dataclasses.replace(
                measurement(two, "task-clock", 2e9, "ns"), pass_index=1
            ),
        ]
        declared = _pass_consistency(rows, threshold=0.05)
        (recompiled,) = [
            d for d in declared if d.name == "module-recompiled-between-passes"
        ]
        assert "/app/solver" in recompiled.message
        assert "two Runs" in recompiled.remedy
