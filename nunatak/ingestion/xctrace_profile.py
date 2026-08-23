"""Parser for xctrace's exported time-profile table - macOS's nominal mode.

The export is reference-compressed XML: any element may carry an `id`
and later occurrences of the same value appear as `<tag ref="N"/>`, so
the reader keeps a registry and dereferences as it walks. Each row is
one sample of one Running thread: a weight in nanoseconds and a
backtrace whose frames carry absolute addresses plus, when Instruments
identified it, the loaded binary with its path, UUID and load address.

Two address conventions live in one backtrace, verified against the
`fmt` attributes: the leaf's address is the PC plus one - a tag bit,
odd on a fixed-width ISA - and the callers' are exact return addresses.
The leaf is untagged here; return addresses stay as printed, exactly
like perf's.
"""

from __future__ import annotations

import xml.etree.ElementTree as ElementTree

from nunatak.ingestion.samples import Sample


def _registry(root: ElementTree.Element) -> dict[str, ElementTree.Element]:
    """Every element carrying an `id`, keyed by it."""
    return {
        element.get("id"): element
        for element in root.iter()
        if element.get("id") is not None
    }


def _deref(
    element: ElementTree.Element | None,
    registry: dict[str, ElementTree.Element],
) -> ElementTree.Element | None:
    """The element itself, or the one its `ref` names."""
    if element is None:
        return None
    reference = element.get("ref")
    return registry.get(reference) if reference is not None else element


def _frame_location(
    frame: ElementTree.Element,
    registry: dict[str, ElementTree.Element],
    leaf: bool,
) -> tuple[str, int | None]:
    """(module, offset) of one dereferenced frame.

    A frame without a binary is a mapping Instruments could not
    identify: its hex name stands as the module, offsetless -
    unresolved by design, like a pseudo module."""
    address = int(frame.get("addr"), 16)
    if leaf:
        address -= 1
    binary = _deref(frame.find("binary"), registry)
    if binary is None:
        return frame.get("name", "?"), None
    return binary.get("path"), address - int(binary.get("load-addr"), 16)


def parse(text: str) -> tuple[list[Sample], dict[str, str], list[str]]:
    """Parse one exported time-profile table into Samples.

    Returns (samples, module identities, unparsed row descriptions).
    Identities map each identified binary's path to its Mach-O UUID.
    An unreadable document is one unparsed entry and nothing else:
    refusing the whole export is better than guessing at half of it.
    """
    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError as error:
        return [], {}, [f"unreadable export: {error}"]
    registry = _registry(root)
    identities = {
        binary.get("path"): binary.get("UUID")
        for binary in root.iter("binary")
        if binary.get("path") is not None and binary.get("UUID") is not None
    }

    samples: list[Sample] = []
    unparsed: list[str] = []
    for row in root.iter("row"):
        if row.find("sentinel") is not None:
            # The recording's closing tick carries no backtrace: not a
            # sample lost, the end of the table.
            continue
        try:
            time = _deref(row.find("sample-time"), registry)
            thread = _deref(row.find("thread"), registry)
            tid = _deref(thread.find("tid"), registry)
            process = _deref(thread.find("process"), registry)
            pid = _deref(process.find("pid"), registry)
            weight = _deref(row.find("weight"), registry)
            backtrace = _deref(row.find("tagged-backtrace"), registry)
            frames = [
                _deref(frame, registry)
                for frame in _deref(backtrace.find("backtrace"), registry)
                if frame.tag == "frame"
            ]
            locations = [
                _frame_location(frame, registry, leaf=(index == 0))
                for index, frame in enumerate(frames)
            ]
            samples.append(
                Sample(
                    pid=int(pid.text),
                    tid=int(tid.text),
                    time_s=int(time.text) / 1e9,
                    period=int(weight.text),
                    counter="cpu-clock",
                    module=locations[0][0],
                    offset=locations[0][1],
                    callers=tuple(locations[1:]),
                )
            )
        except (AttributeError, IndexError, TypeError, ValueError) as error:
            unparsed.append(f"row {len(samples) + len(unparsed)}: {error}")
    return samples, identities, unparsed
