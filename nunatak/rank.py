"""The rank shim: what nunatak runs inside each MPI rank.

`LaunchPlan.wrap` interposes `python -m nunatak.rank` between the
launcher and the application, so this module executes once per rank, on
the rank's node, where both collection layers live. Every rank belongs
to the **counting** layer - one `perf stat` around the whole
application, a few counters, constant cost - except the ranks of the
**sampling** subset, which record themselves instead: the counter group
runs on the rank's own PMCs (an outer sampler fighting for the same
physical counters corrupts them - measured, not feared), and the rank's
time aggregate is recoverable from its own samples, so nothing is
nested around the record.

Artifacts land under `<run>/collect/rank-<rank>/`, and that is the
multi-node retrieval mechanism: the Run directory lives on the shared
filesystem, so each rank writing there before it exits brings the
artifacts home before the job epilogue.

The shim stays silent on the application's stdout and stderr, and
propagates the application's exit code: measurements observe, they
never interfere.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Mapping, Sequence

from nunatak import machine
from nunatak.collect import events as counter_events
from nunatak.collect.execution import SubprocessExecutor
from nunatak.collect.perf import SCRIPT_OUTPUT, PerfAdapter
from nunatak.launch import RankIdentity, rank_identity
from nunatak.pivot import Degradation

COUNTING_EVENTS = ("task-clock", "cycles", "instructions")
STAT_OUTPUT = "perf-stat.csv"
RANK_META = "rank.json"


def samples_here(identity: RankIdentity, threshold: int) -> bool:
    """Whether this rank belongs to the sampling subset.

    Below the threshold everything is sampled. Beyond it - or when the
    world size is unknown - sampling narrows to rank 0 plus the first
    rank of each node: Hotspots stay attributable everywhere the code
    runs, at a cost that stops growing with the job. A rank that knows
    neither its world size nor its local rank samples only as rank 0.
    """
    if identity.world_size is not None and identity.world_size <= threshold:
        return True
    return identity.rank == 0 or identity.local_rank == 0


def _perf_version() -> str | None:
    """The version of the perf on this node's PATH, None without one."""
    if shutil.which("perf") is None:
        return None
    probe = subprocess.run(
        ["perf", "--version"], capture_output=True, text=True
    )
    match = re.search(r"perf version (\S+)", probe.stdout or "")
    return match.group(1) if match else None


def _usable(output: Path) -> bool:
    """Whether the CSV carries at least one count line.

    perf creates its `-o` file before opening the events, so a
    header-only file is the witness of a perf that failed before
    launching the application - a restricted kernel, a rejected event.
    """
    if not output.is_file():
        return False
    return any(
        line.strip() and not line.startswith("#")
        for line in output.read_text().splitlines()
    )


def measure(
    directory: Path,
    command: Sequence[str],
    environment: Mapping[str, str],
    frequency: int = 997,
    rank_threshold: int = 64,
) -> int:
    """Run `command` in this rank, collecting around it, and return its
    exit code.

    The sampling subset records itself (counter group included); every
    other rank counts. Outside any rank identity the command runs
    untouched and nothing is written: a shim that cannot say where it is
    must not invent a Locus. perf opens its events before launching, so
    a missing script output (record) or a header-only CSV (stat) proves
    the application never ran: the rank falls back down the ladder -
    sampling, then counting, then bare - and the application runs
    exactly once. A missing capability never prevents the run.
    """
    identity = rank_identity(environment)
    if identity is None:
        return subprocess.run(list(command)).returncode

    rank_dir = Path(directory) / f"rank-{identity.rank}"
    rank_dir.mkdir(parents=True, exist_ok=True)
    version = _perf_version()
    output = rank_dir / STAT_OUTPUT
    sampling = version is not None and samples_here(identity, rank_threshold)
    degradations: list[Degradation] = []

    exit_code = None
    if sampling:
        executor = SubprocessExecutor()
        adapter = PerfAdapter()
        events = counter_events.sampling_events(machine.snapshot(executor))
        exit_code, degradations = adapter.collect(
            command, rank_dir, executor, frequency, events=events
        )
        if not (rank_dir / SCRIPT_OUTPUT).is_file():
            # perf record fails fast, before launching: the rank falls
            # back to counting, and the application still runs once.
            sampling = False
            exit_code = None
    if not sampling and version is not None and exit_code is None:
        exit_code = subprocess.run(
            [
                "perf", "stat", "-x,", "-e", ",".join(COUNTING_EVENTS),
                "-o", str(output), "--", *command,
            ]
        ).returncode
        if not _usable(output):
            output.unlink(missing_ok=True)
            exit_code = None
    if exit_code is None:
        exit_code = subprocess.run(list(command)).returncode

    (rank_dir / RANK_META).write_text(
        json.dumps(
            {
                "rank": identity.rank,
                "world_size": identity.world_size,
                "local_rank": identity.local_rank,
                "node": platform.node(),
                "perf": version,
                "role": "sampling" if sampling else "counting",
                "sampled": (rank_dir / SCRIPT_OUTPUT).is_file(),
                "counted": output.is_file(),
                "events": list(COUNTING_EVENTS),
                "exit_code": exit_code,
                "degradations": [
                    {"name": d.name, "message": d.message, "remedy": d.remedy}
                    for d in degradations
                ],
            },
            indent=2,
        )
        + "\n"
    )
    return exit_code


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point of `python -m nunatak.rank`."""
    parser = argparse.ArgumentParser(
        prog="python -m nunatak.rank",
        description="nunatak's per-rank counting shim; not meant to be "
        "invoked by hand",
    )
    parser.add_argument("--directory", required=True, help="the Run's collect directory")
    parser.add_argument("--frequency", type=int, default=997, help="sampling frequency")
    parser.add_argument(
        "--rank-threshold", type=int, default=64,
        help="world size beyond which sampling narrows to rank 0 plus one rank per node",
    )
    parser.add_argument("command", nargs=argparse.REMAINDER, help="the application")
    arguments = parser.parse_args(argv)
    command = arguments.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.error("no application to run")
    return measure(
        Path(arguments.directory),
        command,
        os.environ,
        frequency=arguments.frequency,
        rank_threshold=arguments.rank_threshold,
    )


if __name__ == "__main__":
    sys.exit(main())
