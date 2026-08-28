"""compare: the diff of two Runs, in the terminal and for machines.

The terminal shows the first reading level - the total, then the
heaviest entities - in the report's vocabulary. `--json` carries the
whole diff, every delta with its sampling error and its significance
verdict: it is what a performance CI actually consumes, and the verdict
travels with the number so the CI does not reinvent statistics. The
exit code stays 0 either way: a comparison informs, deciding what a
regression means belongs to whoever reads it.
"""

from __future__ import annotations

import json
from pathlib import Path

from nunatak.compare import Comparison, Delta, Side, compare
from nunatak.console import Console
from nunatak.exit_codes import FAILURE_BEFORE_LAUNCH
from nunatak.pivot import read_run

# The terminal is the first reading level, not the inventory: the
# heaviest entities, then how many were left out.
MAX_ROWS = 10


def execute(args, console: Console) -> int:
    """`nunatak compare <before> <after> [--json]`. Returns 0 on a
    produced diff, 125 when either Run cannot be read."""
    runs = []
    for argument in (args.before, args.after):
        try:
            runs.append(read_run(Path(argument)))
        except (ValueError, OSError) as error:
            console.error(str(error))
            return FAILURE_BEFORE_LAUNCH
    comparison = compare(runs[0], runs[1])

    for finding in comparison.findings:
        console.warning(f"not directly comparable [{finding.name}]: {finding.message}")
    for line in lines(comparison):
        console.info(line)

    if args.json:
        print(json.dumps(_payload(comparison, args.before, args.after)))
    return 0


def lines(comparison: Comparison) -> list[str]:
    """The terminal's first reading level: total first, heaviest next."""
    produced = [
        f"compare: {comparison.before} -> {comparison.after}",
        f"total: {_row(comparison.total, comparison.unit)}",
    ]
    for delta in comparison.deltas[:MAX_ROWS]:
        where = f" ({Path(delta.file).name})" if delta.file else ""
        produced.append(f"  {delta.function}{where} {_row(delta, comparison.unit)}")
    left_out = len(comparison.deltas) - MAX_ROWS
    if left_out > 0:
        produced.append(f"  ... and {left_out} more compared entities")
    return produced


def _row(delta: Delta, unit: str | None) -> str:
    """One delta as a sentence carrying its own uncertainty."""
    if delta.before is None:
        return f"appeared at {_quantity(delta.after.value, unit)}"
    if delta.after is None:
        return f"vanished (was {_quantity(delta.before.value, unit)})"
    sentence = (
        f"{_quantity(delta.before.value, unit)} -> "
        f"{_quantity(delta.after.value, unit)}"
    )
    if delta.before.value > 0:
        fraction = delta.change / delta.before.value
        sentence += f": {fraction:+.1%}"
        error = delta.combined_error / delta.before.value
        if delta.significant:
            sentence += f" (significant, sampling error ±{error:.1%})"
        else:
            sentence += (
                f" (within the sampling error of ±{error:.1%}: "
                "not a difference)"
            )
    return sentence


def _quantity(value: float, unit: str | None) -> str:
    """A time-base value, in seconds when the base is a clock."""
    if unit == "ns":
        return f"{value / 1e9:.3g} s"
    return f"{value:.3g}" + (f" {unit}" if unit else "")


def _payload(comparison: Comparison, before: str, after: str) -> dict:
    """The machine-readable diff: everything, verdicts included."""
    return {
        "before": {"run": before, "name": comparison.before},
        "after": {"run": after, "name": comparison.after},
        "unit": comparison.unit,
        "findings": [
            {"name": finding.name, "message": finding.message}
            for finding in comparison.findings
        ],
        "total": _delta(comparison.total),
        "deltas": [_delta(delta) for delta in comparison.deltas],
    }


def _delta(delta: Delta) -> dict:
    """One delta in plain JSON, its uncertainty and verdict attached."""
    change_fraction = None
    if delta.change is not None and delta.before.value > 0:
        change_fraction = delta.change / delta.before.value
    return {
        "function": delta.function,
        "file": delta.file,
        "before": _side(delta.before),
        "after": _side(delta.after),
        "change": delta.change,
        "change_fraction": change_fraction,
        "combined_error": delta.combined_error,
        "significant": delta.significant,
    }


def _side(side: Side | None) -> dict | None:
    """One side in plain JSON, None passing through."""
    if side is None:
        return None
    return {"value": side.value, "samples": side.samples, "error": side.error}
