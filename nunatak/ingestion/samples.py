"""The unit sampling collectors produce, whatever the tool."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Sample:
    """One sampling hit, already normalized to a module-relative offset.

    `callers` is the recorded call stack above the hit, outward - the
    direct caller first - each frame normalized to `(module, offset)`
    like the hit itself. Empty when the recording carried no stacks:
    absence of evidence, never a claim that the function has no caller.
    """

    pid: int
    tid: int
    time_s: float
    period: int
    counter: str
    module: str
    offset: int | None
    callers: tuple[tuple[str, int | None], ...] = ()
