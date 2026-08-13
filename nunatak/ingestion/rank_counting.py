"""Ingestion of the counting layer: per-rank aggregates into the pivot.

Each rank directory under `collect/` was written by the rank shim on the
rank's own node: a `rank.json` identity and, when perf was there, a
`perf stat` CSV. The Measurements produced here are Locus-level - one
value per (node, rank), no Hotspot: the counting layer has nothing to
attribute, and that is what lets it cover every rank at constant cost.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from nunatak.ingestion import perf_stat
from nunatak.pivot import Degradation, Locus, Measurement, Quality
from nunatak.rank import RANK_META, STAT_OUTPUT

_RANK_DIR = re.compile(r"rank-(\d+)$")


def rank_metas(directory: Path) -> list[tuple[Path, dict]]:
    """The rank directories under `directory` and their identity metas,
    ordered by rank number."""
    metas = []
    for rank_dir in sorted(directory.glob("rank-*")):
        meta_path = rank_dir / RANK_META
        if _RANK_DIR.search(rank_dir.name) is None or not meta_path.is_file():
            continue
        metas.append((rank_dir, json.loads(meta_path.read_text())))
    metas.sort(key=lambda entry: entry[1]["rank"])
    return metas


def _measurements_of(meta: dict, csv_text: str) -> tuple[list[Measurement], list[str]]:
    """The Locus-level Measurements of one counted rank."""
    locus = Locus(node=meta["node"], rank=meta["rank"])
    counts, unparsed = perf_stat.parse(csv_text)
    measurements = []
    for count in counts:
        if count.value is None:
            measurements.append(
                Measurement(
                    hotspot=None,
                    locus=locus,
                    counter=count.counter,
                    value=None,
                    unit=count.unit or count.counter,
                    quality=Quality.UNAVAILABLE,
                    reason="counter not supported on this node",
                )
            )
        else:
            measurements.append(
                Measurement(
                    hotspot=None,
                    locus=locus,
                    counter=count.counter,
                    value=count.value,
                    unit=count.unit,
                    quality=Quality.MEASURED,
                    coverage=count.coverage,
                )
            )
    return measurements, unparsed


def ingest_counting(directory: Path) -> tuple[list[Measurement], list[Degradation]]:
    """Turn the rank directories under `directory` into Measurements.

    Returns an empty list for a Run without ranks - a single-process Run
    has no counting layer, which is not a degradation. Uncounted ranks
    and ranks the world size announces but that left no artifacts are
    each declared once, with the rank numbers: silence about a missing
    rank would read as "nothing ran there".
    """
    metas = rank_metas(Path(directory))
    if not metas:
        return [], []

    measurements: list[Measurement] = []
    degradations: list[Degradation] = []
    uncounted: list[int] = []
    unparsed_total = 0
    recorded: dict[tuple, Degradation] = {}
    for rank_dir, meta in metas:
        for entry in meta.get("degradations", []):
            degradation = Degradation(
                name=entry["name"], message=entry["message"], remedy=entry.get("remedy")
            )
            # The same microarchitecture rejects the same group on every
            # node: one identical announcement, not one per rank.
            recorded.setdefault(
                (degradation.name, degradation.message), degradation
            )
        csv_path = rank_dir / STAT_OUTPUT
        if not meta.get("counted") or not csv_path.is_file():
            # The sampling subset does not count: its time aggregate is
            # the sum of its own samples, an absence by design.
            if meta.get("role", "counting") != "sampling":
                uncounted.append(meta["rank"])
            continue
        counted, unparsed = _measurements_of(meta, csv_path.read_text())
        measurements.extend(counted)
        unparsed_total += len(unparsed)
    degradations.extend(recorded.values())

    if uncounted:
        ranks = ", ".join(str(rank) for rank in sorted(uncounted))
        degradations.append(
            Degradation(
                name="counting-unavailable",
                message=f"rank(s) {ranks} ran uncounted: no usable perf on their node",
                remedy="install perf on every compute node",
            )
        )
    if unparsed_total:
        degradations.append(
            Degradation(
                name="perf-stat-unparsed",
                message=f"{unparsed_total} perf stat line(s) not recognized",
                remedy="report this line format; the other counts are ingested",
            )
        )

    world = max(
        (meta["world_size"] for _, meta in metas if meta.get("world_size")),
        default=None,
    )
    if world is not None and len(metas) < world:
        missing = sorted(set(range(world)) - {meta["rank"] for _, meta in metas})
        shown = ", ".join(str(rank) for rank in missing[:8])
        if len(missing) > 8:
            shown += ", ..."
        degradations.append(
            Degradation(
                name="counting-incomplete",
                message=f"{len(metas)} of {world} ranks reported; missing: {shown}",
                remedy="check the job logs of the missing ranks",
            )
        )
    return measurements, degradations
