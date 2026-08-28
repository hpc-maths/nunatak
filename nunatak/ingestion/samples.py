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

    `python_frames` names the Python frames a JIT map identified inside
    this sample, as `(position, function, file)` - position 0 the hit
    itself, position n the n-th caller. The names exist only in the
    collector's text: the map's addresses are JIT-ephemeral, and nothing
    can re-symbolize them once the process is gone.
    """

    pid: int
    tid: int
    time_s: float
    period: int
    counter: str
    module: str
    offset: int | None
    callers: tuple[tuple[str, int | None], ...] = ()
    python_frames: tuple[tuple[int, str, str], ...] = ()
