"""Source resolution and extraction: from persisted chains to code extracts.

A file named by DWARF is searched in three steps: the recorded path as
it is, then the user-supplied source map (`/build/x=/home/me/x`), then a
basename search under the repository root or the working directory. On
multiple ambiguous matches nunatak does not choose: the Hotspot stays
without source, with the reason - a wrong file shown confidently would
be worse than none.

Only the necessary extracts are embedded in the Run, never whole files:
the body of the physical function and its hot inline frames, a few
context lines around. The true end of a function is not in the line
table, so an extract runs from the earliest declaration to the last
sampled line, plus context, and its size is capped with the truncation
marked.
"""

from __future__ import annotations

import os
from pathlib import Path

from nunatak.pivot import AddressDetail, SourceExtract

CONTEXT_LINES = 3
MAX_EXTRACT_LINES = 200

# Directories a basename search never enters: hidden trees and the Runs.
_SKIPPED_DIRS = {".nunatak"}


def _wanted(details: list[AddressDetail]) -> dict[tuple, list]:
    """The line ranges worth extracting, keyed by (Hotspot, file).

    Every frame of every sampled address contributes: the physical
    function and the inline frames of one file merge into one range, a
    frame inlined from a header yields a separate extract of that header.
    """
    wanted: dict[tuple, list] = {}
    for detail in details:
        for frame in detail.frames:
            if frame.file is None:
                continue
            lines = [n for n in (frame.line, frame.declaration_line) if n]
            if not lines:
                continue
            entry = wanted.setdefault((detail.hotspot, frame.file), [min(lines), max(lines)])
            entry[0] = min(entry[0], *lines)
            entry[1] = max(entry[1], *lines)
    return wanted


def _find_by_basename(names: set[str], root: Path) -> dict[str, list[Path]]:
    """One walk under `root` collecting every file whose basename is in
    `names` - a single pass whatever the number of files to resolve."""
    matches: dict[str, list[Path]] = {name: [] for name in names}
    for directory, subdirectories, files in os.walk(root):
        subdirectories[:] = [
            d for d in subdirectories if not d.startswith(".") and d not in _SKIPPED_DIRS
        ]
        for name in names & set(files):
            matches[name].append(Path(directory) / name)
    return matches


def _resolve(
    files: set[str], source_map: dict[str, str], root: Path
) -> dict[str, tuple[Path | None, str | None]]:
    """Locate each DWARF path on this machine: (resolved path, reason).

    Exactly one of the two is set. The longest source-map prefix wins,
    so `/build/app/sub=` can override `/build/app=`.
    """
    resolved: dict[str, tuple[Path | None, str | None]] = {}
    needing_search: set[str] = set()

    for file in files:
        path = Path(file)
        if path.is_file():
            resolved[file] = (path, None)
            continue
        for prefix in sorted(source_map, key=len, reverse=True):
            if file.startswith(prefix):
                mapped = Path(source_map[prefix] + file[len(prefix) :])
                if mapped.is_file():
                    resolved[file] = (mapped, None)
                    break
        else:
            needing_search.add(file)

    by_basename = _find_by_basename(
        {os.path.basename(f) for f in needing_search}, root
    )
    for file in needing_search:
        candidates = by_basename[os.path.basename(file)]
        if len(candidates) == 1:
            resolved[file] = (candidates[0], None)
        elif candidates:
            resolved[file] = (
                None,
                f"ambiguous: {len(candidates)} files named "
                f"'{os.path.basename(file)}' under {root}",
            )
        else:
            resolved[file] = (None, "source file not found on this machine")
    return resolved


def _extract(path: Path, start: int, end: int) -> tuple[str, int, int, bool] | None:
    """Read lines [start, end] of `path` (1-based, bounds clamped), capped
    at MAX_EXTRACT_LINES; None when the file cannot be read after all."""
    try:
        lines = path.read_text(errors="replace").splitlines()
    except OSError:
        return None
    start = max(1, start)
    end = min(len(lines), end)
    truncated = end - start + 1 > MAX_EXTRACT_LINES
    if truncated:
        end = start + MAX_EXTRACT_LINES - 1
    return "\n".join(lines[start - 1 : end]), start, end, truncated


def extract(
    details: list[AddressDetail], source_map: dict[str, str], root: Path
) -> list[SourceExtract]:
    """The source extracts of the named Hotspots in `details`.

    One extract per (Hotspot, file), from a few lines before the earliest
    declaration to a few lines after the last sampled line. A file that
    cannot be resolved yields an extract without text, carrying the
    reason.
    """
    wanted = _wanted(details)
    resolved = _resolve({file for _, file in wanted}, source_map, root)

    extracts = []
    for (hotspot, file), (first, last) in wanted.items():
        path, reason = resolved[file]
        if path is None:
            extracts.append(SourceExtract(hotspot=hotspot, file=file, reason=reason))
            continue
        content = _extract(path, first - CONTEXT_LINES, last + CONTEXT_LINES)
        if content is None:
            extracts.append(
                SourceExtract(
                    hotspot=hotspot,
                    file=file,
                    resolved_path=str(path),
                    reason="source file not readable",
                )
            )
            continue
        text, start, end, truncated = content
        extracts.append(
            SourceExtract(
                hotspot=hotspot,
                file=file,
                resolved_path=str(path),
                start_line=start,
                end_line=end,
                text=text,
                truncated=truncated,
            )
        )
    extracts.sort(
        key=lambda e: (
            e.hotspot.logical_identity.module,
            e.hotspot.display_name,
            e.file,
        )
    )
    return extracts
