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
_PROCESS = re.compile(r"<process\b[^>]*>")
_LAUNCHED = re.compile(r'type="launched"')
_EXIT_STATUS = re.compile(r'return-exit-status="(\d+)"')


def _target_status(toc: str) -> int | None:
    """The exit status of the process xctrace launched.

    A table of contents describes every process a trace saw, and only the
    launched one is the application, so the status is read from that
    element rather than from the first one the document happens to carry.

    Read textually and not as a tree: an export can come back cut short,
    and a truncated document still names the process at its head.
    """
    for match in _PROCESS.finditer(toc):
        element = match.group(0)
        if not _LAUNCHED.search(element):
            continue
        status = _EXIT_STATUS.search(element)
        return int(status.group(1)) if status else None
    return None


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
            status = _target_status(toc.stdout)
            if status is not None:
                return status, []
        # xctrace exits 0 only when its target did, so a successful
        # recording answers for the target on its own.
        if record.exit_code == 0:
            return 0, []
        # It failed, and without the table of contents there is no saying
        # with which code: xctrace reports 54 for any failing target. Its
        # code is what a shell will see, and the loss is declared rather
        # than dressed up as the application's own status.
        return record.exit_code, [
            Degradation(
                name="exit-status-unavailable",
                message=(
                    "the trace's table of contents did not name the launched "
                    f"target's exit status; xctrace's own code "
                    f"({record.exit_code}) stands, and it says the run failed, "
                    "not with which code"
                ),
                remedy="run again: the table-of-contents export answers intermittently",
            )
        ]
