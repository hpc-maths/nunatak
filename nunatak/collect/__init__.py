"""Collection orchestration: adapters around external collectors.

Every collector is executed as a subprocess and its output parsed, never
linked: the product's license and ABI stay decoupled from every tool's.
The single execution boundary lives
in `execution.py`; it is what the corpus records and replays.
"""

from __future__ import annotations

from nunatak.collect.execution import Executor
from nunatak.collect.perf import PerfAdapter
from nunatak.config import Config


def cpu_collector(
    executor: Executor, config: Config
) -> tuple[PerfAdapter | None, str | None]:
    """The CPU collector usable in this environment: (adapter, version).

    (None, None) when the tool is absent; (None, version) when the tool is
    present but the environment forbids sampling - a capability lost to
    permissions is a degradation, never a failed launch. The platform is
    the executor's: a replayed Linux entry stays a Linux collection
    wherever it is replayed."""
    if executor.system != "Linux":
        return None, None
    adapter = PerfAdapter(config.tools.get("perf", "perf"))
    version = adapter.detect(executor)
    if version is None:
        return None, None
    if executor.sampling_blocked() is not None:
        return None, version
    return adapter, version
