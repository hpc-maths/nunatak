"""Tier 2: what only real hardware can verify - a counter reports.

Everything else in this suite replays recorded outputs; these tests run
the real chain - perf, the calibration kernel, real PMUs - and are the
only place that checks a counter actually reports a value. They assert
properties, never numbers, and they are excluded by default: a machine
without usable counters would fail them honestly, not skip them
silently, so opting in is deliberate (`pytest -m hardware`, tier 2's
nightly job).
"""

import json
import os
import shutil
import stat
import subprocess

import pytest

from nunatak.cli import principal
from nunatak.pivot import Quality, locus_level, read_run
from tests.support import ROOFLINE_WORKLOAD_C

pytestmark = pytest.mark.hardware


@pytest.fixture()
def workload(tmp_path):
    """The milestone workload, compiled here and now with debug information.

    The bandwidth-heavy triad, on purpose: a working set that fits in
    one CCX's slice of L3 produces zero DRAM demand fills, and the
    dram_bytes assertion below would fail on a perfectly healthy
    machine - tier 2 measured exactly that before this comment existed.
    """
    compiler = shutil.which("gcc") or shutil.which("cc")
    if compiler is None:
        pytest.fail("tier 2 needs a C compiler on the runner")
    source = tmp_path / "workload.c"
    source.write_text(ROOFLINE_WORKLOAD_C)
    binary = tmp_path / "workload"
    built = subprocess.run(
        [compiler, "-O2", "-g", str(source), "-o", str(binary)],
        capture_output=True,
        text=True,
    )
    assert built.returncode == 0, built.stderr
    return binary


class TestRealRun:
    def test_a_real_run_measures_real_counters(
        self, workload, tmp_path, monkeypatch, capsys
    ):
        monkeypatch.chdir(tmp_path)
        assert principal(["run", "--json", "--", str(workload)]) == 0
        summary = json.loads(capsys.readouterr().out)
        names = {d["name"] for d in summary["degradations"]}
        assert "cpu-collection-unavailable" not in names, (
            "sampling is blocked on this runner: " + str(summary["degradations"])
        )

        run = read_run(summary["run"])
        clocks = [
            m for m in run.measurements if m.counter == "task-clock" and m.value
        ]
        assert clocks, "no task-clock measurement reached the pivot"
        assert sum(m.value for m in clocks) > 0
        assert summary["hotspots"] >= 1
        assert summary["resolved_hotspots"] >= 1, (
            "not one Hotspot got a name on real hardware"
        )

    def test_the_counter_group_reports_on_this_microarchitecture(
        self, workload, tmp_path, monkeypatch, capsys
    ):
        # The reference machine is an AMD Zen: the FLOP and DRAM counters
        # must ride along and report non-zero values for a FLOP-heavy
        # workload. If this regresses, no VM will ever see it - this test
        # is the reason tier 2 exists.
        monkeypatch.chdir(tmp_path)
        assert principal(["run", "--json", "--", str(workload)]) == 0
        summary = json.loads(capsys.readouterr().out)
        run = read_run(summary["run"])
        by_counter = {}
        for measurement in run.measurements:
            if measurement.value:
                by_counter.setdefault(measurement.counter, 0.0)
                by_counter[measurement.counter] += measurement.value
        rejected = any(
            d["name"] == "counter-events-rejected" for d in summary["degradations"]
        )
        assert not rejected, "the kernel rejected the vendor counter group"
        assert by_counter.get("flops", 0) > 0, sorted(by_counter)
        assert by_counter.get("dram_bytes", 0) > 0, sorted(by_counter)


class TestRealCalibration:
    def test_calibration_measures_this_machine(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        assert principal(["calibrate", "--force", "--json"]) == 0
        profile = json.loads(capsys.readouterr().out)
        ceilings = {c["name"]: c for c in profile["ceilings"]}
        for name in ("dram_bandwidth", "flops_dp"):
            assert name in ceilings, sorted(ceilings)
            ceiling = ceilings[name]
            assert ceiling["value"] > 0
            # A loaded night downgrades with its reason - honesty is the
            # invariant, not the label.
            if ceiling["quality"] == Quality.ESTIMATED.value:
                assert ceiling["reason"]
            else:
                assert ceiling["quality"] == Quality.MEASURED.value


class TestRealCounting:
    def _launcher(self, tmp_path, monkeypatch):
        """A launcher-shaped stand-in on PATH: Open MPI's environment,
        sequential "ranks", real perf underneath."""
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        launcher = bin_dir / "mpirun"
        launcher.write_text(
            "#!/bin/sh\n"
            'n=1\n'
            'while [ "$1" = "-n" ]; do n="$2"; shift 2; done\n'
            "rank=0\n"
            'while [ "$rank" -lt "$n" ]; do\n'
            "  OMPI_COMM_WORLD_RANK=$rank OMPI_COMM_WORLD_SIZE=$n \\\n"
            '  OMPI_COMM_WORLD_LOCAL_RANK=$rank "$@" || exit $?\n'
            "  rank=$((rank+1))\n"
            "done\n"
        )
        launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)
        monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
        monkeypatch.chdir(tmp_path)

    def test_below_the_threshold_every_rank_samples_itself(
        self, workload, tmp_path, monkeypatch, capsys
    ):
        # Two ranks, default threshold: both belong to the sampling
        # subset, each records itself with the vendor counter group on
        # its own PMCs - the contention that corrupted nested counters
        # is structurally gone.
        self._launcher(tmp_path, monkeypatch)
        assert principal(["run", "--json", "--", "mpirun", "-n", "2", str(workload)]) == 0
        summary = json.loads(capsys.readouterr().out)
        names = {d["name"] for d in summary["degradations"]}
        assert "counting-unavailable" not in names, summary["degradations"]

        run = read_run(summary["run"])
        sampled = [m for m in run.measurements if m.hotspot is not None]
        assert {m.locus.rank for m in sampled} == {0, 1}
        flops = [m for m in sampled if m.counter == "flops" and m.value]
        assert flops, "the counter group did not ride inside the ranks"
        assert locus_level(run.measurements) == []

    def test_beyond_the_threshold_the_rest_counts(
        self, workload, tmp_path, monkeypatch, capsys
    ):
        # A threshold of one forces the subset policy with two ranks:
        # rank 0 records itself, rank 1 counts on real PMUs.
        self._launcher(tmp_path, monkeypatch)
        (tmp_path / "nunatak.toml").write_text("[sampling]\nrank_threshold = 1\n")
        assert principal(["run", "--json", "--", "mpirun", "-n", "2", str(workload)]) == 0
        summary = json.loads(capsys.readouterr().out)
        names = {d["name"] for d in summary["degradations"]}
        assert "counting-unavailable" not in names, summary["degradations"]
        assert "counting-incomplete" not in names, summary["degradations"]

        run = read_run(summary["run"])
        sampled = [m for m in run.measurements if m.hotspot is not None]
        assert {m.locus.rank for m in sampled} == {0}
        aggregates = locus_level(run.measurements)
        assert {m.locus.rank for m in aggregates} == {1}
        clock = next(m for m in aggregates if m.counter == "task-clock")
        assert clock.unit == "ns" and clock.value and clock.value > 0
        cycles = next(m for m in aggregates if m.counter == "cycles")
        assert cycles.value and cycles.value > 0
