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

# `dsoff` (perf >= 6.4) gives the module-relative offset that the
# normalization into offsets requires, for the hit and for every caller
# when a call-graph mode is recorded.
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
        call_graph: str | None = None,
    ) -> tuple[int, list[Degradation]]:
        """Run `command` under `perf record`, then extract what nunatak
        consumes: the `perf script` text and the build-id list. Returns
        (application exit code, degradations); raw artifacts land under
        `directory`.

        With a counter group, `task-clock` becomes the explicit time base
        (a software event, no hardware counter spent) and the group's
        events ride along; `call_graph` asks perf to record the decided
        stack mode with every sample. perf validates its options before
        launching the application, so a rejection fails fast - no data
        file is written - and the recording walks down its own ladder:
        without call stacks first, then time-only. Each dropped rung is a
        named degradation, and the application runs exactly once, in the
        attempt that perf accepts.

        A rejection is witnessed by `perf script` having nothing to read,
        never by a filesystem check: the witness crosses the execution
        boundary, so a replay reaches the same verdict from the
        recording. An application that itself exits non-zero leaves a
        readable data file and never trips the ladder.
        """
        directory.mkdir(parents=True, exist_ok=True)
        data = directory / PERF_DATA

        selectors: list[str] = []
        if events:
            selectors = ["-e", "task-clock"]
            for entry in events:
                selectors += ["-e", entry.selector]

        attempts: list[tuple[list[str], list[str], Degradation | None]] = [
            (
                selectors,
                ["--call-graph", call_graph] if call_graph else [],
                None,
            )
        ]
        if call_graph:
            attempts.append(
                (
                    selectors,
                    [],
                    Degradation(
                        name="call-stacks-rejected",
                        message=f"perf rejected recording with --call-graph "
                        f"{call_graph}; sampling without stacks",
                        remedy="the kernel may forbid this stack mode here; "
                        "report the perf version",
                    ),
                )
            )
        if selectors:
            attempts.append(
                (
                    [],
                    [],
                    Degradation(
                        name="counter-events-rejected",
                        message="perf rejected this microarchitecture's counter "
                        "group; sampling time only",
                        remedy="the kernel may be too old for these event names; "
                        "report the perf version",
                    ),
                )
            )

        degradations: list[Degradation] = []
        record = script = None
        for attempt_selectors, stack_option, blame in attempts:
            if blame is not None:
                degradations.append(blame)
            record = executor.run(
                [
                    self.path, "record", "--freq", str(frequency),
                    *attempt_selectors, *stack_option,
                    "--output", str(data), "--", *command,
                ],
                capture=False,
                env=env,
            )
            script = executor.run(
                [self.path, "script", "--input", str(data), "--fields", SCRIPT_FIELDS]
            )
            if record.exit_code == 0 or script.exit_code == 0:
                break
        if script.exit_code == 0 and script.stdout is not None:
            (directory / SCRIPT_OUTPUT).write_text(script.stdout)

        buildids = executor.run([self.path, "buildid-list", "--input", str(data)])
        if buildids.exit_code == 0 and buildids.stdout is not None:
            (directory / BUILDID_OUTPUT).write_text(buildids.stdout)

        return record.exit_code, degradations
