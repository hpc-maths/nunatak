"""The launch topology: splitting at the launcher, rank identity.

Everything here is hermetic: the launchers are never executed, and rank
environments are plain dictionaries shaped like what each MPI runtime
documents.
"""

import stat

from nunatak.launch import RankIdentity, rank_identity, real_target, split


def executable(tmp_path, name):
    """A real executable file, so the candidate test resolves it."""
    path = tmp_path / name
    path.write_text("#!/bin/sh\nexit 0\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return str(path)


class TestRealTarget:
    """The naming cascade and doctor keep seeing through launchers."""

    def test_a_plain_command_is_its_own_target(self, tmp_path):
        """No launcher: the first token, even when it does not resolve."""
        assert real_target(["./solver", "--steps", "10"]) == "./solver"

    def test_the_target_behind_mpirun_is_the_binary_not_mpirun(self, tmp_path):
        """`mpirun -n 256 solver` profiles solver."""
        solver = executable(tmp_path, "solver")
        assert real_target(["mpirun", "-n", "256", solver]) == solver

    def test_environment_assignments_and_nested_launchers_are_skipped(self, tmp_path):
        """`env VAR=x numactl --interleave=all solver` still names solver."""
        solver = executable(tmp_path, "solver")
        command = ["env", "OMP_NUM_THREADS=8", "numactl", "--interleave=all", solver, "input.nml"]
        assert real_target(command) == solver

    def test_launcher_without_resolvable_target_gives_none(self, tmp_path):
        """Behind a launcher, an unresolvable token is not guessed at."""
        assert real_target(["mpirun", "-n", "4", str(tmp_path / "missing")]) is None


class TestSplit:
    """The prefix runs once, the application runs in every rank."""

    def test_a_plain_command_has_an_empty_prefix(self):
        """Direct launch: nothing to interpose behind."""
        plan = split(["./solver", "--steps", "10"])
        assert plan.prefix == ()
        assert plan.application == ("./solver", "--steps", "10")
        assert plan.mpi is False
        assert plan.ranks is None

    def test_mpirun_splits_before_the_binary(self, tmp_path):
        """Launcher and its options on one side, application and its
        arguments on the other."""
        solver = executable(tmp_path, "solver")
        plan = split(["mpirun", "-n", "8", "--bind-to", "core", solver, "case.nml"])
        assert plan.prefix == ("mpirun", "-n", "8", "--bind-to", "core")
        assert plan.application == (solver, "case.nml")
        assert plan.mpi is True
        assert plan.ranks == 8

    def test_srun_ntasks_equals_form_declares_the_world_size(self, tmp_path):
        """`--ntasks=256` is read like `-n 256`."""
        solver = executable(tmp_path, "solver")
        plan = split(["srun", "--ntasks=256", solver])
        assert plan.mpi is True
        assert plan.ranks == 256

    def test_a_launch_without_declared_ranks_leaves_them_unknown(self, tmp_path):
        """The scheduler decides; the ranks will read their environment."""
        solver = executable(tmp_path, "solver")
        plan = split(["srun", solver])
        assert plan.mpi is True
        assert plan.ranks is None

    def test_nice_dash_n_is_a_niceness_not_a_world_size(self, tmp_path):
        """Only options after the MPI launcher declare ranks."""
        solver = executable(tmp_path, "solver")
        plan = split(["nice", "-n", "10", "mpirun", "-np", "4", solver])
        assert plan.ranks == 4

    def test_single_node_wrappers_are_prefix_but_not_mpi(self, tmp_path):
        """`numactl` changes the environment, not the topology."""
        solver = executable(tmp_path, "solver")
        plan = split(["numactl", "--interleave=all", solver])
        assert plan.prefix == ("numactl", "--interleave=all")
        assert plan.mpi is False

    def test_wrap_interposes_the_shim_inside_each_rank(self, tmp_path):
        """The launcher still fans out; each rank starts in the shim."""
        solver = executable(tmp_path, "solver")
        plan = split(["mpirun", "-n", "8", solver, "case.nml"])
        wrapped = plan.wrap(["nunatak-rank", "--"])
        assert wrapped == ["mpirun", "-n", "8", "nunatak-rank", "--", solver, "case.nml"]

    def test_wrap_refuses_an_unresolved_application(self, tmp_path):
        """Appending a shim after an unresolved target would hand the
        launcher a command that is not a launch."""
        plan = split(["mpirun", "-n", "4", str(tmp_path / "missing")])
        assert plan.application == ()
        try:
            plan.wrap(["nunatak-rank", "--"])
        except ValueError:
            return
        raise AssertionError("wrap accepted an empty application")


class TestRankIdentity:
    """Each runtime family publishes its own variables; the MPI
    implementation's beat the scheduler's."""

    def test_open_mpi_publishes_rank_size_and_local_rank(self):
        """The OMPI_COMM_WORLD_* family, complete."""
        environment = {
            "OMPI_COMM_WORLD_RANK": "3",
            "OMPI_COMM_WORLD_SIZE": "8",
            "OMPI_COMM_WORLD_LOCAL_RANK": "1",
        }
        assert rank_identity(environment) == RankIdentity(
            rank=3, world_size=8, local_rank=1
        )

    def test_slurm_variables_serve_a_bare_srun(self):
        """srun without an MPI runtime of its own still identifies ranks."""
        environment = {
            "SLURM_PROCID": "12",
            "SLURM_NTASKS": "64",
            "SLURM_LOCALID": "4",
        }
        assert rank_identity(environment) == RankIdentity(
            rank=12, world_size=64, local_rank=4
        )

    def test_the_implementation_wins_over_the_scheduler(self):
        """mpirun under a Slurm allocation subdivides srun's placement:
        MPI_COMM_WORLD is what OMPI_* describes, not SLURM_*."""
        environment = {
            "OMPI_COMM_WORLD_RANK": "0",
            "OMPI_COMM_WORLD_SIZE": "4",
            "SLURM_PROCID": "2",
            "SLURM_NTASKS": "1",
        }
        identity = rank_identity(environment)
        assert identity.rank == 0
        assert identity.world_size == 4

    def test_rank_zero_is_a_rank_not_an_absence(self):
        """A zero value must never read as 'no rank'."""
        identity = rank_identity({"PMI_RANK": "0", "PMI_SIZE": "16"})
        assert identity == RankIdentity(rank=0, world_size=16, local_rank=None)

    def test_outside_any_rank_there_is_no_identity(self):
        """The orchestrator's own environment: None, by design."""
        assert rank_identity({"PATH": "/usr/bin"}) is None

    def test_a_garbled_value_is_ignored_not_crashed_on(self):
        """A rank variable that is not an integer identifies nothing."""
        assert rank_identity({"OMPI_COMM_WORLD_RANK": "yes"}) is None
