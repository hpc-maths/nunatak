"""The network probe: stack identity, cached build, self-reported output.

Version outputs and the probe transcript are verbatim: Open MPI 5.0.7
and MPICH 4.2.1 as Ubuntu ships them, and a real 2-rank pingpong on the
EPYC 7702 (shared-memory link, hence the numbers).
"""

import json
import os
import stat
from pathlib import Path

from nunatak import probe
from nunatak.cli import doctor
from nunatak.collect.execution import SubprocessExecutor
from nunatak.config import Config
from tests.support import ScriptedExecutor

OPEN_MPI_VERSION = """\
mpirun (Open MPI) 5.0.7

Report bugs to https://www.open-mpi.org/community/help/
"""

HYDRA_VERSION = """\
HYDRA build details:
    Version:                                 4.2.1
    Release Date:                            Wed Apr 17 15:30:02 CDT 2024
    Process Manager:                         pmi
"""

PROBE_OUTPUT = """\
probe pingpong
ranks 2
latency_us 0.603
bytes 4194304
rep 0 3.732137e+09
rep 1 3.811625e+09
rep 2 3.820277e+09
rep 3 3.815909e+09
rep 4 3.801362e+09
"""


class TestStack:
    def test_open_mpi_identifies_by_its_one_liner(self):
        assert probe._parse_launcher(OPEN_MPI_VERSION) == ("Open MPI", "5.0.7")

    def test_mpich_identifies_by_its_hydra_block(self):
        assert probe._parse_launcher(HYDRA_VERSION) == ("MPICH", "4.2.1")

    def test_an_unknown_launcher_keeps_its_first_line(self):
        implementation, version = probe._parse_launcher("SomeVendor MPI 9.9\n")
        assert implementation == "unknown"
        assert version == "SomeVendor MPI 9.9"

    def test_the_stack_is_the_triple_that_keys_the_cache(self):
        executor = (
            ScriptedExecutor()
            .on("mpicc", stdout="gcc (Ubuntu 14.2.0-19ubuntu2) 14.2.0")
            .on("mpirun", stdout=OPEN_MPI_VERSION)
        )
        mpi_stack = probe.stack(executor, Config())
        assert mpi_stack == probe.MpiStack(
            implementation="Open MPI", version="5.0.7", mpicc="mpicc"
        )
        assert mpi_stack.label == "Open MPI 5.0.7"

    def test_without_a_usable_mpicc_there_is_no_stack(self):
        executor = ScriptedExecutor().on("mpicc", exit_code=127)
        assert probe.stack(executor, Config()) is None


def fake_mpicc(directory):
    """An mpicc stand-in that logs its calls and produces the binary."""
    compiler = directory / "mpicc"
    compiler.write_text(
        "#!/bin/sh\n"
        'echo "$@" >> "$0.log"\n'
        'while [ "$1" != "-o" ]; do shift; done\n'
        'echo built > "$2"\n'
    )
    compiler.chmod(compiler.stat().st_mode | stat.S_IXUSR)
    return compiler


class TestBuild:
    def test_the_first_build_compiles_and_the_second_reuses(self, tmp_path):
        compiler = fake_mpicc(tmp_path)
        mpi_stack = probe.MpiStack("Open MPI", "5.0.7", str(compiler))
        executor = SubprocessExecutor()
        cache = tmp_path / "probes"
        first = probe.build(executor, mpi_stack, cache)
        second = probe.build(executor, mpi_stack, cache)
        assert first is not None and first == second
        assert first.read_text() == "built\n"
        calls = Path(f"{compiler}.log").read_text().splitlines()
        assert len(calls) == 1, "a cached probe must not rebuild"
        # The cache entry stays explainable without nunatak.
        recorded = json.loads((first.parent / "stack.json").read_text())
        assert recorded["implementation"] == "Open MPI"

    def test_two_stacks_never_share_a_binary(self, tmp_path):
        compiler = fake_mpicc(tmp_path)
        executor = SubprocessExecutor()
        cache = tmp_path / "probes"
        one = probe.build(
            executor, probe.MpiStack("Open MPI", "5.0.7", str(compiler)), cache
        )
        other = probe.build(
            executor, probe.MpiStack("MPICH", "4.2.1", str(compiler)), cache
        )
        assert one != other

    def test_a_failing_compiler_yields_none_not_a_binary(self, tmp_path):
        compiler = tmp_path / "mpicc"
        compiler.write_text("#!/bin/sh\nexit 1\n")
        compiler.chmod(compiler.stat().st_mode | stat.S_IXUSR)
        mpi_stack = probe.MpiStack("Open MPI", "5.0.7", str(compiler))
        assert probe.build(SubprocessExecutor(), mpi_stack, tmp_path / "p") is None


class TestParse:
    def test_the_verbatim_transcript_parses_completely(self):
        outcome = probe.parse(PROBE_OUTPUT)
        assert outcome.ranks == 2
        assert outcome.bytes == 4194304
        assert outcome.latency_us == 0.603
        assert len(outcome.rates) == 5
        assert max(outcome.rates) == 3.820277e09

    def test_foreign_output_is_not_a_probe_run(self):
        assert probe.parse("perf version 6.14.11\n") is None


class TestDoctor:
    def test_without_mpicc_the_network_analysis_is_declared_unavailable(self):
        executor = ScriptedExecutor().on("mpicc", exit_code=127)
        check = doctor._network_probe(executor, Config())
        assert check.status == "missing"
        assert check.degradation.name == "network-analysis-unavailable"

    def test_a_built_probe_reports_the_stack_and_the_path(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
        compiler = fake_mpicc(tmp_path)
        config = Config(tools={"mpicc": str(compiler)})
        executor = (
            ScriptedExecutor()
            .on(compiler.name, stdout="gcc 14.2.0")
            .on("mpirun", stdout=OPEN_MPI_VERSION)
        )
        # The build goes through a real subprocess: swap executors after
        # the identification, like the doctor's own SubprocessExecutor
        # would serve both.
        mpi_stack = probe.stack(executor, config)
        binary = probe.build(SubprocessExecutor(), mpi_stack)
        assert binary is not None
        assert str(tmp_path) in str(binary)
