"""Parser for /usr/bin/sample's call-graph report - macOS's temporal mode.

The report is a self-symbolicated call tree: each node carries a hit
count, a symbol, its module and one or more absolute addresses, and the
Binary Images section maps addresses back to module-relative offsets.
Two shapes of honesty are decided here rather than upstream:

- A node's own weight is its count minus its children's - the hits that
  ended in the node itself - so interior frames keep their self time
  exactly like perf's leaf-based samples.
- A leaf that aggregated many addresses prints them elided
  (`+ 100,92,...`): the first address anchors the whole count. The
  per-address distribution inside a function is not recoverable from
  this report, which is the function-grained resolution the platform's
  degraded mode announces.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from nunatak.ingestion.samples import Sample

REPORT_VERSIONS = {7}

_ANALYSIS = re.compile(
    r"^Analysis of sampling .* \(pid (?P<pid>\d+)\) "
    r"every (?P<interval>\d+) millisecond"
)
_VERSION = re.compile(r"^Report Version:\s+(\d+)")

# One call-tree node: a sibling gutter, a hit count, then the fields
# separated by two spaces. Aggregated leaves elide offsets and
# addresses with a literal `...`.
_NODE = re.compile(
    r"^(?P<gutter>[ +!:|]*)(?P<count>\d+) (?P<rest>.*\S)\s*$"
)
_FRAME = re.compile(
    r"^(?P<symbol>.+?)  \(in (?P<module>[^)]+)\)"
    r"(?: \+ (?P<offsets>[0-9,.]+))?"
    r"  \[(?P<addresses>[0-9a-fx,.]+)\]"
    r"(?:  \S+:\d+)?$"
)
_THREAD = re.compile(r"^Thread_(?P<tid>\d+)")

_IMAGE = re.compile(
    r"^\s+(?P<start>0x[0-9a-f]+)\s+-\s+(?P<end>0x[0-9a-f]+)\s+"
    r"(?P<main>\+?)(?P<name>\S+)\s+\(.*?\)\s+<(?P<uuid>[0-9A-Fa-f-]+)>\s+"
    r"(?P<path>.+?)\s*$"
)


@dataclass(frozen=True)
class Image:
    """One loaded binary: its address range, its Mach-O UUID - the
    platform's build-id - and where it lives on disk."""

    start: int
    end: int
    main: bool
    name: str
    uuid: str
    path: str


@dataclass
class _Node:
    """One open tree node while walking: its location and what its
    children have consumed of its count."""

    column: int
    count: int
    location: tuple[str, int | None]
    children: int = 0
    ancestors: tuple[tuple[str, int | None], ...] = field(default_factory=tuple)


def _images(lines: list[str]) -> list[Image]:
    """The Binary Images table, address-sorted."""
    images = []
    for line in lines:
        match = _IMAGE.match(line)
        if match:
            images.append(
                Image(
                    start=int(match.group("start"), 16),
                    end=int(match.group("end"), 16),
                    main=match.group("main") == "+",
                    name=match.group("name"),
                    uuid=match.group("uuid"),
                    path=match.group("path"),
                )
            )
    images.sort(key=lambda image: image.start)
    return images


def _module_of(image: Image, target: str | None) -> str:
    """The module path attribution will look for.

    The report redacts non-system paths (`/tmp/*/solver`), so the main
    executable's path comes from the launch command instead - the one
    path the Run knows for certain.
    """
    if image.main and target is not None:
        return target
    return image.path


def _locate(
    address: int, images: list[Image], target: str | None, printed: str
) -> tuple[str, int | None]:
    """(module, offset) of one absolute address via the image ranges;
    the printed module name with no offset when no range covers it."""
    for image in images:
        if image.start <= address <= image.end:
            return _module_of(image, target), address - image.start
    return printed, None


def parse(
    text: str, target: str | None = None
) -> tuple[list[Sample], dict[str, str], int | None, list[str]]:
    """Parse one sample report into Samples.

    Returns (samples, module identities, report version, unparsed
    lines). Each tree node contributes its self count - count minus
    children - as that many hits at its first address, callers outward
    like perf's blocks. Module identities map each image's module to
    its Mach-O UUID, the platform's build-id. The report version rides
    along so the caller can refuse a format this parser never saw,
    instead of parsing it by luck.
    """
    lines = text.splitlines()
    images = _images(lines)
    pid, interval_ms, version = 0, 1, None
    samples: list[Sample] = []
    unparsed: list[str] = []

    for line in lines:
        match = _ANALYSIS.match(line)
        if match:
            pid = int(match.group("pid"))
            interval_ms = int(match.group("interval"))
        match = _VERSION.match(line)
        if match:
            version = int(match.group(1))

    def emit(node: _Node, tid: int) -> None:
        own = node.count - node.children
        if own <= 0:
            return
        module, offset = node.location
        samples.extend(
            Sample(
                pid=pid,
                tid=tid,
                time_s=0.0,
                period=interval_ms * 1_000_000,
                counter="wall-clock",
                module=module,
                offset=offset,
                callers=node.ancestors,
            )
            for _ in range(own)
        )

    identities = {
        _module_of(image, target): image.uuid for image in images
    }
    try:
        begin = lines.index("Call graph:") + 1
    except ValueError:
        return [], identities, version, ["no call graph section"]
    stack: list[_Node] = []
    tid = 0
    for line in lines[begin:]:
        if not line.strip():
            continue
        if line.startswith(("Total number in stack", "Binary Images:", "Sort by top")):
            break
        match = _NODE.match(line)
        if match is None:
            unparsed.append(line)
            continue
        column = len(match.group("gutter"))
        while stack and stack[-1].column >= column:
            emit(stack.pop(), tid)
        rest = match.group("rest")
        thread = _THREAD.match(rest)
        if thread is not None:
            while stack:
                emit(stack.pop(), tid)
            tid = int(thread.group("tid"))
            continue
        frame = _FRAME.match(rest)
        if frame is None:
            unparsed.append(line)
            continue
        address = int(frame.group("addresses").split(",")[0], 16)
        location = _locate(address, images, target, frame.group("module"))
        count = int(match.group("count"))
        if stack:
            stack[-1].children += count
        ancestors = (
            (stack[-1].location, *stack[-1].ancestors) if stack else ()
        )
        stack.append(
            _Node(column=column, count=count, location=location, ancestors=ancestors)
        )
    while stack:
        emit(stack.pop(), tid)
    return samples, identities, version, unparsed
