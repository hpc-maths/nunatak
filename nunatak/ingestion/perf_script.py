"""Parser for `perf script` sample lines, perf 6.4 and newer.

The adapter requests the explicit field list
`comm,pid,tid,time,period,event,ip,sym,symoff,dso,dsoff`. Without call
stacks that yields one line per sample::

    workload  4013/4013  136.565152: 1003009 task-clock:ppp:  aaaadcb806d0 main+0x50 (/tmp/workload+0x6d0)

With `--call-graph`, the location moves into an indented block under a
bare header, innermost frame first, one blank line closing each sample::

    workload-fp 2676193/2676193 28629340.327978:    1003009 task-clock:u:
        593e2599c1b8 main+0xf8 (/tmp/workload-fp+0x11b8)
        70b387e2a578 __libc_start_call_main+0x78 (/usr/lib/.../libc.so.6+0x2a578)

`dsoff` (the `+0x11b8` after the module path, added in perf 6.4) is the
module-relative offset the normalization requires; the absolute `ip` and
perf's own symbolization are deliberately discarded - attribution works
from `(module, offset)` and nothing else, for the hit and for every
caller above it.
"""

from __future__ import annotations

import re

from nunatak.ingestion.samples import Sample

MINIMUM_VERSION = (6, 4)

_SAMPLE = re.compile(
    r"""^\s*
    (?P<comm>.*?)\s+
    (?P<pid>\d+)/(?P<tid>\d+)\s+
    (?P<time>\d+\.\d+):\s+
    (?P<period>\d+)\s+
    (?P<event>\S+):\s+
    (?P<ip>[0-9a-fA-F]+)\s+
    (?P<symbol>.*?)\s+
    \((?P<dso>[^()]+)\)
    \s*$""",
    re.VERBOSE,
)

# The header of a call-stack sample carries no location of its own.
_HEADER = re.compile(
    r"""^\s*
    (?P<comm>.*?)\s+
    (?P<pid>\d+)/(?P<tid>\d+)\s+
    (?P<time>\d+\.\d+):\s+
    (?P<period>\d+)\s+
    (?P<event>\S+):
    \s*$""",
    re.VERBOSE,
)

# One frame of the block: indented, an absolute ip, perf's symbolization,
# the module in parentheses.
_FRAME = re.compile(
    r"""^\t\s*
    (?P<ip>[0-9a-fA-F]+)\s+
    (?P<symbol>.*?)\s+
    \((?P<dso>[^()]+)\)
    \s*$""",
    re.VERBOSE,
)


def supports(version: str) -> bool:
    """Whether this parser understands the detected perf version.

    The upper bound is open: new releases are vetted by replaying the
    corpus, not by refusing to run."""
    match = re.match(r"(\d+)\.(\d+)", version)
    if match is None:
        return False
    return (int(match.group(1)), int(match.group(2))) >= MINIMUM_VERSION


# A JIT map module, and the symbol shape CPython trampolines publish in
# it: `py::<qualified name>:<file>`, perf appending `+0x<symoff>`.
_MAP_DSO = re.compile(r"/tmp/perf-\d+\.map(\+0x[0-9a-fA-F]+)?$")
_SYMOFF = re.compile(r"\+0x[0-9a-fA-F]+$")


def _python_name(symbol: str, dso: str) -> tuple[str, str] | None:
    """The (function, file) a map frame names, None for a native frame.

    The name is kept at parse time or lost forever: the map's addresses
    belong to a JIT, they mean nothing once the process is gone.
    """
    if not _MAP_DSO.search(dso) or not symbol.startswith("py::"):
        return None
    text = _SYMOFF.sub("", symbol)[len("py::"):]
    function, separator, file = text.rpartition(":")
    if not separator:
        return None
    return function, file


def _location(dso: str) -> tuple[str, int | None]:
    """Normalize perf's `module+0xoffset` into `(module, offset)`.

    A dso without a `+0x` offset (pseudo modules such as `[vdso]`) keeps
    the module with offset None: the module is known, the position inside
    it is not.
    """
    module, plus, offset = dso.rpartition("+")
    if plus and offset.startswith("0x"):
        return module, int(offset, 16)
    return dso, None


def parse_samples(text: str):
    """Parse sample lines into `Sample` objects.

    Returns (samples, unparsed lines). Flat lines and call-stack blocks
    are both understood - a recording holds one shape or the other, the
    parser does not care. In a block, the first frame is the hit itself
    and the rest are its callers, outward.
    """
    samples = []
    unparsed = []
    pending: tuple[re.Match, str] | None = None
    frames: list[tuple[str, int | None]] = []
    python: list[tuple[int, str, str]] = []

    def close():
        if pending is None:
            return
        if frames:
            samples.append(
                _sample(
                    pending[0], *frames[0],
                    callers=tuple(frames[1:]),
                    python_frames=tuple(python),
                )
            )
        else:
            # A header whose unwind produced nothing has no location: it
            # cannot become a Sample, and swallowing it would understate
            # the unparsed count.
            unparsed.append(pending[1])

    for line in text.splitlines():
        if not line.strip():
            close()
            pending, frames, python = None, [], []
            continue
        frame = _FRAME.match(line)
        if frame is not None and pending is not None:
            named = _python_name(frame.group("symbol"), frame.group("dso"))
            if named is not None:
                python.append((len(frames), *named))
            frames.append(_location(frame.group("dso")))
            continue
        close()
        pending, frames, python = None, [], []
        match = _SAMPLE.match(line)
        if match is not None:
            module, offset = _location(match.group("dso"))
            named = _python_name(match.group("symbol"), match.group("dso"))
            samples.append(
                _sample(
                    match, module, offset,
                    python_frames=((0, *named),) if named is not None else (),
                )
            )
            continue
        header = _HEADER.match(line)
        if header is not None:
            pending = (header, line)
            continue
        unparsed.append(line)
    close()
    return samples, unparsed


def _sample(
    match: re.Match,
    module: str,
    offset: int | None,
    callers: tuple[tuple[str, int | None], ...] = (),
    python_frames: tuple[tuple[int, str, str], ...] = (),
) -> Sample:
    """Build a Sample from a matched line."""
    return Sample(
        pid=int(match.group("pid")),
        tid=int(match.group("tid")),
        time_s=float(match.group("time")),
        period=int(match.group("period")),
        counter=match.group("event").split(":")[0],
        module=module,
        offset=offset,
        callers=callers,
        python_frames=python_frames,
    )


def parse_buildid_list(text: str) -> dict[str, str]:
    """Parse `perf buildid-list` output: `<build-id> <module path>` lines."""
    module_ids = {}
    for line in text.splitlines():
        parts = line.split(maxsplit=1)
        if len(parts) == 2:
            module_ids[parts[1].strip()] = parts[0]
    return module_ids
