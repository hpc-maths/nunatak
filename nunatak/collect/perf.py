"""perf adapter: Linux CPU collection by event-triggered sampling.

An adapter knows how to detect the presence and version of its tool, build
its command line, execute it, and declare what it produces. It knows
nothing about the pivot: parsing its outputs is the ingestion's job,
versioned by detected tool version.
"""

from __future__ import annotations

import re
from pathlib import Path

from nunatak.collect.execution import Executor
from nunatak.pivot import Degradation

# One line per sample: the call-graph opt-in (--call-graph dwarf) arrives
# with the attribution chain. `dsoff` (perf >= 6.4) gives the
# module-relative offset that the normalization into offsets requires.
SCRIPT_FIELDS = "comm,pid,tid,time,period,event,ip,sym,symoff,dso,dsoff"

PERF_DATA = "perf.data"
SCRIPT_OUTPUT = "perf-script.txt"
BUILDID_OUTPUT = "perf-buildid-list.txt"


class PerfAdapter:
    """Produces Measurements (no Events): sampled raw counters per Hotspot."""

    tool = "perf"

    def __init__(self, path: str = "perf"):
        self.path = path

    def detect(self, executor: Executor) -> str | None:
        """Version of the tool, or None when it cannot run."""
        invocation = executor.run([self.path, "--version"])
        if invocation.exit_code != 0 or not invocation.stdout:
            return None
        match = re.search(r"perf version (\S+)", invocation.stdout)
        return match.group(1) if match else None

    def collect(
        self,
        command: list[str],
        directory: Path,
        executor: Executor,
        frequency: int,
        events: tuple = (),
        env: dict | None = None,
    ) -> tuple[int, list[Degradation]]:
        """Run `command` under `perf record`, then extract what nunatak
        consumes: the `perf script` text and the build-id list. Returns
        (application exit code, degradations); raw artifacts land under
        `directory`.

        With a counter group, `task-clock` becomes the explicit time base
        (a software event, no hardware counter spent) and the group's
        events ride along. perf validates events before launching the
        application, so a rejected group fails fast - no data file is
        written - and the recording is retried time-only: the application
        never runs twice.
        """
        directory.mkdir(parents=True, exist_ok=True)
        data = directory / PERF_DATA

        selectors: list[str] = []
        if events:
            selectors = ["-e", "task-clock"]
            for entry in events:
                selectors += ["-e", entry.selector]

        degradations = []
        record = executor.run(
            [
                self.path, "record", "--freq", str(frequency), *selectors,
                "--output", str(data), "--", *command,
            ],
            capture=False,
            env=env,
        )
        script = executor.run(
            [self.path, "script", "--input", str(data), "--fields", SCRIPT_FIELDS]
        )
        if selectors and record.exit_code != 0 and script.exit_code != 0:
            # A rejected group fails fast: the application never launched
            # and no data was written, so `perf script` has nothing to
            # read. That script invocation is the witness, and it crosses
            # the execution boundary - a replay reaches the same verdict
            # from the recording, where a filesystem check would consult
            # the replaying machine's disk. An application that itself
            # exits non-zero leaves a readable data file and never trips
            # this.
            degradations.append(
                Degradation(
                    name="counter-events-rejected",
                    message="perf rejected this microarchitecture's counter "
                    "group; sampling time only",
                    remedy="the kernel may be too old for these event names; "
                    "report the perf version",
                )
            )
            record = executor.run(
                [
                    self.path, "record", "--freq", str(frequency),
                    "--output", str(data), "--", *command,
                ],
                capture=False,
                env=env,
            )
            script = executor.run(
                [self.path, "script", "--input", str(data), "--fields", SCRIPT_FIELDS]
            )
        if script.exit_code == 0 and script.stdout is not None:
            (directory / SCRIPT_OUTPUT).write_text(script.stdout)

        buildids = executor.run([self.path, "buildid-list", "--input", str(data)])
        if buildids.exit_code == 0 and buildids.stdout is not None:
            (directory / BUILDID_OUTPUT).write_text(buildids.stdout)

        return record.exit_code, degradations
