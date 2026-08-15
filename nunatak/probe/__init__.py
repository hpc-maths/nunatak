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
from nunatak.launch import LaunchPlan
from nunatak.pivot import Ceiling, Degradation, Quality

# Bump when pingpong.c changes: measurements from different probes are
# not comparable, so a cached binary of another version is stale.
PROBE_VERSION = 1

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


def stack_key(mpi_stack: MpiStack) -> str:
    """The cache key of one stack: same triple, same artifacts.

    Shared by everything built against the stack - the probe and mpiP
    live in the same cache entry, next to the stack.json that explains
    them.
    """
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
    entry = directory / stack_key(mpi_stack)
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


def built(mpi_stack: MpiStack, directory: Path | None = None) -> Path | None:
    """The cached probe binary for `mpi_stack`, None when never built.

    A run never compiles: doctor built the probe on a login node, where
    the compilers are, and this lookup is all a compute allocation needs.
    """
    directory = cache_directory() if directory is None else directory
    binary = directory / stack_key(mpi_stack) / f"probe-v{PROBE_VERSION}"
    return binary if binary.is_file() else None


@dataclass(frozen=True)
class ProbeRun:
    """Parsed output of one probe run: the self-reported topology and
    message size travel with the rates, like the calibration kernel's."""

    ranks: int | None
    nodes: int | None
    bytes: int | None
    latency_us: float | None
    rates: tuple[float, ...]


# Enough repetitions to witness dispersion, few enough to stay seconds.
REPETITIONS = 3

_SHARED_MEMORY_REASON = (
    "measured over shared memory: single-node allocation, not the interconnect"
)


def network_ceilings(
    executor: Executor, plan: LaunchPlan, mpi_stack: MpiStack | None
) -> tuple[tuple[Ceiling, ...], list[Degradation]]:
    """Run the cached probe inside this launch's allocation and return
    the network Ceilings it measured.

    The probe goes through the same launcher prefix as the application,
    so it lands where the job's ranks land, and the Ceiling keeps the
    best repetition - an upper bound. A single-node world measured
    shared memory, not the interconnect: both Ceilings then carry that
    motivated downgrade. A run never compiles the probe; a missing
    binary names doctor as the way forward and the run proceeds.
    """
    binary = built(mpi_stack) if mpi_stack is not None else None
    if binary is None:
        return (), [
            Degradation(
                name="network-ceiling-unavailable",
                message="no built network probe for this MPI stack",
                remedy="run `nunatak doctor` where the compilers are, then rerun",
            )
        ]
    invocation = executor.run([*plan.prefix, str(binary), str(REPETITIONS)])
    outcome = parse(invocation.stdout or "") if invocation.exit_code == 0 else None
    if outcome is None or not outcome.rates:
        return (), [
            Degradation(
                name="network-ceiling-unavailable",
                message="the network probe ran but did not report",
                remedy="its messages in the log above say more",
            )
        ]
    single_node = outcome.nodes == 1
    quality = Quality.ESTIMATED if single_node else Quality.MEASURED
    reason = _SHARED_MEMORY_REASON if single_node else None
    ceilings = (
        Ceiling(
            name="network_bandwidth",
            value=max(outcome.rates),
            unit="byte/s",
            quality=quality,
            reason=reason,
        ),
    )
    if outcome.latency_us is not None:
        ceilings += (
            Ceiling(
                name="network_latency",
                value=outcome.latency_us * 1e-6,
                unit="s",
                quality=quality,
                reason=reason,
            ),
        )
    return ceilings, []


def parse(stdout: str) -> ProbeRun | None:
    """Parse the probe's self-reported lines, None when they are not its."""
    seen = False
    ranks = size = nodes = None
    latency = None
    rates = []
    for line in stdout.splitlines():
        parts = line.split()
        if parts[:2] == ["probe", "pingpong"]:
            seen = True
        elif parts[:1] == ["ranks"] and len(parts) == 2:
            ranks = int(parts[1])
        elif parts[:1] == ["nodes"] and len(parts) == 2:
            nodes = int(parts[1])
        elif parts[:1] == ["bytes"] and len(parts) == 2:
            size = int(parts[1])
        elif parts[:1] == ["latency_us"] and len(parts) == 2:
            latency = float(parts[1])
        elif parts[:1] == ["rep"] and len(parts) == 3:
            rates.append(float(parts[2]))
    if not seen:
        return None
    return ProbeRun(
        ranks=ranks, nodes=nodes, bytes=size, latency_us=latency, rates=tuple(rates)
    )
