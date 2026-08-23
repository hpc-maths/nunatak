"""Persistence: the advice lives in the Run directory, apart from the pivot.

An Explanation is not reproducible, so unlike the Diagnostic - always
recomputed - it must be persisted, and unlike a Measurement it must
never sit among the facts: it gets its own file at the Run's root,
labeled advice, replaced wholesale on regeneration. The withheld
Hotspots and their reasons are NOT stored: they are a pure function of
the pivot, recomputed by whoever renders them, like the Diagnostic.

Each entry is keyed by the Hotspot's logical identity - what survives
recompilation and names the same code in the report - and carries the
model and provider that actually answered: advice without its author
could not be weighed by the reader.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path

from nunatak.explain.generate import Explanation

FILE = "explanations.json"

# Version of the stored shape, gated on read: a report must not render
# a file written by a future nunatak it does not understand.
SCHEMA = 1


def write(directory: Path, explanations: list[Explanation]) -> Path:
    """Write the advice file of a Run, replacing any previous one."""
    path = Path(directory) / FILE
    payload = {
        "format": {"name": "nunatak-explanations", "schema": SCHEMA, "label": "advice"},
        "generated": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "explanations": [
            {
                "hotspot": {
                    "module": e.hotspot.logical_identity.module,
                    "name": e.hotspot.logical_identity.name,
                    "source_file": e.hotspot.logical_identity.source_file,
                },
                "advice": e.advice,
                "model": e.model,
                "provider": e.provider,
            }
            for e in explanations
        ],
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    return path


def read(directory: Path) -> dict | None:
    """The advice file of a Run, None when absent or not understood.

    An unreadable or future-schema file is treated as absent rather
    than rendered wrong: the Run keeps its Diagnostic either way.
    """
    path = Path(directory) / FILE
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    form = payload.get("format", {}) if isinstance(payload, dict) else {}
    if form.get("name") != "nunatak-explanations" or form.get("schema") != SCHEMA:
        return None
    return payload
