"""Resolution of the real target binary behind a launcher.

In `nunatak run -- mpirun -n 256 ./solver` the profiled binary is `solver`,
not `mpirun`. The same machinery serves the Run naming cascade and the
binary inspection of `doctor`.
"""

from __future__ import annotations

import os
import shutil

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


def _is_executable_candidate(token: str) -> bool:
    """Whether `token` resolves to an executable file, by path or on PATH."""
    if os.sep in token:
        return os.access(token, os.X_OK) and os.path.isfile(token)
    return shutil.which(token) is not None


def real_target(command: list[str]) -> str | None:
    """Return the argv token of the profiled binary, seen through launchers.

    Heuristic: skip environment assignments, known launchers and their
    options; the first remaining token that resolves to an executable is the
    target. Returns None when nothing resolves - callers fall back to the
    first token of the command.
    """
    saw_launcher = False
    for token in command:
        if "=" in token.split(os.sep)[-1] and not os.sep in token:
            continue  # environment assignment such as OMP_NUM_THREADS=8
        if token.startswith("-"):
            continue  # launcher option; its value fails the executable test
        base = os.path.basename(token)
        if base in LAUNCHERS:
            saw_launcher = True
            continue
        if _is_executable_candidate(token):
            return token
        if not saw_launcher:
            # No launcher involved: the first token is the target even when
            # it does not resolve (the error surfaces at launch, as 126/127).
            return token
    return None
