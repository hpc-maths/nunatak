"""Parser for `perf script` sample lines, perf 6.4 and newer.

The adapter requests the explicit field list
`comm,pid,tid,time,period,event,ip,sym,symoff,dso,dsoff`, which yields one
line per sample::

    workload  4013/4013  136.565152: 1003009 task-clock:ppp:  aaaadcb806d0 main+0x50 (/tmp/workload+0x6d0)

`dsoff` (the `+0x6d0` after the module path, added in perf 6.4) is the
module-relative offset the normalization requires; the absolute `ip` and
perf's own symbolization are deliberately discarded - attribution works
from `(module, offset)` and nothing else.
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


def supports(version: str) -> bool:
    """Whether this parser understands the detected perf version.

    The upper bound is open: new releases are vetted by replaying the
    corpus, not by refusing to run."""
    match = re.match(r"(\d+)\.(\d+)", version)
    if match is None:
        return False
    return (int(match.group(1)), int(match.group(2))) >= MINIMUM_VERSION


def parse_samples(text: str):
    """Parse sample lines into `Sample` objects.

    Returns (samples, unparsed lines). A dso without a `+0x` offset (pseudo
    modules such as `[vdso]`) yields a sample with offset None: the module
    is known, the position inside it is not.
    """
    samples = []
    unparsed = []
    for line in text.splitlines():
        if not line.strip():
            continue
        match = _SAMPLE.match(line)
        if match is None:
            unparsed.append(line)
            continue
        module, plus, offset = match.group("dso").rpartition("+")
        if plus and offset.startswith("0x"):
            samples.append(_sample(match, module, int(offset, 16)))
        else:
            samples.append(_sample(match, match.group("dso"), None))
    return samples, unparsed


def _sample(match: re.Match, module: str, offset: int | None) -> Sample:
    """Build a Sample from a matched line."""
    return Sample(
        pid=int(match.group("pid")),
        tid=int(match.group("tid")),
        time_s=float(match.group("time")),
        period=int(match.group("period")),
        counter=match.group("event").split(":")[0],
        module=module,
        offset=offset,
    )


def parse_buildid_list(text: str) -> dict[str, str]:
    """Parse `perf buildid-list` output: `<build-id> <module path>` lines."""
    module_ids = {}
    for line in text.splitlines():
        parts = line.split(maxsplit=1)
        if len(parts) == 2:
            module_ids[parts[1].strip()] = parts[0]
    return module_ids
