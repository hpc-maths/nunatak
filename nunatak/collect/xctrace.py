"""xctrace driver: the nominal macOS mode, when Xcode is present.

Where /usr/bin/sample's report aggregates a function's addresses,
xctrace's Time Profiler keeps every sample: per-address weights, the
exact leaf PC, callers with their binaries, and only Running threads -
cpu time, not wall time. The recording wraps the command like perf
does, `--target-stdout -` keeps the application's output on the
caller's terminal, and the target's exit status - which xctrace does
not propagate through its own - is read from the trace's table of
contents.

Three recordable crossings of the execution boundary: the recording,
the time-profile export, the table-of-contents export. The .trace
bundle itself stays in the Run as the raw artifact; replays only need
the two exported XML texts.
"""

from __future__ import annotations

import re
from pathlib import Path

from nunatak.collect.execution import Executor
from nunatak.pivot import Degradation

PROFILE_OUTPUT = "xctrace-time-profile.xml"
TOC_OUTPUT = "xctrace-toc.xml"
TRACE_BUNDLE = "xctrace.trace"

_TABLE_XPATH = '/trace-toc/run[@number="1"]/data/table[@schema="time-profile"]'
_EXIT_STATUS = re.compile(r'return-exit-status="(\d+)"')


class XctraceAdapter:
    """Produces Measurements from Instruments' time-profile table."""

    tool = "xctrace"

    def __init__(self, path: str = "xctrace"):
        self.path = path

    def detect(self, executor: Executor) -> str | None:
        """Version of the tool, or None when it cannot run.

        /usr/bin/xctrace exists on every Mac as a shim that errors out
        without Xcode: only the version banner proves the real tool."""
        invocation = executor.run([self.path, "version"])
        output = f"{invocation.stdout or ''}{invocation.stderr or ''}"
        match = re.search(r"xctrace version (\S+)", output)
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
        wrap=None,
    ) -> tuple[int, list[Degradation]]:
        """Run `command` under the Time Profiler, then export what
        nunatak consumes.

        `wrap` lets a rider envelop the recording invocation itself.
        `events` and `call_graph` are accepted for the adapter contract
        and ignored: macOS offers no counter events, and the Time
        Profiler records backtraces unconditionally; its interval is the
        instrument's own (1 ms), read back per sample from the exported
        weights rather than assumed. The application's exit status comes
        from the table of contents - xctrace exits with its own code
        when the target fails, and the recording is not the failure.
        """
        directory.mkdir(parents=True, exist_ok=True)
        trace = directory / TRACE_BUNDLE
        # A rider (powermetrics) wraps the whole recording, never the
        # command: xctrace only traces the process it launches, and a
        # shell forking the application would hide it from the profiler.
        argv = [
            self.path, "record", "--template", "Time Profiler",
            "--output", str(trace), "--target-stdout", "-",
            "--launch", "--", *command,
        ]
        record = executor.run(
            wrap(argv) if wrap is not None else argv, capture=False, env=env
        )
        profile = executor.run(
            [self.path, "export", "--input", str(trace), "--xpath", _TABLE_XPATH]
        )
        if profile.exit_code == 0 and profile.stdout is not None:
            (directory / PROFILE_OUTPUT).write_text(profile.stdout)
        toc = executor.run([self.path, "export", "--input", str(trace), "--toc"])
        if toc.exit_code == 0 and toc.stdout is not None:
            (directory / TOC_OUTPUT).write_text(toc.stdout)
            match = _EXIT_STATUS.search(toc.stdout)
            if match is not None:
                return int(match.group(1)), []
        # No table of contents to answer for the target: the recording
        # itself failed, and its own exit code is the honest one.
        return record.exit_code, []
