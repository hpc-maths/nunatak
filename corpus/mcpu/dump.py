"""Print the -mcpu inventory of the LLVM under test, one name per line.

The version watch diffs this inventory against the committed baseline of
the last validated major: a name that appears is a microarchitecture the
new LLVM learned, and the signal that drives the theory table and the
event sets forward. NUNATAK_LLVM names the bin directory of the install
to inventory, exactly as in the `-m llvm` test lane; without it the
host's located LLVM answers.

    NUNATAK_LLVM=/usr/lib/llvm-21/bin python corpus/mcpu/dump.py

Refreshing the baseline is part of validating a new major: rerun this
against it, commit the output as `llvm-<major>.txt`, and bump
TESTED_LLVM in the same change.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from nunatak.attribution.loops import _known_cpus, _mca_path
from nunatak.attribution.symbolizer import locate
from nunatak.collect.execution import SubprocessExecutor
from nunatak.config import Config


def main() -> None:
    """Locate the install under test and print its models, sorted."""
    executor = SubprocessExecutor()
    override = os.environ.get("NUNATAK_LLVM")
    config = (
        Config(tools={"llvm-symbolizer": os.path.join(override, "llvm-symbolizer")})
        if override
        else Config()
    )
    symbolizer = locate(executor, config)
    if symbolizer is None:
        raise SystemExit("no usable llvm-symbolizer to inventory")
    if override and not symbolizer.path.startswith(override):
        raise SystemExit(
            f"NUNATAK_LLVM={override} did not answer; refusing to "
            f"inventory {symbolizer.path} instead"
        )
    names = _known_cpus(executor, _mca_path(symbolizer))
    if not names:
        raise SystemExit(f"llvm-mca next to {symbolizer.path} lists no models")
    print("\n".join(sorted(names)))


if __name__ == "__main__":
    main()
