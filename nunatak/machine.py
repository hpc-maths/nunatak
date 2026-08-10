"""Machine snapshot embedded in every Run manifest.

The identification fields are captured today; the Ceilings will be
produced by the Calibration.
"""

from __future__ import annotations

import os
import platform
from pathlib import Path

from nunatak.collect.execution import Executor
from nunatak.pivot import Machine


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


def snapshot(executor: Executor) -> Machine:
    """Best-effort description of the hardware this process runs on."""
    return Machine(
        system=platform.system(),
        kernel=platform.release(),
        architecture=platform.machine(),
        cpu_model=_cpu_model(executor),
        logical_cores=os.cpu_count(),
    )
