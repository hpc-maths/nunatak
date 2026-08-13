"""Network probe: built at first use against the site's MPI stack.

The probe binds to the site's MPI, and MPI ABIs are mutually
incompatible (Open MPI, MPICH, Intel MPI, Cray MPICH): it is never
shipped built. It is compiled with the site's own `mpicc` at first use
- preferably during `doctor`, on a login node, compute nodes often
having no compiler - and cached by stack under
`$XDG_CACHE_HOME/nunatak/probes`: on a cluster with modules, the MPI
loaded at install time is almost never the job's. The identified stack
is recorded in the Run's Provenance: a network analysis whose
underlying stack is unknown is not interpretable.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from nunatak.collect.execution import Executor
from nunatak.config import Config

# Bump when pingpong.c changes: measurements from different probes are
# not comparable, so a cached binary of another version is stale.
PROBE_VERSION = 0

_SOURCE = Path(__file__).parent / "pingpong.c"


@dataclass(frozen=True)
class MpiStack:
    """The triple that decides whether a built probe is reusable."""

    implementation: str
    version: str
    mpicc: str

    @property
    def label(self) -> str:
        """The human-readable form recorded in the Provenance."""
        return f"{self.implementation} {self.version}"


def mpicc_path(executor: Executor, config: Config) -> str | None:
    """The usable MPI compiler wrapper, None when nothing answers.

    `tools.mpicc` in the configuration wins, then the conventional name.
    """
    candidates = []
    if "mpicc" in config.tools:
        candidates.append(config.tools["mpicc"])
    candidates.append("mpicc")
    for candidate in candidates:
        if executor.run([candidate, "--version"]).exit_code == 0:
            return candidate
    return None


def _parse_launcher(text: str) -> tuple[str, str]:
    """Implementation and version out of `mpirun --version` output.

    The two shapes parsed here are verbatim: Open MPI's one-liner and
    MPICH's HYDRA block. Anything else keeps its first line as the
    version of an "unknown" implementation - truthful enough for a
    cache key, and recorded as-is in the Provenance.
    """
    match = re.search(r"\(Open MPI\) (\S+)", text)
    if match:
        return "Open MPI", match.group(1)
    if "HYDRA" in text:
        match = re.search(r"Version:\s+(\S+)", text)
        if match:
            return "MPICH", match.group(1)
    first = text.strip().splitlines()[0].strip() if text.strip() else "unknown"
    return "unknown", first


def stack(executor: Executor, config: Config) -> MpiStack | None:
    """Identify the site's MPI stack; None without a usable mpicc."""
    mpicc = mpicc_path(executor, config)
    if mpicc is None:
        return None
    launcher = executor.run(["mpirun", "--version"])
    text = launcher.stdout or "" if launcher.exit_code == 0 else ""
    implementation, version = _parse_launcher(text)
    return MpiStack(implementation=implementation, version=version, mpicc=mpicc)


def cache_directory() -> Path:
    """Where built probes live, sibling of the Machine profiles."""
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".cache"
    return base / "nunatak" / "probes"


def _key(mpi_stack: MpiStack) -> str:
    """The cache key of one stack: same triple, same binary."""
    triple = "|".join((mpi_stack.implementation, mpi_stack.version, mpi_stack.mpicc))
    return hashlib.sha256(triple.encode()).hexdigest()[:16]


def build(
    executor: Executor, mpi_stack: MpiStack, directory: Path | None = None
) -> Path | None:
    """Compile the probe for `mpi_stack`, reusing the cached binary.

    The stack triple is written next to the binary, so a cache entry
    stays explainable without nunatak. None when mpicc fails - the
    named degradation is the caller's to announce.
    """
    directory = cache_directory() if directory is None else directory
    entry = directory / _key(mpi_stack)
    binary = entry / f"probe-v{PROBE_VERSION}"
    if binary.is_file():
        return binary
    entry.mkdir(parents=True, exist_ok=True)
    (entry / "stack.json").write_text(
        json.dumps(
            {
                "implementation": mpi_stack.implementation,
                "version": mpi_stack.version,
                "mpicc": mpi_stack.mpicc,
            },
            indent=2,
        )
        + "\n"
    )
    invocation = executor.run(
        [mpi_stack.mpicc, "-O2", str(_SOURCE), "-o", str(binary)]
    )
    return binary if invocation.exit_code == 0 else None


@dataclass(frozen=True)
class ProbeRun:
    """Parsed output of one probe run: the self-reported topology and
    message size travel with the rates, like the calibration kernel's."""

    ranks: int | None
    bytes: int | None
    latency_us: float | None
    rates: tuple[float, ...]


def parse(stdout: str) -> ProbeRun | None:
    """Parse the probe's self-reported lines, None when they are not its."""
    seen = False
    ranks = size = None
    latency = None
    rates = []
    for line in stdout.splitlines():
        parts = line.split()
        if parts[:2] == ["probe", "pingpong"]:
            seen = True
        elif parts[:1] == ["ranks"] and len(parts) == 2:
            ranks = int(parts[1])
        elif parts[:1] == ["bytes"] and len(parts) == 2:
            size = int(parts[1])
        elif parts[:1] == ["latency_us"] and len(parts) == 2:
            latency = float(parts[1])
        elif parts[:1] == ["rep"] and len(parts) == 3:
            rates.append(float(parts[2]))
    if not seen:
        return None
    return ProbeRun(ranks=ranks, bytes=size, latency_us=latency, rates=tuple(rates))
