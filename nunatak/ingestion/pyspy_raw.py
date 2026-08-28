"""Parser for py-spy's raw collapsed stacks, py-spy 0.4.

One line per distinct stack::

    process 3732039:"";process 3732041:"python3 hot.py";<module> (hot.py:19);main (hot.py:16);axpy (hot.py:5) 54

Frames run outermost first, `;`-separated, each `name (file:line)`; the
trailing integer aggregates the samples that saw this exact stack.
`--subprocesses` prefixes `process <pid>:"<command>"` frames - the
wrapper shell first, then the interpreter - which locate the stack but
are not code.

The lines become ordinary Samples whose frames are all Python: the
ingestion's folding then produces the same `(file, function)` Hotspots
the trampoline path yields, and the stacks carry their names. One
Sample per aggregated hit keeps the statistical floor honest.
"""

from __future__ import annotations

import re

from nunatak.ingestion.samples import Sample

# py-spy versions this parser understands, by major.minor.
SUPPORTED = {"0.4"}

_FRAME = re.compile(r"^(?P<name>.*) \((?P<file>.+):(?P<line>\d+)\)$")
_PROCESS = re.compile(r'^process (?P<pid>\d+):"(?P<command>.*)"$')


def supports(version: str) -> bool:
    """Whether this parser understands the detected py-spy version."""
    return ".".join(version.split(".")[:2]) in SUPPORTED


def parse_samples(text: str, rate: int) -> tuple[list[Sample], list[str]]:
    """Parse collapsed lines into Samples; returns (samples, unparsed).

    Each aggregated line is emitted once per hit it counted, every
    frame carried as a Python frame: position 0 is the innermost -
    the hit - exactly as the trampoline path orders them.
    """
    period = int(round(1e9 / rate)) if rate > 0 else 0
    samples: list[Sample] = []
    unparsed: list[str] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        stack, _, count_text = line.rpartition(" ")
        if not count_text.isdigit() or not stack:
            unparsed.append(line)
            continue
        pid = 0
        saw_process = False
        frames: list[tuple[str, str]] = []
        recognized = True
        for token in stack.split(";"):
            process = _PROCESS.match(token)
            if process is not None:
                saw_process = True
                pid = int(process.group("pid"))
                continue
            frame = _FRAME.match(token)
            if frame is None:
                recognized = False
                break
            frames.append((frame.group("name"), frame.group("file")))
        if recognized and saw_process and not frames:
            # A watched process with no Python stack: the exit-witness
            # shell py-spy rides over. Scaffolding, not code.
            continue
        if not recognized or not frames:
            unparsed.append(line)
            continue
        innermost_first = list(reversed(frames))
        sample = Sample(
            pid=pid,
            tid=pid,
            time_s=0.0,
            period=period,
            counter="cpu-clock",
            module=innermost_first[0][1],
            offset=None,
            callers=tuple((file, None) for _, file in innermost_first[1:]),
            python_frames=tuple(
                (position, name, file)
                for position, (name, file) in enumerate(innermost_first)
            ),
        )
        samples.extend([sample] * int(count_text))
    return samples, unparsed
