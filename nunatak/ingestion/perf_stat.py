"""Parser for `perf stat -x,` CSV output - the counting layer's format.

Fixtures in the tests are the verbatim output of perf 6.14.11 on an AMD
EPYC 7702: value, unit, event, counter runtime in nanoseconds, coverage
percentage, then derived columns this parser ignores. A `-o` file opens
with a `# started on ...` comment. `<not supported>` in the value column
states the counter does not exist on this machine - which is a fact to
keep, never a zero.
"""

from __future__ import annotations

from dataclasses import dataclass

# perf reports task-clock in milliseconds; the pivot's clocks are in
# nanoseconds, like the sampling layer's time base.
_CLOCK_SCALE = {"msec": 1e6}
_CLOCKS = {"task-clock", "cpu-clock"}


@dataclass(frozen=True)
class Count:
    """One counted event: a value over the whole process, or its absence.

    `coverage` is `time_running / time_enabled` as a fraction; counting
    three events on hardware with more counters than that does not
    multiplex, but the column is authoritative, not our assumption.
    """

    counter: str
    value: float | None
    unit: str
    coverage: float | None


def parse(text: str) -> tuple[list[Count], list[str]]:
    """Parse `perf stat -x,` CSV into Counts.

    Returns the Counts and the lines that did not parse - the caller
    turns those into a named degradation instead of guessing.
    """
    counts: list[Count] = []
    unparsed: list[str] = []
    for line in text.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        fields = line.split(",")
        if len(fields) >= 7 and not fields[0].strip() and not fields[2]:
            # A derived-metric continuation row (`,,,,,0.08,stalled
            # cycles per insn`): no event, no count - display sugar for
            # a pair of events, not a measurement lost.
            continue
        if len(fields) < 5 or not fields[2]:
            unparsed.append(line)
            continue
        counter = fields[2].split(":")[0]
        raw, unit = fields[0], fields[1]
        try:
            coverage = float(fields[4]) / 100.0
        except ValueError:
            coverage = None
        if raw.startswith("<"):
            # `<not supported>` or `<not counted>`: an absence, not zero.
            counts.append(Count(counter=counter, value=None, unit=unit, coverage=None))
            continue
        try:
            value = float(raw)
        except ValueError:
            unparsed.append(line)
            continue
        if counter in _CLOCKS and unit in _CLOCK_SCALE:
            value, unit = value * _CLOCK_SCALE[unit], "ns"
        counts.append(
            Count(counter=counter, value=value, unit=unit or counter, coverage=coverage)
        )
    return counts, unparsed
