"""Recording corpus: capture once on real hardware, replay forever without.

The corpus is captured, never hand-written: a hand-written corpus only
tests the idea we have of tool outputs, never the real ones.
nunatak produces it itself: `RecordingExecutor` wraps the real executor
during a run on real hardware and saves every invocation crossing the
execution boundary; `ReplayExecutor` substitutes those recordings for the
real tools, which is what makes adapters substitutable by a source of
recordings.

Entry layout::

    entry/
      meta.json               command, platform, collectors, versions
      invocations/000.json    argv, exit code, whether output was captured
      invocations/000.stdout  raw captured output (absent when not captured)
      invocations/000.stderr
"""

from __future__ import annotations

import collections
import datetime
import json
import os
import platform
from pathlib import Path

import nunatak
from nunatak.collect.execution import Executor, Invocation
from nunatak.exit_codes import COMMAND_NOT_FOUND

META = "meta.json"
INVOCATIONS = "invocations"


def write_meta(entry: Path, command: list[str], collectors: list[dict]) -> None:
    """Describe a corpus entry: what ran, where, with which collectors."""
    meta = {
        "created": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "command": command,
        "nunatak_version": nunatak.__version__,
        "platform": {
            "system": platform.system(),
            "kernel": platform.release(),
            "architecture": platform.machine(),
        },
        "collectors": collectors,
    }
    (entry / META).write_text(json.dumps(meta, indent=2) + "\n")


def read_meta(entry: Path) -> dict:
    """Load the description of a corpus entry."""
    return json.loads((entry / META).read_text())


class RecordingExecutor(Executor):
    """Wraps the real executor and records every invocation, in order."""

    def __init__(self, inner: Executor, entry: Path):
        self.inner = inner
        self.entry = Path(entry)
        directory = self.entry / INVOCATIONS
        directory.mkdir(parents=True, exist_ok=True)
        if any(directory.iterdir()):
            raise ValueError(f"corpus entry {self.entry} already contains invocations")
        self._counter = 0

    def run(self, argv, capture=True, env=None, cwd=None):
        """Run through the wrapped executor and persist the invocation."""
        invocation = self.inner.run(argv, capture=capture, env=env, cwd=cwd)
        stem = self.entry / INVOCATIONS / f"{self._counter:03d}"
        self._counter += 1
        stem.with_suffix(".json").write_text(
            json.dumps(
                {
                    "argv": list(invocation.argv),
                    "exit_code": invocation.exit_code,
                    "captured": capture,
                },
                indent=2,
            )
            + "\n"
        )
        if capture:
            stem.with_suffix(".stdout").write_text(invocation.stdout or "")
            stem.with_suffix(".stderr").write_text(invocation.stderr or "")
        return invocation


class ReplayExecutor(Executor):
    """Substitutes recordings for the real tools.

    Invocations are matched by program base name, in recorded order (one
    FIFO queue per program): absolute paths legitimately differ between the
    recording machine and the replaying one. A program the entry never
    recorded is reported absent - a corpus entry declares what existed.
    """

    def __init__(self, entry: Path):
        self.entry = Path(entry)
        self.meta = read_meta(self.entry)
        self._queues: dict[str, collections.deque] = collections.defaultdict(
            collections.deque
        )
        for record in sorted((self.entry / INVOCATIONS).glob("*.json")):
            self._queues[os.path.basename(json.loads(record.read_text())["argv"][0])].append(
                record
            )

    @property
    def system(self) -> str:
        """The recorded platform, not the replaying machine's."""
        return self.meta["platform"]["system"]

    def run(self, argv, capture=True, env=None, cwd=None):
        """Serve the next recording for this program instead of running it."""
        queue = self._queues.get(os.path.basename(argv[0]))
        if not queue:
            return Invocation(
                argv=tuple(argv),
                exit_code=COMMAND_NOT_FOUND,
                stderr=f"{argv[0]}: not recorded in corpus entry {self.entry}",
            )
        record_path = queue.popleft()
        record = json.loads(record_path.read_text())
        stdout = stderr = None
        if capture and record["captured"]:
            stdout = record_path.with_suffix(".stdout").read_text()
            stderr = record_path.with_suffix(".stderr").read_text()
        return Invocation(
            argv=tuple(argv),
            exit_code=record["exit_code"],
            stdout=stdout,
            stderr=stderr,
        )
