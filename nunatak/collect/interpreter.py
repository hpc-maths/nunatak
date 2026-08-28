"""The interpreted application: CPython through perf's trampolines.

From 3.12 on, CPython can JIT a small trampoline per Python function
and publish it in a perf map - the one door through which perf sees
Python frames inside native call stacks, with no line of the
application touched: `PYTHONPERFSUPPORT=1` in the launch environment is
the whole mechanism. Anything else that writes a perf map (Numba, a
JIT) enters through the same door with no code of its own here.

Detection keys on the interpreter being named in the command -
`python3 script.py`, also behind an MPI launcher - because argv is the
only witness a replay can reproduce: a shebang lives in a file that no
longer exists where the corpus replays. The version crosses the
execution boundary for the same reason - the decision it drives must
replay identically on hosts with other Pythons.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from nunatak.collect.execution import Executor
from nunatak.launch import real_target

# The first CPython that ships perf trampolines.
TRAMPOLINES = (3, 12)

_INTERPRETER = re.compile(r"^python(\d+(\.\d+)*)?$")
_VERSION = re.compile(r"Python (\d+)\.(\d+)")


@dataclass(frozen=True)
class PythonTarget:
    """A profiled application that is a CPython program."""

    interpreter: str
    version: tuple[int, int]

    @property
    def trampolines(self) -> bool:
        """Whether this CPython can expose Python frames to perf."""
        return self.version >= TRAMPOLINES

    @property
    def release(self) -> str:
        """The version as people write it."""
        return f"{self.version[0]}.{self.version[1]}"


def detect(executor: Executor, command: list[str]) -> PythonTarget | None:
    """The CPython application behind `command`, None for a native one.

    The interpreter answers for its own version - a banner, exactly like
    every other tool at the boundary - so the verdict a Run was recorded
    with is the verdict it replays with.
    """
    target = real_target(list(command)) or (command[0] if command else None)
    if target is None or not _INTERPRETER.fullmatch(os.path.basename(target)):
        return None
    banner = executor.run([target, "--version"])
    if banner.exit_code != 0:
        return None
    matched = _VERSION.search((banner.stdout or "") + (banner.stderr or ""))
    if matched is None:
        return None
    return PythonTarget(
        interpreter=target, version=(int(matched[1]), int(matched[2]))
    )


def environment(base: dict | None = None) -> dict:
    """The collection environment of a trampoline-capable target.

    A full environment, not the one variable: what the executor receives
    replaces the process environment entirely, and an application
    launched without PATH or HOME would be measured failing, not
    running.
    """
    composed = dict(os.environ if base is None else base)
    composed["PYTHONPERFSUPPORT"] = "1"
    return composed
