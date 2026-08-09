"""The unit sampling collectors produce, whatever the tool."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Sample:
    """One sampling hit, already normalized to a module-relative offset."""

    pid: int
    tid: int
    time_s: float
    period: int
    counter: str
    module: str
    offset: int | None
