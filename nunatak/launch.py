"""The launch topology: launcher, application, ranks.

`nunatak run -- mpirun -n 8 ./solver` starts one launcher process where
nunatak runs, and eight ranks wherever the scheduler placed them. This
module is the only place that knows launchers. It splits the command
into launcher prefix and application, so per-rank collection can be
interposed between the two; it reads the rank identity that the MPI
runtime writes into each rank's environment; and the same split names
the real target - `solver`, never `mpirun` - for the Run naming cascade
and the binary inspection of `doctor`.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from typing import Mapping, Sequence

# Everything recognized as "not the application": MPI launchers plus the
# single-node wrappers commonly stacked in front of a binary.
LAUNCHERS = {
    "mpirun",
    "mpiexec",
    "mpiexec.hydra",
    "orterun",
    "prterun",
    "srun",
    "jsrun",
    "aprun",
    "flux",
    "numactl",
    "taskset",
    "env",
    "nice",
    "stdbuf",
    "time",
}

# The subset that fans the application out into MPI ranks. A plain
# `numactl` or `env` wrapper changes the environment, not the topology.
MPI_LAUNCHERS = {
    "mpirun",
    "mpiexec",
    "mpiexec.hydra",
    "orterun",
    "prterun",
    "srun",
    "jsrun",
    "aprun",
    "flux",
}

# Options through which the launchers above declare their world size.
RANK_COUNT_OPTIONS = {"-n", "-np", "--np", "--ntasks"}

# One entry per runtime family, most specific first: a Slurm job running
# Open MPI sets both OMPI_* and SLURM_* families, and the implementation's
# own variables are the ones that describe MPI_COMM_WORLD - srun's
# placement is what mpirun subdivided. Each entry is (rank, world size,
# local rank); None states that the family publishes no such variable.
_RANK_VARIABLES = (
    ("OMPI_COMM_WORLD_RANK", "OMPI_COMM_WORLD_SIZE", "OMPI_COMM_WORLD_LOCAL_RANK"),
    ("MV2_COMM_WORLD_RANK", "MV2_COMM_WORLD_SIZE", "MV2_COMM_WORLD_LOCAL_RANK"),
    ("PMI_RANK", "PMI_SIZE", "MPI_LOCALRANKID"),
    ("PALS_RANKID", None, "PALS_LOCAL_RANKID"),
    ("FLUX_TASK_RANK", "FLUX_JOB_SIZE", "FLUX_TASK_LOCAL_ID"),
    ("SLURM_PROCID", "SLURM_NTASKS", "SLURM_LOCALID"),
)


@dataclass(frozen=True)
class LaunchPlan:
    """A command split at the boundary the launcher cannot cross.

    `prefix` runs once, here; `application` runs in every rank, there.
    An empty `application` states that no target could be resolved behind
    the launcher - there is nothing to wrap, and callers say so instead
    of guessing.
    """

    prefix: tuple[str, ...]
    application: tuple[str, ...]
    mpi: bool
    ranks: int | None

    @property
    def target(self) -> str | None:
        """The argv token of the profiled binary, None when unresolved."""
        return self.application[0] if self.application else None

    def wrap(self, shim: Sequence[str]) -> list[str]:
        """The same launch with `shim` interposed inside each rank.

        `mpirun -n 8 ./solver` becomes `mpirun -n 8 <shim> ./solver`:
        the launcher still fans out, but each rank now starts in the
        shim, which is where per-rank collection happens.
        """
        if not self.application:
            raise ValueError("no resolved application to wrap")
        return [*self.prefix, *shim, *self.application]


def _is_executable_candidate(token: str) -> bool:
    """Whether `token` resolves to an executable file, by path or on PATH."""
    if os.sep in token:
        return os.access(token, os.X_OK) and os.path.isfile(token)
    return shutil.which(token) is not None


def _application_index(command: Sequence[str]) -> int | None:
    """Index of the profiled binary's token, seen through launchers.

    Heuristic: skip environment assignments, known launchers and their
    options; the first remaining token that resolves to an executable is
    the application. Without any launcher, the first plain token is the
    application even when it does not resolve - the error surfaces at
    launch, as 126/127. None when a launcher hides everything.
    """
    saw_launcher = False
    for index, token in enumerate(command):
        if "=" in token.split(os.sep)[-1] and os.sep not in token:
            continue  # environment assignment such as OMP_NUM_THREADS=8
        if token.startswith("-"):
            continue  # launcher option; its value fails the executable test
        if os.path.basename(token) in LAUNCHERS:
            saw_launcher = True
            continue
        if _is_executable_candidate(token) or not saw_launcher:
            return index
    return None


def _declared_ranks(prefix: Sequence[str]) -> int | None:
    """The world size the MPI launcher's options declare, None otherwise.

    Only tokens after the first MPI launcher are read: `nice -n 10`
    carries a niceness, not a rank count. A launch that lets the
    scheduler decide declares nothing here; the ranks discover their
    world size in their environment.
    """
    start = next(
        (
            index
            for index, token in enumerate(prefix)
            if os.path.basename(token) in MPI_LAUNCHERS
        ),
        None,
    )
    if start is None:
        return None
    for index, token in enumerate(prefix[start:], start):
        name, assigned, value = token.partition("=")
        if name not in RANK_COUNT_OPTIONS:
            continue
        if not assigned and index + 1 < len(prefix):
            value = prefix[index + 1]
        if value.isdigit():
            return int(value)
    return None


def split(command: Sequence[str]) -> LaunchPlan:
    """The LaunchPlan of `command`: prefix, application, MPI topology."""
    index = _application_index(command)
    prefix = tuple(command) if index is None else tuple(command[:index])
    application = () if index is None else tuple(command[index:])
    mpi = any(os.path.basename(token) in MPI_LAUNCHERS for token in prefix)
    return LaunchPlan(
        prefix=prefix,
        application=application,
        mpi=mpi,
        ranks=_declared_ranks(prefix) if mpi else None,
    )


def real_target(command: list[str]) -> str | None:
    """Return the argv token of the profiled binary, seen through
    launchers. Returns None when nothing resolves - callers fall back to
    the first token of the command."""
    return split(command).target


def _integer(text: str | None) -> int | None:
    """`text` as a non-negative integer, None for anything else."""
    return int(text) if text is not None and text.isdigit() else None


@dataclass(frozen=True)
class RankIdentity:
    """What one process knows about its place in MPI_COMM_WORLD.

    `local_rank` is the rank's index on its own node - what designates
    one sampled rank per node without any communication. None states the
    runtime did not publish the value, never that it is zero.
    """

    rank: int
    world_size: int | None = None
    local_rank: int | None = None


def rank_identity(environment: Mapping[str, str]) -> RankIdentity | None:
    """The rank identity the MPI runtime wrote into `environment`.

    None outside any rank - which is exactly how a process decides it is
    the orchestrator and not a rank.
    """
    for rank_variable, size_variable, local_variable in _RANK_VARIABLES:
        rank = _integer(environment.get(rank_variable))
        if rank is None:
            continue
        return RankIdentity(
            rank=rank,
            world_size=_integer(environment.get(size_variable or "")),
            local_rank=_integer(environment.get(local_variable or "")),
        )
    return None
