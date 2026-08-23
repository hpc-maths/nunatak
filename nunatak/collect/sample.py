"""/usr/bin/sample driver: temporal sampling, macOS's stated degraded mode.

macOS exposes no event-triggered sampling: the nominal mode is temporal
- the call stacks of every thread, looked at on a fixed interval. Raw
counters per Hotspot are unavailable by platform, the roofline stays
estimated, and both are said where they matter, never silently.

sample attaches to a pid instead of wrapping a command, so the launch
is one shell invocation that starts the application, points sample at
it and propagates the application's exit code - a single recordable
crossing of the execution boundary, exactly like `perf record`'s. The
report is then read back with `cat` in a second invocation: a replay
substitutes the recorded text without needing the file on disk.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from nunatak.collect.execution import Executor
from nunatak.launch import real_target
from nunatak.pivot import Degradation

REPORT_OUTPUT = "sample-report.txt"
TARGET_META = "sample-target.json"

# sample needs a duration up front where perf records open-ended;
# -mayDie ends the analysis when the application exits, so the cap only
# truncates pathologically long runs - and the report's own sample
# count keeps the truncation visible.
DURATION_CAP = 3600


class SampleAdapter:
    """Produces Measurements from /usr/bin/sample's call-graph report."""

    tool = "sample"

    def __init__(self, path: str = "/usr/bin/sample"):
        self.path = path

    def detect(self, executor: Executor) -> str | None:
        """The tool's version, or None when it cannot run.

        sample carries no version of its own - it follows the operating
        system - so the usage banner proves it runs and `sw_vers` names
        the release that versions it.
        """
        invocation = executor.run([self.path])
        banner = f"{invocation.stdout or ''}{invocation.stderr or ''}"
        if "Usage: sample" not in banner:
            return None
        version = executor.run(["sw_vers", "-productVersion"])
        if version.exit_code != 0 or not version.stdout:
            return None
        return f"macOS {version.stdout.strip()}"

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
        """Run `command` with sample attached, then read the report back.

        `events` and `call_graph` are accepted for the adapter contract
        and ignored: macOS offers no counter events to ride along, and
        sample records call stacks unconditionally. The report lands
        under `directory`, along with the resolved target path - the
        report redacts non-system paths, and attribution needs the real
        one to read the binary.
        """
        directory.mkdir(parents=True, exist_ok=True)
        report = directory / REPORT_OUTPUT
        interval_ms = max(1, round(1000 / frequency))
        wrapper = (
            '"$@" & APP=$!; '
            f'{self.path} $APP {DURATION_CAP} {interval_ms} -mayDie '
            f'-file "{report}" >/dev/null 2>&1; '
            "wait $APP"
        )
        argv = ["/bin/sh", "-c", wrapper, "--", *command]
        run = executor.run(
            wrap(argv) if wrap is not None else argv, capture=False, env=env
        )
        text = executor.run(["/bin/cat", str(report)])
        if text.exit_code == 0 and text.stdout is not None:
            report.write_text(text.stdout)

        # Absolute, because attribution only opens absolute paths - a
        # relative launch (./solver) must not hide the binary from it.
        target = real_target(command) or command[0]
        resolved = shutil.which(target) if "/" not in target else target
        (directory / TARGET_META).write_text(
            json.dumps({"target": os.path.abspath(resolved or target)})
        )
        return run.exit_code, []
