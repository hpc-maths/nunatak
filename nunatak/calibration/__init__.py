"""Calibration: the operation that produces the Ceilings of a Machine.

The nominal path runs microbenchmarks on the target - a Ceiling is the
maximum of its repetitions, never their mean, because a roofline only
makes sense against a bound that is reachable in practice. The
theoretical table is the last rung of the fallback ladder: it never
produces anything better than an estimated Ceiling, and it never
extrapolates - an unknown microarchitecture yields no Ceiling at all.
"""

from __future__ import annotations

from nunatak.pivot import Ceiling

__all__ = ["merged_ceilings"]


def merged_ceilings(
    measured: tuple[Ceiling, ...], theoretical: tuple[Ceiling, ...]
) -> tuple[Ceiling, ...]:
    """One set of Ceilings for the Machine: what was measured wins, the
    theoretical table fills whatever stayed unmeasured - a partial
    calibration still deserves a complete roofline."""
    names = {ceiling.name for ceiling in measured}
    return tuple(measured) + tuple(
        ceiling for ceiling in theoretical if ceiling.name not in names
    )
