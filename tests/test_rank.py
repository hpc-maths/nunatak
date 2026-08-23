"""The counting layer end to end: shim, perf stat parser, ingestion.

The CSV fixtures are the verbatim output of `perf stat -x,` from perf
6.14.11 on an AMD EPYC 7702; the shim tests run `python -m nunatak.rank`
as a real subprocess against a scripted `perf` and a scripted `mpirun`,
so the whole chain - launcher fan-out, per-rank counting, retrieval into
one directory - is exercised without MPI or hardware counters.
"""

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

from nunatak.cli.run import collection_command
from nunatak.config import Config
from nunatak.ingestion import ingest, perf_stat, rank_counting
from nunatak.launch import RankIdentity, split
from nunatak.rank import samples_here
from nunatak.pivot import Quality

REPO_ROOT = Path(__file__).resolve().parents[1]

CSV = """\
14.36,msec,task-clock:u,14356087,100.00,0.124,CPUs utilized
617886,,cycles:u,14356087,100.00,0.043,GHz
5171496,,instructions:u,14356087,100.00,8.37,insn per cycle
"""

UNSUPPORTED = "<not supported>,,stalled-cycles-backend:u,0,100.00,,\n"

# Verbatim perf 6.14.11 on the EPYC asked for nine events over six
# counters: the kernel rotates them and the coverage column says so.
# The bare row is a derived-metric continuation - no event, no count.
MULTIPLEXED = """\
8148092781,,cycles:u,2896410491,85.00,,
19480092744,,instructions:u,2896298471,85.00,2.39,insn per cycle
,,,,,0.08,stalled cycles per insn
1540099307,,stalled-cycles-frontend:u,2896704184,85.00,18.90,frontend cycles idle
<not supported>,,ref-cycles:u,0,100.00,,
"""

FILE_HEADER = "# started on Wed Aug 12 04:34:50 2026\n\n"

# The two sample lines are verbatim perf 6.14.11 output (corpus entry
# workload-c-calibrated), served by the stub's `script` subcommand.
SCRIPT_LINES = """\
        workload 2510799/2510799 28130600.333169:     588211 cycles:Pu:      5db4528f3178 main+0xb8 (/tmp/nunatak-capture-full/workload+0x1178)
        workload 2510799/2510799 28130600.333364:     603961 cycles:Pu:      5db4528f3174 main+0xb4 (/tmp/nunatak-capture-full/workload+0x1174)
"""

STUB_PERF = f"""\
#!/bin/sh
case "$1" in
  --version)
    echo "perf version 6.14.11"
    ;;
  stat)
    shift
    out=""
    while [ "$1" != "--" ]; do
      if [ "$1" = "-o" ]; then out="$2"; shift; fi
      shift
    done
    shift
    cat > "$out" <<'CSV_EOF'
{FILE_HEADER}{CSV}CSV_EOF
    exec "$@"
    ;;
  record)
    shift
    out=""
    while [ "$1" != "--" ]; do
      if [ "$1" = "--output" ]; then out="$2"; shift; fi
      shift
    done
    shift
    : > "$out"
    exec "$@"
    ;;
  script)
    cat <<'LINES_EOF'
{SCRIPT_LINES}LINES_EOF
    ;;
  buildid-list)
    echo "4ce402d2f4f91e424538da7cbab70af0d8100e4e /tmp/nunatak-capture-full/workload"
    ;;
esac
"""

REJECTING_PERF = """\
#!/bin/sh
case "$1" in
  --version)
    echo "perf version 6.14.11"
    ;;
  stat)
    echo "event syntax error" >&2
    exit 129
    ;;
esac
"""

RESTRICTED_PERF = """\
#!/bin/sh
case "$1" in
  --version)
    echo "perf version 6.8.0"
    ;;
  stat)
    shift
    out=""
    while [ "$1" != "--" ]; do
      if [ "$1" = "-o" ]; then out="$2"; shift; fi
      shift
    done
    echo "# started on Wed Aug 12 05:00:00 2026" > "$out"
    echo "Access to performance monitoring operations is restricted." >&2
    exit 255
    ;;
esac
"""

# A launcher-shaped stand-in: runs the wrapped command once per rank,
# sequentially, with the environment Open MPI documents.
STUB_MPIRUN = """\
#!/bin/sh
n=1
while [ "$1" = "-n" ]; do n="$2"; shift 2; done
rank=0
while [ "$rank" -lt "$n" ]; do
  OMPI_COMM_WORLD_RANK=$rank OMPI_COMM_WORLD_SIZE=$n \\
  OMPI_COMM_WORLD_LOCAL_RANK=$rank "$@" || exit $?
  rank=$((rank+1))
done
"""


def script(directory, name, text):
    path = directory / name
    path.write_text(text)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def shim_environment(tmp_path, perf_text=None, rank=3, size=128, local=1):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    environment = dict(os.environ)
    if perf_text is not None:
        script(bin_dir, "perf", perf_text)
        environment["PATH"] = f"{bin_dir}{os.pathsep}/bin{os.pathsep}/usr/bin"
    else:
        # The machine's own perf must stay invisible: CI runners ship
        # one that the kernel then refuses.
        environment["PATH"] = str(bin_dir)
    environment["PYTHONPATH"] = str(REPO_ROOT)
    if rank is not None:
        environment["OMPI_COMM_WORLD_RANK"] = str(rank)
        environment["OMPI_COMM_WORLD_SIZE"] = str(size)
        environment["OMPI_COMM_WORLD_LOCAL_RANK"] = str(local)
    return environment


def run_shim(directory, command, environment):
    return subprocess.run(
        [sys.executable, "-m", "nunatak.rank", "--directory", str(directory), "--", *command],
        env=environment,
        capture_output=True,
        text=True,
    )


def rank_meta(collect_dir, rank):
    return json.loads((collect_dir / f"rank-{rank}" / "rank.json").read_text())


class TestPerfStatParser:
    def test_counts_come_back_normalized(self):
        counts, unparsed = perf_stat.parse(CSV)
        assert unparsed == []
        by_name = {count.counter: count for count in counts}
        assert set(by_name) == {"task-clock", "cycles", "instructions"}
        # perf reports task-clock in msec; the pivot's clocks are ns.
        assert by_name["task-clock"].value == 14.36e6
        assert by_name["task-clock"].unit == "ns"
        assert by_name["cycles"].value == 617886.0
        assert by_name["cycles"].coverage == 1.0

    def test_multiplexed_counters_carry_their_coverage(self):
        counts, unparsed = perf_stat.parse(MULTIPLEXED)
        assert unparsed == []
        by_name = {count.counter: count for count in counts}
        assert by_name["cycles"].coverage == 0.85
        assert by_name["instructions"].value == 19480092744
        # The derived continuation row is display sugar, not a count.
        assert len(counts) == 4

    def test_the_output_file_header_is_skipped(self):
        counts, unparsed = perf_stat.parse(FILE_HEADER + CSV)
        assert len(counts) == 3
        assert unparsed == []

    def test_not_supported_is_an_absence_not_zero(self):
        counts, _ = perf_stat.parse(CSV + UNSUPPORTED)
        absent = counts[-1]
        assert absent.counter == "stalled-cycles-backend"
        assert absent.value is None

    def test_a_garbled_line_is_returned_not_guessed_at(self):
        counts, unparsed = perf_stat.parse(CSV + "what,is,this\n")
        assert len(counts) == 3
        assert unparsed == ["what,is,this"]


class TestPolicy:
    def test_below_the_threshold_every_rank_samples(self):
        identity = RankIdentity(rank=37, world_size=64, local_rank=5)
        assert samples_here(identity, threshold=64) is True

    def test_beyond_the_threshold_only_rank_zero_and_node_firsts_sample(self):
        assert samples_here(RankIdentity(0, 128, 3), 64) is True
        assert samples_here(RankIdentity(64, 128, 0), 64) is True
        assert samples_here(RankIdentity(65, 128, 1), 64) is False

    def test_an_unknown_world_size_narrows_rather_than_floods(self):
        assert samples_here(RankIdentity(0, None, None), 64) is True
        assert samples_here(RankIdentity(9, None, 0), 64) is True
        assert samples_here(RankIdentity(9, None, None), 64) is False


class TestShim:
    def test_a_sampling_rank_records_itself(self, tmp_path):
        collect = tmp_path / "collect"
        environment = shim_environment(tmp_path, STUB_PERF, rank=0, local=0)
        outcome = run_shim(collect, [sys.executable, "-c", ""], environment)
        assert outcome.returncode == 0
        assert (collect / "rank-0" / "perf-script.txt").is_file()
        assert not (collect / "rank-0" / "perf-stat.csv").exists()
        meta = rank_meta(collect, 0)
        assert meta["role"] == "sampling"
        assert meta["sampled"] is True
        assert meta["counted"] is False


    def test_a_counted_rank_leaves_its_artifacts_and_the_exit_code(self, tmp_path):
        collect = tmp_path / "collect"
        environment = shim_environment(tmp_path, STUB_PERF)
        outcome = run_shim(
            collect, [sys.executable, "-c", "import sys; sys.exit(7)"], environment
        )
        assert outcome.returncode == 7
        assert (collect / "rank-3" / "perf-stat.csv").is_file()
        meta = rank_meta(collect, 3)
        assert meta["counted"] is True
        assert meta["role"] == "counting"
        assert meta["perf"] == "6.14.11"
        assert meta["world_size"] == 128
        assert meta["exit_code"] == 7

    def test_without_perf_the_rank_runs_bare_and_says_so(self, tmp_path):
        collect = tmp_path / "collect"
        environment = shim_environment(tmp_path, perf_text=None)
        outcome = run_shim(collect, [sys.executable, "-c", ""], environment)
        assert outcome.returncode == 0
        assert not (collect / "rank-3" / "perf-stat.csv").exists()
        meta = rank_meta(collect, 3)
        assert meta["counted"] is False
        assert meta["perf"] is None

    def test_a_rejecting_perf_never_runs_the_application_twice(self, tmp_path):
        collect = tmp_path / "collect"
        environment = shim_environment(tmp_path, REJECTING_PERF)
        witness = tmp_path / "launches.txt"
        outcome = run_shim(
            collect,
            [sys.executable, "-c", f"open({str(witness)!r}, 'a').write('x')"],
            environment,
        )
        assert outcome.returncode == 0
        assert witness.read_text() == "x"
        assert rank_meta(collect, 3)["counted"] is False

    def test_a_restricted_perf_leaves_a_header_not_a_count(self, tmp_path):
        # GitHub-runner shape: perf exists, creates its CSV header, then
        # the kernel refuses the events - the application never launched.
        collect = tmp_path / "collect"
        environment = shim_environment(tmp_path, RESTRICTED_PERF)
        witness = tmp_path / "launches.txt"
        outcome = run_shim(
            collect,
            [sys.executable, "-c", f"open({str(witness)!r}, 'a').write('x')"],
            environment,
        )
        assert outcome.returncode == 0
        assert witness.read_text() == "x"
        meta = rank_meta(collect, 3)
        assert meta["counted"] is False
        assert not (collect / "rank-3" / "perf-stat.csv").exists()

    def test_outside_any_rank_nothing_is_written(self, tmp_path):
        collect = tmp_path / "collect"
        environment = shim_environment(tmp_path, STUB_PERF, rank=None)
        outcome = run_shim(
            collect, [sys.executable, "-c", "import sys; sys.exit(5)"], environment
        )
        assert outcome.returncode == 5
        assert not collect.exists()


def meta(rank, node="n0", world=None, counted=True, perf="6.14.11"):
    return {
        "rank": rank,
        "world_size": world,
        "local_rank": 0,
        "node": node,
        "perf": perf,
        "counted": counted,
        "events": ["task-clock", "cycles", "instructions"],
        "exit_code": 0,
    }


def rank_dir(collect, entry, csv=CSV):
    directory = collect / f"rank-{entry['rank']}"
    directory.mkdir(parents=True)
    (directory / "rank.json").write_text(json.dumps(entry))
    if entry["counted"]:
        (directory / "perf-stat.csv").write_text(FILE_HEADER + csv)
    return directory


class TestIngestCounting:
    def test_coverage_above_the_threshold_stays_measured(self, tmp_path):
        rank_dir(tmp_path, meta(0), csv=MULTIPLEXED)
        measurements, _ = rank_counting.ingest_counting(tmp_path, 0.8)
        cycles = next(m for m in measurements if m.counter == "cycles")
        assert cycles.quality is Quality.MEASURED
        assert cycles.coverage == 0.85
        assert cycles.reason is None

    def test_coverage_below_the_threshold_downgrades_with_the_numbers(
        self, tmp_path
    ):
        # Same recorded run, stricter threshold: the rule reads the
        # effective configuration, never a constant of its own.
        rank_dir(tmp_path, meta(0), csv=MULTIPLEXED)
        measurements, _ = rank_counting.ingest_counting(tmp_path, 0.9)
        cycles = next(m for m in measurements if m.counter == "cycles")
        assert cycles.quality is Quality.ESTIMATED
        assert "coverage 85% below the 90% threshold" in cycles.reason
        # The unsupported counter keeps its own verdict: absence beats
        # any coverage arithmetic.
        absent = next(m for m in measurements if m.counter == "ref-cycles")
        assert absent.quality is Quality.UNAVAILABLE

    def test_counted_ranks_become_locus_level_measurements(self, tmp_path):
        rank_dir(tmp_path, meta(0, node="n0"))
        rank_dir(tmp_path, meta(1, node="n1"))
        measurements, degradations = rank_counting.ingest_counting(tmp_path, 0.8)
        assert degradations == []
        assert len(measurements) == 6
        assert all(m.hotspot is None for m in measurements)
        assert {(m.locus.node, m.locus.rank) for m in measurements} == {
            ("n0", 0),
            ("n1", 1),
        }
        clock = next(
            m for m in measurements if m.counter == "task-clock" and m.locus.rank == 0
        )
        assert clock.value == 14.36e6
        assert clock.unit == "ns"
        assert clock.quality is Quality.MEASURED

    def test_an_unsupported_counter_ingests_as_unavailable(self, tmp_path):
        rank_dir(tmp_path, meta(0), csv=CSV + UNSUPPORTED)
        measurements, _ = rank_counting.ingest_counting(tmp_path, 0.8)
        absent = next(m for m in measurements if m.counter == "stalled-cycles-backend")
        assert absent.quality is Quality.UNAVAILABLE
        assert absent.value is None

    def test_an_uncounted_rank_is_declared_by_number(self, tmp_path):
        rank_dir(tmp_path, meta(0))
        rank_dir(tmp_path, meta(1, counted=False, perf=None))
        measurements, degradations = rank_counting.ingest_counting(tmp_path, 0.8)
        assert len(measurements) == 3
        (degradation,) = degradations
        assert degradation.name == "counting-unavailable"
        assert "1" in degradation.message

    def test_missing_ranks_are_declared_against_the_world_size(self, tmp_path):
        rank_dir(tmp_path, meta(0, world=4))
        rank_dir(tmp_path, meta(2, world=4))
        _, degradations = rank_counting.ingest_counting(tmp_path, 0.8)
        (degradation,) = degradations
        assert degradation.name == "counting-incomplete"
        assert "2 of 4" in degradation.message
        assert "1, 3" in degradation.message

    def test_a_run_without_ranks_has_no_counting_layer(self, tmp_path):
        assert rank_counting.ingest_counting(tmp_path, 0.8) == ([], [])


class TestCollectionCommand:
    def test_an_mpi_launch_gets_the_shim_inside_each_rank(self, tmp_path):
        solver = script(tmp_path, "solver", "#!/bin/sh\nexit 0\n")
        collect = tmp_path / "run" / "collect"
        command = collection_command(
            split(["mpirun", "-n", "4", str(solver)]), collect, Config()
        )
        assert command[:3] == ["mpirun", "-n", "4"]
        assert command[3] == sys.executable
        assert command[4:7] == ["-m", "nunatak.rank", "--directory"]
        assert command[8:12] == ["--frequency", "997", "--rank-threshold", "64"]
        assert command[-2:] == ["--", str(solver)]

    def test_the_settled_stack_mode_rides_the_shim(self, tmp_path):
        solver = script(tmp_path, "solver", "#!/bin/sh\nexit 0\n")
        command = collection_command(
            split(["mpirun", "-n", "4", str(solver)]),
            tmp_path / "collect",
            Config(),
            call_graph="fp",
            frequency=97,
        )
        assert command[command.index("--call-graph") + 1] == "fp"
        assert command[command.index("--frequency") + 1] == "97"


class TestLauncherToPivotChain:
    def test_the_subset_samples_and_the_rest_counts(self, tmp_path):
        """The wrapped command, run under a launcher-shaped stand-in
        with a threshold of one: rank 0 records itself, rank 1 counts,
        and everything lands in one collect directory - the whole chain
        without MPI."""
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        script(bin_dir, "perf", STUB_PERF)
        script(bin_dir, "mpirun", STUB_MPIRUN)
        environment = dict(os.environ)
        environment["PATH"] = f"{bin_dir}{os.pathsep}/bin{os.pathsep}/usr/bin"
        environment["PYTHONPATH"] = str(REPO_ROOT)

        collect = tmp_path / "run" / "collect"
        app = script(tmp_path, "app", "#!/bin/sh\nexit 0\n")
        wrapped = collection_command(
            split(["mpirun", "-n", "2", str(app)]),
            collect,
            Config(sampling_rank_threshold=1),
        )
        outcome = subprocess.run(
            wrapped, env=environment, capture_output=True, text=True
        )
        assert outcome.returncode == 0, outcome.stderr

        counting, degradations = rank_counting.ingest_counting(collect, 0.8)
        assert degradations == []
        assert {m.locus.rank for m in counting} == {1}
        assert len(counting) == 3

        metas = dict(
            (meta["rank"], (rank_dir, meta))
            for rank_dir, meta in rank_counting.rank_metas(collect)
        )
        assert metas[0][1]["role"] == "sampling"
        assert metas[1][1]["role"] == "counting"
        rank_dir, meta = metas[0]
        sampled, _, sampled_degradations = ingest(
            "perf", meta["perf"], rank_dir, node=meta["node"], rank=0
        )
        assert sampled_degradations == []
        assert sampled, "the sampled rank produced no Measurement"
        assert all(m.locus.rank == 0 for m in sampled)
        assert all(m.hotspot is not None for m in sampled)
