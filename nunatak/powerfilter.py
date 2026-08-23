"""`python -m nunatak.powerfilter <name>`: slim the powermetrics stream.

powermetrics has no task filter, and under a profiler its plist samples
enumerate every process on the machine - two megabytes per sample,
measured, of which nunatak consumes a few hundred bytes: the package
energies and the tasks bearing the profiled command's name. This filter
sits in the rider's pipe and keeps exactly that, one reduced plist per
sample, NUL-separated like the original stream.

Standard library only, like the rank shim, and for the same reason: it
runs inside the launch wrapper, where nothing beyond the interpreter is
guaranteed. Killing it is the rider's teardown - it is the user's
process where powermetrics is root's - and powermetrics follows on the
broken pipe. A partial trailing sample is dropped: it was cut mid-write
by that teardown, not lost.
"""

from __future__ import annotations

import plistlib
import sys

_TASK_FIELDS = ("pid", "name", "energy_impact", "cputime_ns")
_PROCESSOR_FIELDS = ("cpu_energy", "gpu_energy", "ane_energy")


def reduced(chunk: bytes, name: str) -> bytes | None:
    """One sample, kept fields only; None when the chunk is not a plist."""
    try:
        sample = plistlib.loads(chunk)
    except Exception:
        return None
    processor = sample.get("processor", {})
    kept = {
        "elapsed_ns": sample.get("elapsed_ns", 0),
        "processor": {
            field: processor[field]
            for field in _PROCESSOR_FIELDS
            if field in processor
        },
        "tasks": [
            {field: task[field] for field in _TASK_FIELDS if field in task}
            for task in sample.get("tasks", ())
            if task.get("name") == name
        ],
    }
    return plistlib.dumps(kept, fmt=plistlib.FMT_XML)


def main() -> int:
    """Filter stdin's NUL-separated samples onto stdout, flushed per
    sample so the file holds every completed one at teardown time."""
    name = sys.argv[1]
    buffer = b""
    stdin = sys.stdin.buffer
    stdout = sys.stdout.buffer
    while True:
        block = stdin.read(65536)
        if not block:
            break
        buffer += block
        while b"\x00" in buffer:
            chunk, buffer = buffer.split(b"\x00", 1)
            if not chunk.strip():
                continue
            slim = reduced(chunk, name)
            if slim is not None:
                stdout.write(slim)
                stdout.write(b"\x00")
                stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
