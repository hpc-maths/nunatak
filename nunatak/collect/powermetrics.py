"""powermetrics rider: per-process energy aggregates on macOS runs.

powermetrics must run as root, which makes it a site decision exactly
like perf's paranoid level on Linux: a sudoers rule
(`NOPASSWD: /usr/bin/powermetrics`) enables it, its absence is a named
degradation, never a password prompt in the middle of a run. The probe
is `sudo -n -l` - listing the permission without spending a root
process on it.

It rides the run as a wrapper around the launched command: powermetrics
streams unbuffered plist samples through a pipe into `cat`, and when
the application exits the wrapper kills the cat - ours to kill, where
the root process is not - so powermetrics dies on the broken pipe at
its next write, kernel-delivered, no root kill rule needed. The
samples flushed while the application lived are all on disk. Both
macOS collectors trace the launched process's children, and only
Running threads, so the wrapper's own sleeping processes leave no
weight in the profile.
"""

from __future__ import annotations

import shlex
import sys
from pathlib import Path

from nunatak.collect.execution import Executor

OUTPUT = "powermetrics.plist"
TOOL = "/usr/bin/powermetrics"
# One sample per second: the finest grain whose raw stream stays around
# a quarter megabyte per second of run. An application shorter than the
# interval completes before the first sample and gets the honest
# absence, declared.
INTERVAL_MS = 1000

_SAMPLERS = "cpu_power,tasks"


def allowed(executor: Executor) -> bool:
    """Whether the site's sudoers policy lets powermetrics run.

    `sudo -n -l <tool>` answers from the policy alone: no password
    prompt ever, no root process spent on probing."""
    invocation = executor.run(["sudo", "-n", "-l", TOOL])
    return invocation.exit_code == 0


def wrapped(command: list[str], output: Path, target_name: str) -> list[str]:
    """`command`, wrapped so powermetrics samples for exactly its life.

    `command` is the collector's whole recording invocation, never the
    bare application: xctrace only traces the process it launches, and
    a shell forking the application would hide it from the profiler -
    measured, not feared. One shell invocation: the rider starts, the
    command runs, the filter - `python -m nunatak.powerfilter`, ours to
    kill where the root process is not - dies, and the rider follows on
    the broken pipe. The filter keeps the stream at a few kilobytes per
    sample where the raw one runs to megabytes under a profiler. The
    command's own exit code is the wrapper's.
    """
    slim = (
        f"{shlex.quote(sys.executable)} -m nunatak.powerfilter "
        f"{shlex.quote(target_name)}"
    )
    rider = (
        f"sudo -n {TOOL} --samplers {_SAMPLERS} --show-process-energy "
        f"--format plist -b 0 -i {INTERVAL_MS} -n -1 2>/dev/null "
        f"| {slim} > {shlex.quote(str(output))} & RIDER=$!; "
        '"$@"; STATUS=$?; '
        "kill $RIDER 2>/dev/null; "
        "exit $STATUS"
    )
    return ["/bin/sh", "-c", rider, "--", *command]


def read_back(executor: Executor, directory: Path) -> str | None:
    """The rider's samples, read through the execution boundary.

    A replay substitutes the recorded text; the file is rewritten from
    it so the ingestion reads the same bytes either way. None when the
    rider left nothing - an application shorter than the interval, or
    no rider at all."""
    output = directory / OUTPUT
    invocation = executor.run(["/bin/cat", str(output)])
    if invocation.exit_code != 0 or not invocation.stdout:
        return None
    output.write_text(invocation.stdout)
    return invocation.stdout
