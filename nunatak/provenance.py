"""Provenance collection: best-effort, descriptive, never blocking a Run."""

from __future__ import annotations

from pathlib import Path

from nunatak.collect.execution import Executor
from nunatak.pivot import Provenance


def _git(executor: Executor, cwd: Path, *args: str) -> str | None:
    """Run one git query; None when git or the repository is absent."""
    invocation = executor.run(["git", "-C", str(cwd), *args])
    if invocation.exit_code != 0 or invocation.stdout is None:
        return None
    return invocation.stdout.strip()


def collect(
    executor: Executor, cwd: Path, effective_configuration: dict[str, object]
) -> Provenance:
    """Record what can be observed about the code identity and the effective
    configuration. Runtime dependencies (loaded libraries with their
    build-id) arrive with the attribution chain."""
    commit = _git(executor, cwd, "rev-parse", "HEAD")
    dirty: bool | None = None
    if commit is not None:
        status = _git(executor, cwd, "status", "--porcelain")
        dirty = bool(status) if status is not None else None
    return Provenance(
        commit=commit,
        dirty_tree=dirty,
        effective_configuration=dict(effective_configuration),
    )
