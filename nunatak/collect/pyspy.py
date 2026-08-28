"""py-spy: the temporal fallback where the trampolines do not exist.

A CPython older than 3.12 exposes no frames to perf; py-spy reads them
from outside, at wall intervals, active threads only - Python Hotspots
with full resolution, raw hardware Counters unavailable. The two flows
are never fused into one stack: two clocks, two triggers, merging them
would be double counting dressed as measurement.

Two measured facts shape the invocation. py-spy exits 0 even when the
application failed, so the exit code nunatak must propagate is
witnessed by a shell wrapper writing it to a file - and py-spy stays
the parent of everything (`--subprocesses` reaches the interpreter
through the wrapper), which is what keeps the ptrace lawful under
yama's default scope: a profiler may always read its descendants,
attaching to a sibling is refused on stock kernels.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from nunatak.collect.execution import Executor
from nunatak.config import Config
from nunatak.pivot import Degradation

RAW_OUTPUT = "pyspy-raw.txt"
EXIT_FILE = "pyspy-exit"
META_OUTPUT = "pyspy.json"

_BANNER = re.compile(r"py-spy (\d+\.\d+(\.\d+)?)")

# The wrapper that witnesses the application's exit code: py-spy only
# reports its own, which is 0 even when the application failed. No
# semicolon anywhere in it: py-spy prints the wrapper's own command
# line inside its process frames, and the parser splits stacks on
# semicolons - the scaffolding must not shatter the lines it rides in.
def _witness(exit_file):
    """The sh script that runs the application and writes its exit."""
    return f'"$@" && echo 0 > {exit_file} || echo $? > {exit_file}'


@dataclass(frozen=True)
class PySpyAdapter:
    """One usable py-spy, invoked and parsed, never linked."""

    path: str = "py-spy"
    tool: str = "py-spy"

    def detect(self, executor: Executor) -> str | None:
        """The version py-spy answers with, None when it cannot run."""
        invocation = executor.run([self.path, "--version"])
        if invocation.exit_code != 0:
            return None
        matched = _BANNER.search(
            (invocation.stdout or "") + (invocation.stderr or "")
        )
        return matched.group(1) if matched else None

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
        """Run `command` under py-spy, temporally. Returns (application
        exit code, degradations); the raw collapsed stacks land under
        `directory`.

        `events` and `call_graph` are accepted and unused: a temporal
        sampler has no counters to program, and the collapsed format
        carries every stack by construction. The sampling rate follows
        the configured frequency, so one knob governs both paths.
        """
        directory.mkdir(parents=True, exist_ok=True)
        raw = directory / RAW_OUTPUT
        exit_file = directory / EXIT_FILE
        record = executor.run(
            [
                self.path, "record", "--subprocesses",
                "--format", "raw", "--rate", str(frequency),
                "--output", str(raw),
                "--", "sh", "-c", _witness(exit_file), "sh", *command,
            ],
            capture=False,
            env=env,
        )
        (directory / META_OUTPUT).write_text(
            f'{{"rate": {frequency}}}\n'
        )
        # The tool writes its own file; reading it back through the
        # executor is what makes a replay materialize it - the same
        # parity every self-writing collector keeps.
        collapsed = executor.run(["/bin/cat", str(raw)])
        if collapsed.exit_code == 0 and collapsed.stdout is not None:
            raw.write_text(collapsed.stdout)
        witnessed = executor.run(["/bin/cat", str(exit_file)])
        if witnessed.exit_code == 0 and (witnessed.stdout or "").strip().isdigit():
            return int(witnessed.stdout.strip()), []
        # No witness file: py-spy failed before the application ran -
        # its own exit code is the best remaining evidence.
        return record.exit_code, [
            Degradation(
                name="python-sampling-failed",
                message="py-spy wrote no exit witness: the application "
                "may not have run",
                remedy="py-spy's messages above say more",
            )
        ]


def locate(executor: Executor, config: Config) -> tuple[PySpyAdapter, str] | None:
    """The usable py-spy and its version, None without one.

    `tools.py-spy` in nunatak.toml replaces the default entirely; the
    bare name otherwise resolves on the executor's PATH - pip installs
    land in too many prefixes for a fixed path to exist.
    """
    adapter = PySpyAdapter(path=config.tools.get("py-spy", "py-spy"))
    version = adapter.detect(executor)
    if version is None:
        return None
    return adapter, version
