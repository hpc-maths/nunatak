"""The rank shim: what nunatak runs inside each MPI rank.

`LaunchPlan.wrap` interposes `python -m nunatak.rank` between the
launcher and the application, so this module executes once per rank, on
the rank's node. It is the counting layer of the two-layer collection:
one `perf stat` around the whole application - a few counters, constant
cost, every rank - whose per-rank aggregates reveal the load imbalance
that sampling a subset of ranks never could.

Artifacts land under `<run>/collect/rank-<rank>/`, and that is the
multi-node retrieval mechanism: the Run directory lives on the shared
filesystem, so each rank writing there before it exits brings the
artifacts home before the job epilogue.

The shim depends on nothing but the standard library, stays silent on
the application's stdout and stderr, and propagates the application's
exit code: measurements observe, they never interfere.
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

from nunatak.launch import rank_identity

COUNTING_EVENTS = ("task-clock", "cycles", "instructions")
STAT_OUTPUT = "perf-stat.csv"
RANK_META = "rank.json"


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


def measure(directory: Path, command: Sequence[str], environment: Mapping[str, str]) -> int:
    """Run `command` in this rank, counting around it, and return its exit
    code.

    Outside any rank identity the command runs untouched and nothing is
    written: a shim that cannot say where it is must not invent a Locus.
    When perf is missing, or fails before launching the application - it
    opens its events first, so a missing or header-only CSV proves the
    application never ran - the application still runs bare and the rank
    meta says the rank went uncounted: a missing capability never
    prevents the run.
    """
    identity = rank_identity(environment)
    if identity is None:
        return subprocess.run(list(command)).returncode

    rank_dir = Path(directory) / f"rank-{identity.rank}"
    rank_dir.mkdir(parents=True, exist_ok=True)
    version = _perf_version()
    output = rank_dir / STAT_OUTPUT

    exit_code = None
    if version is not None:
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
                "counted": output.is_file(),
                "events": list(COUNTING_EVENTS),
                "exit_code": exit_code,
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
    parser.add_argument("command", nargs=argparse.REMAINDER, help="the application")
    arguments = parser.parse_args(argv)
    command = arguments.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.error("no application to run")
    return measure(Path(arguments.directory), command, os.environ)


if __name__ == "__main__":
    sys.exit(main())
