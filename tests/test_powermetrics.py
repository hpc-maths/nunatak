"""The powermetrics rider: root telemetry, filtered, summed, declared.

Fixtures are verbatim from the Apple M5 Max: one full powermetrics
plist sample (231 KB for one second of one machine - the reason the
filter exists) and the reduced stream the filter left in a recorded
run's pipe.
"""

import json
from pathlib import Path

import pytest

from nunatak import powerfilter
from nunatak.collect import powermetrics
from nunatak.collect.xctrace import XctraceAdapter
from nunatak.ingestion import powermetrics_plist
from nunatak.pivot import Quality
from tests.support import ScriptedExecutor

FIXTURES = Path(__file__).resolve().parent / "fixtures"
FULL = (FIXTURES / "powermetrics-full-sample.plist").read_bytes()
REDUCED = (FIXTURES / "powermetrics-reduced.plist").read_text()
CORPUS = (
    Path(__file__).resolve().parent.parent
    / "corpus" / "recordings" / "xctrace" / "16.0" / "darwin-arm64"
    / "triad-c-power"
)


class TestFilter:
    def test_a_full_sample_reduces_to_the_kept_fields(self):
        chunk = FULL.rstrip(b"\x00")
        slim = powerfilter.reduced(chunk, "kernel_task")
        assert slim is not None
        assert len(slim) < len(chunk) // 20
        import plistlib

        sample = plistlib.loads(slim)
        assert set(sample) == {"elapsed_ns", "processor", "tasks"}
        assert "cpu_energy" in sample["processor"]
        assert all(task["name"] == "kernel_task" for task in sample["tasks"])

    def test_garbage_reduces_to_nothing_not_a_crash(self):
        assert powerfilter.reduced(b"not a plist", "x") is None


class TestParser:
    def test_the_reduced_stream_sums_into_the_aggregates(self):
        aggregates, count, unparsed = powermetrics_plist.parse(
            REDUCED, "triad-mid"
        )
        assert unparsed == []
        assert count == 2
        assert aggregates["energy_impact"] == pytest.approx(7475.15, rel=1e-3)
        assert aggregates["cpu_energy"] == 22613.0
        assert aggregates["gpu_energy"] == 103.0

    def test_measurements_are_locus_level_and_estimated_with_reasons(self):
        rows, count, _ = powermetrics_plist.measurements(
            REDUCED, "triad-mid", node="laptop"
        )
        assert count == 2
        assert [r.counter for r in rows] == [
            "energy_impact", "cpu_energy", "gpu_energy",
        ]
        assert all(r.hotspot is None for r in rows)
        assert all(r.quality is Quality.ESTIMATED for r in rows)
        assert "not joules" in rows[0].reason
        assert "every process" in rows[1].reason
        assert rows[1].unit == "mJ"

    def test_an_empty_stream_is_no_measurement_never_zeroes(self):
        rows, count, _ = powermetrics_plist.measurements("", "app", node="n")
        assert rows == [] and count == 0


class TestRider:
    def test_the_wrapper_envelops_the_whole_recording_invocation(self, tmp_path):
        argv = powermetrics.wrapped(
            ["xctrace", "record", "--launch", "--", "./solver"],
            tmp_path / "pm.plist",
            "solver",
        )
        assert argv[:2] == ["/bin/sh", "-c"]
        script = argv[2]
        assert f"sudo -n {powermetrics.TOOL}" in script
        assert "-m nunatak.powerfilter solver" in script
        assert "kill $RIDER" in script
        # The recording invocation rides behind `--`, untouched.
        assert argv[-5:] == ["xctrace", "record", "--launch", "--", "./solver"]

    def test_the_sudoers_policy_is_probed_without_a_root_process(self):
        allowed = ScriptedExecutor(system="Darwin").on("sudo", exit_code=0)
        assert powermetrics.allowed(allowed)
        assert allowed.calls[0][:3] == ["sudo", "-n", "-l"]
        refused = ScriptedExecutor(system="Darwin").on(
            "sudo", stderr="a password is required", exit_code=1
        )
        assert not powermetrics.allowed(refused)

    def test_the_adapter_applies_the_wrap_to_its_recording(self, tmp_path):
        executor = (
            ScriptedExecutor(system="Darwin")
            .on("sh", exit_code=0)
            .on("xctrace", stderr="no trace", exit_code=1)
            .on("xctrace", stderr="no trace", exit_code=1)
        )
        XctraceAdapter().collect(
            ["./solver"], tmp_path / "c", executor, frequency=997,
            wrap=lambda argv: ["/bin/sh", "-c", "rider", "--", *argv],
        )
        launched = executor.calls[0]
        assert launched[:3] == ["/bin/sh", "-c", "rider"]
        assert launched[4] == "xctrace"

    def test_read_back_rewrites_the_file_from_the_recorded_text(self, tmp_path):
        executor = ScriptedExecutor(system="Darwin").on("cat", stdout=REDUCED)
        text = powermetrics.read_back(executor, tmp_path)
        assert text == REDUCED
        assert (tmp_path / powermetrics.OUTPUT).read_text() == REDUCED


class TestDoctorVerdict:
    def light(self, sudo_exit):
        from nunatak.cli.doctor import light_checks
        from nunatak.config import Config

        executor = (
            ScriptedExecutor(system="Darwin")
            .on("xctrace", stdout="xctrace version 16.0 (17F113)\n")
            .on("sudo", exit_code=sudo_exit)
        )
        from nunatak.collect import cpu_collector

        adapter, version = cpu_collector(executor, Config())
        checks = light_checks(
            executor, Config(), [], cpu=(adapter, version), llvm=(None,)
        )
        return next(c for c in checks if c.name == "power-aggregates")

    def test_an_allowing_policy_is_ok(self):
        assert self.light(0).status == "ok"

    def test_a_refusing_policy_is_a_named_degradation(self):
        check = self.light(1)
        assert check.status == "warning"
        assert check.degradation.name == "power-aggregates-unavailable"
        assert "NOPASSWD" in check.remedy


class TestReplayedRiderRun:
    """The recorded macOS entry with the rider: xctrace, atos and the
    filtered powermetrics stream replayed from the Apple M5 Max."""

    @pytest.fixture(autouse=True)
    def in_tmp_cwd(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

    def test_the_energy_aggregates_ride_the_replayed_run(self, capsys):
        from nunatak.cli import principal
        from nunatak.pivot import read_run

        assert (
            principal(
                ["run", "--replay", str(CORPUS), "--no-calibrate", "--json",
                 "--", "./triad-mid"]
            )
            == 0
        )
        summary = json.loads(capsys.readouterr().out)
        run = read_run(summary["run"])
        aggregates = {
            m.counter: m for m in run.measurements if m.hotspot is None
        }
        assert set(aggregates) == {"energy_impact", "cpu_energy", "gpu_energy"}
        assert aggregates["cpu_energy"].value == 22613.0
        assert aggregates["energy_impact"].quality is Quality.ESTIMATED
        names = {d["name"] for d in summary["degradations"]}
        assert "power-aggregates-unavailable" not in names
        assert summary["resolved_hotspots"] >= 1
