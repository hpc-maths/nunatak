"""Machine snapshot, identity and profile cache.

A Machine is not a node: its identity is the couple hardware plus
allocation shape, which is what makes Ceilings comparable to
Measurements aggregated over the same scope. The profile is cached under
`$XDG_CACHE_HOME/nunatak/machines/` and reused across Runs; every Run
still embeds a complete snapshot in its manifest, so the cache can
disappear without any Run losing anything.

The identification fields and the allocation shape are captured today;
the Ceilings will be produced by the Calibration, and the cache is what
will keep it from replaying on every Run.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
from pathlib import Path

from nunatak.collect.execution import Executor
from nunatak.pivot import Allocation, Machine
from nunatak.pivot.persistence import machine_from_dict, machine_to_dict

# Bump when the calibration kernels change: Ceilings measured by
# different kernels are not comparable, so a cached profile from another
# kernel version is stale by definition.
KERNEL_VERSION = 0


def _cpu_model(executor: Executor) -> str | None:
    """Marketing name of the CPU, best-effort per platform."""
    if platform.system() == "Darwin":
        invocation = executor.run(["sysctl", "-n", "machdep.cpu.brand_string"])
        if invocation.exit_code == 0 and invocation.stdout:
            return invocation.stdout.strip()
        return None
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.is_file():
        for line in cpuinfo.read_text().splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    return None


def _cgroup_directory(
    proc_self: Path = Path("/proc/self/cgroup"),
    root: Path = Path("/sys/fs/cgroup"),
) -> Path | None:
    """This process's cgroup v2 directory, None without the unified
    hierarchy (cgroup v1, macOS)."""
    try:
        for line in proc_self.read_text().splitlines():
            # The unified hierarchy is the "0::" entry.
            if line.startswith("0::"):
                return root / line[3:].strip().lstrip("/")
    except OSError:
        return None
    return None


def _cpu_quota(cgroup: Path | None) -> float | None:
    """The cgroup CPU limit in cores, None when unbounded or unknown.

    `cpu.max` reads `max 100000` when unbounded, else `quota period`.
    """
    if cgroup is None:
        return None
    try:
        quota, period = (cgroup / "cpu.max").read_text().split()
    except (OSError, ValueError):
        return None
    if quota == "max":
        return None
    return int(quota) / int(period)


def _memory_limit(cgroup: Path | None) -> int | None:
    """The cgroup memory cap in bytes, None when unbounded or unknown."""
    if cgroup is None:
        return None
    try:
        limit = (cgroup / "memory.max").read_text().strip()
    except OSError:
        return None
    return None if limit == "max" else int(limit)


def allocation(
    proc_self: Path = Path("/proc/self/cgroup"),
    cgroup_root: Path = Path("/sys/fs/cgroup"),
) -> Allocation:
    """The share of the node this process actually received.

    The affinity mask is the ground truth of what a batch scheduler
    granted; the cgroup limits catch what affinity does not (CPU
    bandwidth quotas, memory caps). Platforms without either report
    None: an unobservable bound is not an absent one.
    """
    mask: tuple[int, ...] | None = None
    if hasattr(os, "sched_getaffinity"):
        mask = tuple(sorted(os.sched_getaffinity(0)))
    cgroup = _cgroup_directory(proc_self, cgroup_root)
    return Allocation(
        visible_cores=len(mask) if mask is not None else os.cpu_count(),
        affinity_mask=mask,
        cpu_quota=_cpu_quota(cgroup),
        memory_limit_bytes=_memory_limit(cgroup),
    )


def snapshot(executor: Executor) -> Machine:
    """Best-effort description of the hardware this process runs on and
    of the share of it this process received."""
    return Machine(
        system=platform.system(),
        kernel=platform.release(),
        architecture=platform.machine(),
        cpu_model=_cpu_model(executor),
        logical_cores=os.cpu_count(),
        allocation=allocation(),
    )


def identity(machine: Machine) -> str:
    """Canonical fingerprint of a Machine: hardware plus allocation shape.

    A thousand identical nodes share one identity; two jobs receiving
    different shares of one node get two. The kernel release is left out
    on purpose - a kernel update does not change what the silicon can
    reach - and the Ceilings are the profile's content, never its key.
    """
    canonical = {
        "system": machine.system,
        "architecture": machine.architecture,
        "cpu_model": machine.cpu_model,
        "logical_cores": machine.logical_cores,
        "visible_cores": machine.allocation.visible_cores,
        "affinity_mask": machine.allocation.affinity_mask,
        "cpu_quota": machine.allocation.cpu_quota,
        "memory_limit_bytes": machine.allocation.memory_limit_bytes,
    }
    digest = hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()
    return digest[:16]


def cache_directory() -> Path:
    """Where Machine profiles live: `$XDG_CACHE_HOME/nunatak/machines`."""
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".cache"
    return base / "nunatak" / "machines"


def store(machine: Machine, directory: Path | None = None) -> Path:
    """Cache `machine`'s profile under its identity and return the path.

    The kernel version rides along: a profile measured by other
    calibration kernels is stale by definition and will not be loaded.
    """
    directory = cache_directory() if directory is None else directory
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{identity(machine)}.json"
    payload = {
        "kernel_version": KERNEL_VERSION,
        "machine": machine_to_dict(machine),
    }
    path.write_text(json.dumps(payload, indent=2) + "\n")
    return path


def load(machine: Machine, directory: Path | None = None) -> Machine | None:
    """The cached profile of `machine`'s identity, None when there is
    none, when it is unreadable, or when it was measured by another
    kernel version."""
    directory = cache_directory() if directory is None else directory
    path = directory / f"{identity(machine)}.json"
    try:
        payload = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    if payload.get("kernel_version") != KERNEL_VERSION:
        return None
    try:
        return machine_from_dict(payload["machine"])
    except (KeyError, TypeError, ValueError):
        return None
