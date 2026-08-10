"""calibrate: measure this Machine's Ceilings and cache the profile.

The calibration also triggers by itself at the first `run` on an unknown
Machine; this verb exists for whoever prefers to spend the budget in a
small dedicated job rather than at the start of a large allocation. A
cached profile short-circuits it - `--force` takes back control - and
the profile is only stored when something was actually measured: a
theory-only outcome must not silence the next attempt.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from nunatak import corpus, machine
from nunatak.calibration import kernel, merged_ceilings, theory
from nunatak.config import load
from nunatak.console import Console
from nunatak.pivot import Machine, Quality


def calibrated_machine(executor, config, snapshot: Machine) -> tuple[Machine, bool]:
    """The snapshot with its Ceilings measured, merged with the theory,
    and stored when anything was measured. Returns (machine, measured).

    Shared by this verb and by `run`'s first-Run trigger, so the two can
    never diverge.
    """
    theoretical = theory.theoretical_ceilings(snapshot)
    measured = kernel.calibrate(
        executor,
        snapshot,
        config,
        theoretical={ceiling.name: ceiling.value for ceiling in theoretical},
    )
    calibrated = dataclasses.replace(
        snapshot, ceilings=merged_ceilings(measured, theoretical)
    )
    anything_measured = any(
        ceiling.quality is Quality.MEASURED for ceiling in measured
    )
    if anything_measured:
        machine.store(calibrated)
    return calibrated, anything_measured


def execute(args, console: Console) -> int:
    """`nunatak calibrate [--force] [--json]`. Returns 0: an incomplete
    calibration leaves theoretical Ceilings, it is not an error."""
    config, _ = load(Path.cwd())
    if args.replay is not None:
        executor = corpus.ReplayExecutor(Path(args.replay))
    elif args.record:
        from nunatak.collect.execution import SubprocessExecutor

        executor = corpus.RecordingExecutor(SubprocessExecutor(), Path(args.record))
    else:
        from nunatak.collect.execution import SubprocessExecutor

        executor = SubprocessExecutor()

    snapshot = machine.snapshot(executor)
    cached = machine.load(snapshot)
    if cached is not None and not args.force:
        console.info(
            f"Machine {machine.identity(snapshot)} already calibrated "
            "(--force to redo)"
        )
        result, from_cache = cached, True
    else:
        console.info(
            f"calibrating Machine {machine.identity(snapshot)} "
            f"({kernel.BUDGET_SECONDS:.0f}s budget)"
        )
        result, measured = calibrated_machine(executor, config, snapshot)
        from_cache = False
        if not measured:
            console.info(
                "nothing could be measured (no compiler, or the kernel did "
                "not build); Ceilings stay theoretical"
            )

    if args.record:
        corpus.write_meta(Path(args.record), ["calibrate"], [])

    if args.json:
        print(
            json.dumps(
                {
                    "machine": machine.identity(result),
                    "cached": from_cache,
                    "ceilings": [
                        {
                            "name": c.name,
                            "value": c.value,
                            "unit": c.unit,
                            "quality": c.quality.value,
                            "reason": c.reason,
                        }
                        for c in result.ceilings
                    ],
                }
            )
        )
    else:
        for ceiling in result.ceilings:
            console.info(
                f"{ceiling.name:<16} {ceiling.value:.3e} {ceiling.unit:<8} "
                f"{ceiling.quality.value}"
                + (f" ({ceiling.reason})" if ceiling.reason else "")
            )
        if not result.ceilings:
            console.info("no Ceiling could be produced on this Machine")
    return 0
