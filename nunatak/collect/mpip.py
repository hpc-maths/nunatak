"""mpiP: the MPI collector, preloaded into every rank.

mpiP wraps the PMPI interface through `LD_PRELOAD` - the application is
never recompiled - and writes one aggregated report at `MPI_Finalize`:
per-rank MPI time and sent volumes, the counting layer's view of the
network. The library must be built against the site's MPI stack, so
this module only locates one; the build-at-first-use mechanism belongs
to the network probe (spec ch. 12), which shares that constraint.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

from nunatak.config import Config

LIBRARY = "libmpiP.so"

# After the configuration and the loader path, the prefixes a hand-built
# mpiP usually lands in.
SEARCH_DIRS = ("/usr/local/lib", "/usr/lib")


def locate(config: Config, environment: Mapping[str, str] = os.environ) -> str | None:
    """The path of `libmpiP.so`, or None when no copy is found.

    `tools.mpip` in the configuration wins and is trusted only if the
    file exists; then each directory of `LD_LIBRARY_PATH` - which is how
    an environment module exposes the site's build - then the usual
    prefixes. Located here on the login node, used on the compute
    nodes: the path must hold there too, which a shared filesystem
    gives for free.
    """
    configured = config.tools.get("mpip")
    if configured:
        return configured if Path(configured).is_file() else None
    directories = environment.get("LD_LIBRARY_PATH", "").split(os.pathsep)
    for directory in (*directories, *SEARCH_DIRS):
        candidate = Path(directory) / LIBRARY if directory else None
        if candidate is not None and candidate.is_file():
            return str(candidate)
    return None
