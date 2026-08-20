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
from pathlib import Path

import pytest

from nunatak import machine, probe
from nunatak.cli import principal
from nunatak.collect import mpip, stacks
from nunatak.collect.execution import SubprocessExecutor
from nunatak.config import Config
from nunatak.pivot import Quality, locus_level, read_run
from tests.support import ROOFLINE_WORKLOAD_C, WORKLOAD_C

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


# The exact source that generated the verbatim mpiP fixture: uneven
# per-rank compute, 50 Allreduce rounds, rank-to-0 Sends.
MPI_WORKLOAD_C = """\
#include <mpi.h>
#include <stdlib.h>
#include <string.h>

int main(int argc, char **argv) {
  MPI_Init(&argc, &argv);
  int rank, size;
  MPI_Comm_rank(MPI_COMM_WORLD, &rank);
  MPI_Comm_size(MPI_COMM_WORLD, &size);

  int n = 1 << 20;
  double *a = malloc(n * sizeof(double));
  double *b = malloc(n * sizeof(double));
  memset(a, 0, n * sizeof(double));
  for (int repeat = 0; repeat < 40 * (rank + 1); repeat++)
    for (int i = 0; i < n; i++)
      a[i] = a[i] * 0.5 + 1.0;

  for (int round = 0; round < 50; round++) {
    MPI_Allreduce(a, b, n, MPI_DOUBLE, MPI_SUM, MPI_COMM_WORLD);
    if (rank > 0)
      MPI_Send(a, 4096, MPI_DOUBLE, 0, 0, MPI_COMM_WORLD);
    else
      for (int source = 1; source < size; source++)
        MPI_Recv(b, 4096, MPI_DOUBLE, source, 0, MPI_COMM_WORLD, MPI_STATUS_IGNORE);
  }
  free(a); free(b);
  MPI_Finalize();
  return 0;
}
"""

MPIP_CANDIDATES = ("/opt/mpiP/lib/libmpiP.so", "/usr/local/lib/libmpiP.so")


class TestRealMpi:
    def test_a_real_mpi_run_measures_ranks_and_the_network(
        self, tmp_path, monkeypatch, capsys
    ):
        # The one test where nothing is a stand-in: a real Open MPI
        # launcher, real PMUs inside the ranks, a real mpiP preloaded
        # into a real MPI application.
        mpicc = shutil.which("mpicc")
        if mpicc is None or shutil.which("mpirun") is None:
            pytest.fail("tier 2 needs Open MPI (mpicc and mpirun) on the runner")
        library = next(
            (path for path in MPIP_CANDIDATES if Path(path).is_file()), None
        )
        if library is None:
            pytest.fail("tier 2 needs libmpiP.so on the runner")

        source = tmp_path / "mpi_workload.c"
        source.write_text(MPI_WORKLOAD_C)
        binary = tmp_path / "mpi_workload"
        built = subprocess.run(
            [mpicc, "-O2", "-g", str(source), "-o", str(binary)],
            capture_output=True,
            text=True,
        )
        assert built.returncode == 0, built.stderr
        (tmp_path / "nunatak.toml").write_text(f'[tools]\nmpip = "{library}"\n')
        monkeypatch.chdir(tmp_path)

        assert principal(["run", "--json", "--", "mpirun", "-n", "2", str(binary)]) == 0
        summary = json.loads(capsys.readouterr().out)
        names = {d["name"] for d in summary["degradations"]}
        for absent in ("mpi-analysis-unavailable", "mpi-report-missing",
                       "counting-unavailable", "counting-incomplete"):
            assert absent not in names, summary["degradations"]

        run = read_run(summary["run"])
        aggregates = locus_level(run.measurements)
        mpi_times = {
            m.locus.rank: m.value for m in aggregates if m.counter == "mpi_time"
        }
        assert set(mpi_times) == {0, 1}
        assert all(value and value > 0 for value in mpi_times.values())
        sent = {
            m.locus.rank: m.value for m in aggregates if m.counter == "mpi_sent_bytes"
        }
        assert all(value and value > 0 for value in sent.values())
        # Both ranks are below the threshold: sampled Hotspots per rank.
        sampled = [m for m in run.measurements if m.hotspot is not None]
        assert {m.locus.rank for m in sampled} == {0, 1}
        tools = {c.tool for p in run.passes for c in p.collectors}
        assert tools == {"perf", "mpiP"}
        # The stack travels with the Run: a network analysis whose
        # underlying MPI is unknown is not interpretable.
        assert run.provenance.dependencies.get("mpi", "").startswith("Open MPI")
        assert "mpicc" in run.provenance.dependencies


class TestRealProbe:
    def test_the_probe_builds_once_and_measures_a_real_link(self, tmp_path, monkeypatch):
        if shutil.which("mpicc") is None or shutil.which("mpirun") is None:
            pytest.fail("tier 2 needs Open MPI (mpicc and mpirun) on the runner")
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
        executor = SubprocessExecutor()
        mpi_stack = probe.stack(executor, Config())
        assert mpi_stack is not None
        assert mpi_stack.implementation == "Open MPI"

        binary = probe.build(executor, mpi_stack)
        assert binary is not None and binary.is_file()
        again = probe.build(executor, mpi_stack)
        assert again == binary

        outcome = executor.run(["mpirun", "-n", "2", str(binary), "3"])
        assert outcome.exit_code == 0, outcome.stderr
        measured = probe.parse(outcome.stdout or "")
        assert measured is not None
        assert measured.ranks == 2
        assert measured.nodes == 1
        assert measured.latency_us is not None and measured.latency_us > 0
        assert len(measured.rates) == 3
        assert max(measured.rates) > 0

    def test_an_mpi_run_carries_its_network_ceilings(
        self, tmp_path, monkeypatch, capsys
    ):
        # doctor built the probe; the run launches it through the real
        # mpirun before the application, and the Machine snapshot in the
        # written Run carries the network Ceilings - honestly downgraded
        # on this single-node allocation.
        mpicc = shutil.which("mpicc")
        if mpicc is None or shutil.which("mpirun") is None:
            pytest.fail("tier 2 needs Open MPI (mpicc and mpirun) on the runner")
        executor = SubprocessExecutor()
        mpi_stack = probe.stack(executor, Config())
        assert probe.build(executor, mpi_stack) is not None

        source = tmp_path / "mpi_workload.c"
        source.write_text(MPI_WORKLOAD_C)
        binary = tmp_path / "mpi_workload"
        built = subprocess.run(
            [mpicc, "-O2", "-g", str(source), "-o", str(binary)],
            capture_output=True,
            text=True,
        )
        assert built.returncode == 0, built.stderr
        monkeypatch.chdir(tmp_path)

        assert principal(["run", "--json", "--", "mpirun", "-n", "2", str(binary)]) == 0
        summary = json.loads(capsys.readouterr().out)
        names = {d["name"] for d in summary["degradations"]}
        assert "network-ceiling-unavailable" not in names, summary["degradations"]

        run = read_run(summary["run"])
        ceilings = {c.name: c for c in run.machine.ceilings}
        assert "network_bandwidth" in ceilings, sorted(ceilings)
        bandwidth = ceilings["network_bandwidth"]
        assert bandwidth.value > 0
        assert bandwidth.quality is Quality.ESTIMATED
        assert "shared memory" in bandwidth.reason
        assert ceilings["network_latency"].value > 0


class TestRealMpipBuild:
    def test_doctor_builds_mpip_and_the_run_uses_it(
        self, tmp_path, monkeypatch, capsys
    ):
        # The whole first-use chain, nothing stubbed: the pinned source
        # downloaded from GitHub, configure/make with the real wrappers,
        # the library cached by stack, then a real MPI run that locates
        # it there - no tools.mpip, no module.
        mpicc = shutil.which("mpicc")
        if mpicc is None or shutil.which("mpirun") is None:
            pytest.fail("tier 2 needs Open MPI (mpicc and mpirun) on the runner")
        executor = SubprocessExecutor()
        mpi_stack = probe.stack(executor, Config())
        fortran = mpip.fortran_wrapper(executor, Config())
        if fortran is None:
            pytest.fail("tier 2 needs a Fortran MPI wrapper on the runner")
        library = mpip.build(executor, mpi_stack, fortran)
        assert library is not None, "the pinned mpiP did not build"
        assert mpip.locate(Config(), mpi_stack=mpi_stack) == str(library)

        source = tmp_path / "mpi_workload.c"
        source.write_text(MPI_WORKLOAD_C)
        binary = tmp_path / "mpi_workload"
        built = subprocess.run(
            [mpicc, "-O2", "-g", str(source), "-o", str(binary)],
            capture_output=True,
            text=True,
        )
        assert built.returncode == 0, built.stderr
        monkeypatch.chdir(tmp_path)

        assert principal(["run", "--json", "--", "mpirun", "-n", "2", str(binary)]) == 0
        summary = json.loads(capsys.readouterr().out)
        names = {d["name"] for d in summary["degradations"]}
        assert "mpi-analysis-unavailable" not in names, summary["degradations"]
        assert "mpi-report-missing" not in names, summary["degradations"]

        run = read_run(summary["run"])
        mpi_times = [
            m for m in locus_level(run.measurements) if m.counter == "mpi_time"
        ]
        assert {m.locus.rank for m in mpi_times} == {0, 1}
        assert all(m.value and m.value > 0 for m in mpi_times)


class TestRealStackLadder:
    def _compile(self, tmp_path, flag):
        """The small workload compiled here and now, with `flag` deciding
        the frame pointers."""
        compiler = shutil.which("gcc") or shutil.which("cc")
        if compiler is None:
            pytest.fail("tier 2 needs a C compiler on the runner")
        source = tmp_path / "workload.c"
        source.write_text(WORKLOAD_C)
        binary = tmp_path / f"workload{flag}"
        built = subprocess.run(
            [compiler, "-O2", "-g", flag, str(source), "-o", str(binary)],
            capture_output=True,
            text=True,
        )
        assert built.returncode == 0, built.stderr
        return binary

    def test_frame_pointers_settle_the_fp_rung_against_real_prologues(
        self, tmp_path
    ):
        # This machine is AMD: the lbr rung cannot apply, so the decision
        # exercises the whole probing chain - ldd, the real distribution
        # libc, GNU objdump - against prologues that exist right now.
        binary = self._compile(tmp_path, "-fno-omit-frame-pointer")
        executor = SubprocessExecutor()
        model = executor.cpu_model()
        assert model is not None and "Intel" not in model
        decision = stacks.decide(executor, Config(), str(binary), model)
        assert decision.mode == "fp", decision.detail
        assert decision.modules[0].rate == 1.0

    def test_an_fp_less_binary_loses_the_ladder_and_is_named(self, tmp_path):
        binary = self._compile(tmp_path, "-fomit-frame-pointer")
        executor = SubprocessExecutor()
        decision = stacks.decide(
            executor, Config(), str(binary), executor.cpu_model()
        )
        assert decision.mode is None, decision.detail
        assert str(binary) in decision.detail
        assert "-fno-omit-frame-pointer" in decision.remedy


class TestRealStackCollection:
    def test_a_real_run_records_stacks_over_the_fp_rung(
        self, tmp_path, monkeypatch, capsys
    ):
        # The whole chain on real hardware: prologues probed, fp settled,
        # perf records with --call-graph fp, every sample carries its
        # stack, and the parser sees no line it cannot read.
        compiler = shutil.which("gcc") or shutil.which("cc")
        if compiler is None:
            pytest.fail("tier 2 needs a C compiler on the runner")
        source = tmp_path / "workload.c"
        source.write_text(WORKLOAD_C)
        binary = tmp_path / "workload"
        built = subprocess.run(
            [compiler, "-O2", "-g", "-fno-omit-frame-pointer",
             str(source), "-o", str(binary)],
            capture_output=True,
            text=True,
        )
        assert built.returncode == 0, built.stderr
        monkeypatch.chdir(tmp_path)

        assert principal(
            ["run", "--json", "--no-calibrate", "--", str(binary)]
        ) == 0
        summary = json.loads(capsys.readouterr().out)
        names = {d["name"] for d in summary["degradations"]}
        assert "call-stacks-unavailable" not in names, summary["degradations"]
        assert "call-stacks-rejected" not in names, summary["degradations"]
        assert "perf-script-unparsed" not in names, summary["degradations"]

        from nunatak.ingestion.perf_script import parse_samples

        script_text = (
            Path(summary["run"]) / "collect" / "perf-script.txt"
        ).read_text()
        samples, unparsed = parse_samples(script_text)
        assert unparsed == []
        assert samples and all(s.callers for s in samples)

        run = read_run(summary["run"])
        assert run.stacks
        clock = sum(s.value for s in run.stacks if s.counter == "task-clock")
        assert clock == sum(s.period for s in samples if s.counter == "task-clock")

        # The paths were named by the same attribution pass as the
        # leaves: the payload attaches main to its real caller.
        from nunatak import analysis, report

        payload = report.build(run, analysis.diagnose(run))
        main = next(h for h in payload["hotspots"] if h["name"] == "main")
        assert main["callers"], "no caller attached on real hardware"
        assert main["inclusive"] is not None


class TestRealFallbackSymbolizer:
    def test_addr2line_resolves_a_fresh_binary_with_the_extent_rule(
        self, workload
    ):
        # The real Binutils pair on a binary compiled minutes ago: the
        # located addr2line resolves a line-level chain anchored at the
        # symbol start, and an address in the padding past the last
        # function stays out of the chains - whatever the tool answered.
        from nunatak.attribution import addr2line

        executor = SubprocessExecutor()
        tool = addr2line.locate(executor, Config())
        assert tool is not None, "tier 2 needs binutils on the runner"

        extents = addr2line._function_extents(executor, tool.readelf, str(workload))
        assert extents, "no function extents in a freshly compiled binary"
        start, size = max(extents, key=lambda entry: entry[1])
        inside, gap = start + size // 2, start + size + 1

        outcome = tool.symbolize(executor, str(workload), [inside, gap])
        assert outcome.error is None
        chain = outcome.chains[inside]
        assert chain.physical.start_address == start
        assert chain.frames[0].file and chain.frames[0].line
        assert gap not in outcome.chains or (
            # The gap may fall inside the next function; only a covered
            # address is allowed to resolve.
            any(v <= gap < v + s for v, s in extents)
        )


class TestRealWitness:
    def test_sampled_cycle_periods_track_the_counted_total(self, tmp_path, workload):
        # The witness must be trustworthy or every fusion verdict it
        # guards is poison: the sum of sampled cycle periods has to track
        # the counted total. (`instructions` failed exactly this bar on
        # this machine - 1x or exactly 16x depending on counter
        # placement - which is why it is not a witness.)
        from nunatak import machine
        from nunatak.collect import events
        from nunatak.collect.perf import PerfAdapter
        from nunatak.ingestion.perf_script import parse_samples

        executor = SubprocessExecutor()
        snapshot = machine.snapshot(executor)
        witness = events.witness(snapshot)
        assert witness, "tier 2 runs on a known microarchitecture"

        counted = subprocess.run(
            ["perf", "stat", "-x,", "-e", "cycles", "--", str(workload)],
            capture_output=True,
            text=True,
        )
        total = int(counted.stderr.split(",")[0])

        PerfAdapter().collect(
            [str(workload)], tmp_path / "collect", executor,
            frequency=997, events=witness,
        )
        # A Sample carries the raw selector (`cycles/period=.../u`); the
        # fold onto the canonical name is ingestion's, mirrored here.
        samples, _ = parse_samples((tmp_path / "collect" / "perf-script.txt").read_text())
        sampled = sum(
            s.period
            for s in samples
            if (entry := events.canonical(s.counter)) and entry.canonical == "cycles"
        )
        assert sampled > 0
        assert abs(sampled - total) / total < 0.10, (sampled, total)
