"""Parser for powermetrics' plist stream - macOS per-process aggregates.

The stream is one XML property list per sample, NUL-separated. Three
aggregates survive into the pivot, every one Locus-level (no Hotspot to
attach to) and every one estimated with its reason:

- `energy_impact`, summed over the samples for the tasks bearing the
  profiled command's name: Apple's abstract per-process energy number -
  explicitly not joules, and matched by name because powermetrics
  offers no pid filter.
- `cpu_energy` and `gpu_energy` in millijoules, summed over the
  samples: package-wide - every process on the machine included -
  which the reason says.

The sums cover the samples that completed while the application lived;
an application shorter than the sampling interval leaves none, and the
caller declares that absence.
"""

from __future__ import annotations

import plistlib

from nunatak.pivot import Locus, Measurement, Quality

ENERGY_IMPACT_REASON = (
    "Apple's abstract per-process energy number, not joules; tasks "
    "matched by process name"
)
PACKAGE_REASON = (
    "whole-package energy over the sampling window: every process on "
    "the machine included"
)


def parse(text: str, target_name: str) -> tuple[dict[str, float], int, list[str]]:
    """Sum the stream's samples into the kept aggregates.

    Returns (aggregates, sample count, unparsed chunk descriptions).
    `target_name` is the profiled command's basename, the key the tasks
    are matched by.
    """
    aggregates = {"energy_impact": 0.0, "cpu_energy": 0.0, "gpu_energy": 0.0}
    count = 0
    unparsed: list[str] = []
    for index, chunk in enumerate(text.split("\x00")):
        if not chunk.strip():
            continue
        try:
            sample = plistlib.loads(chunk.encode())
        except Exception as error:
            unparsed.append(f"sample {index}: {error}")
            continue
        count += 1
        processor = sample.get("processor", {})
        aggregates["cpu_energy"] += float(processor.get("cpu_energy", 0))
        aggregates["gpu_energy"] += float(processor.get("gpu_energy", 0))
        for task in sample.get("tasks", ()):
            if task.get("name") == target_name:
                aggregates["energy_impact"] += float(task.get("energy_impact", 0))
    return aggregates, count, unparsed


def measurements(
    text: str, target_name: str, node: str
) -> tuple[list[Measurement], int, list[str]]:
    """The Locus-level Measurements of one rider stream."""
    aggregates, count, unparsed = parse(text, target_name)
    if count == 0:
        return [], 0, unparsed
    locus = Locus(node=node)
    rows = [
        Measurement(
            hotspot=None,
            locus=locus,
            counter="energy_impact",
            value=aggregates["energy_impact"],
            unit="energy-impact",
            quality=Quality.ESTIMATED,
            reason=ENERGY_IMPACT_REASON,
            sample_count=count,
        )
    ]
    for counter in ("cpu_energy", "gpu_energy"):
        rows.append(
            Measurement(
                hotspot=None,
                locus=locus,
                counter=counter,
                value=aggregates[counter],
                unit="mJ",
                quality=Quality.ESTIMATED,
                reason=PACKAGE_REASON,
                sample_count=count,
            )
        )
    return rows, count, unparsed
