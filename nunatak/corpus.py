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
import threading
from pathlib import Path

import nunatak
from nunatak.collect.execution import Executor, Invocation
from nunatak.exit_codes import COMMAND_NOT_FOUND

META = "meta.json"
INVOCATIONS = "invocations"


def write_meta(
    entry: Path,
    command: list[str],
    collectors: list[dict],
    sampling_blocked: str | None = None,
    cpu_model: str | None = None,
    cpuinfo: str | None = None,
) -> None:
    """Describe a corpus entry: what ran, where, with which collectors.

    `sampling_blocked` and `cpu_model` preserve the recording machine's
    verdicts, so a replay takes the same path the recording took: an
    entry captured where sampling was denied must not replay as if it
    were allowed - it would ask for collector invocations the entry
    never recorded - and a processor-keyed decision (the call-stack
    ladder's lbr rung) must not follow the replaying machine's vendor.
    """
    meta = {
        "created": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "command": command,
        "nunatak_version": nunatak.__version__,
        "platform": {
            "system": platform.system(),
            "kernel": platform.release(),
            "architecture": platform.machine(),
        },
        "sampling_blocked": sampling_blocked,
        "cpu_model": cpu_model,
        "cpuinfo": cpuinfo,
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
        # Explanations cross the boundary in parallel: the numbering must
        # stay one-invocation-one-slot under concurrent calls.
        self._lock = threading.Lock()

    def sampling_blocked(self):
        """The recording machine's verdict: sampling happens on real hardware."""
        return self.inner.sampling_blocked()

    def cpu_model(self):
        """The recording machine's processor, preserved into the meta."""
        return self.inner.cpu_model()

    def cpuinfo(self):
        """The recording machine's identification block, for the meta."""
        return self.inner.cpuinfo()

    def run(self, argv, capture=True, env=None, cwd=None, on_line=None):
        """Run through the wrapped executor and persist the invocation."""
        invocation = self.inner.run(
            argv, capture=capture, env=env, cwd=cwd, on_line=on_line
        )
        with self._lock:
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
        # Same concurrency as the recording side: parallel explanation
        # calls must each pop exactly one recording.
        self._lock = threading.Lock()

    @property
    def system(self) -> str:
        """The recorded platform, not the replaying machine's."""
        return self.meta["platform"]["system"]

    def sampling_blocked(self):
        """The recording machine's verdict, never the replaying one's.

        An entry captured where sampling was denied must replay down the
        same degraded path: deciding "allowed" here would ask for
        collector invocations the entry never recorded. Entries written
        before the verdict was kept read back as unblocked - the real
        corpus was captured with sampling working.
        """
        return self.meta.get("sampling_blocked")

    def cpu_model(self):
        """The recorded processor, never the replaying machine's.

        The call-stack ladder keys its lbr rung on the vendor: read
        live, one entry would take different paths on different replay
        hosts. Entries written before the model was kept read back as
        unknown - the honest value for a recording that never said.
        """
        return self.meta.get("cpu_model")

    def cpuinfo(self):
        """The recorded identification block, never the replaying host's.

        The pass structure of a multi-pass run derives from it: read
        live, an entry recorded on Zen 2 would build different passes -
        or none - on every other CI host. Older entries read back as
        unknown."""
        return self.meta.get("cpuinfo")

    def run(self, argv, capture=True, env=None, cwd=None, on_line=None):
        """Serve the next recording for this program instead of running it.

        A streaming caller gets the recorded lines through its callback:
        the display path replays exactly like the parsing path.
        """
        with self._lock:
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
            if on_line is not None:
                for line in stdout.splitlines():
                    on_line(line)
        return Invocation(
            argv=tuple(argv),
            exit_code=record["exit_code"],
            stdout=stdout,
            stderr=stderr,
        )
