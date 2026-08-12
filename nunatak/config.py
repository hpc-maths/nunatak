"""Configuration: three layers with increasing precedence - site, project,
command-line flags.

TOML format, `nunatak.toml` at the repository root - never inside
`pyproject.toml`, the profiled application being rarely written in Python.
The effective configuration is recorded in the Provenance, thresholds
included: a threshold can be tuned, it cannot be tuned silently.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

SITE_CONFIG = Path("/etc/nunatak.toml")
PROJECT_CONFIG = "nunatak.toml"


@dataclass
class Config:
    """Resolved configuration after the cascade."""

    project_name: str | None = None
    runs_dir: str = ".nunatak"
    tools: dict[str, str] = field(default_factory=dict)
    source_map: dict[str, str] = field(default_factory=dict)
    coverage_threshold: float = 0.8
    sampling_frequency: int = 997
    sampling_rank_threshold: int = 64


def find_project_config(cwd: Path) -> Path | None:
    """Walk up from `cwd` to the filesystem root looking for `nunatak.toml`."""
    for directory in (cwd, *cwd.parents):
        candidate = directory / PROJECT_CONFIG
        if candidate.is_file():
            return candidate
    return None


def _read(path: Path) -> dict:
    """Parse one TOML layer."""
    with path.open("rb") as stream:
        return tomllib.load(stream)


def load(
    cwd: Path,
    name: str | None = None,
    site_config: Path | None = None,
) -> tuple[Config, dict[str, object]]:
    """Load the configuration cascade and return (config, effective).

    `cwd` anchors the project-file search, `name` is the `--name` flag
    (always winning), `site_config` overrides the site file location (used
    by tests; defaults to `/etc/nunatak.toml`, or `$NUNATAK_SITE_CONFIG`).
    `effective` is the flat mapping recorded in the Provenance.
    """
    config = Config()

    if site_config is None:
        env = os.environ.get("NUNATAK_SITE_CONFIG")
        site_config = Path(env) if env else SITE_CONFIG
    project_config = find_project_config(cwd)

    for path in (site_config, project_config):
        if path is None or not path.is_file():
            continue
        data = _read(path)
        config.project_name = data.get("name", config.project_name)
        config.runs_dir = data.get("runs_dir", config.runs_dir)
        config.tools.update(data.get("tools", {}))
        config.source_map.update(data.get("source_map", {}))
        thresholds = data.get("thresholds", {})
        config.coverage_threshold = thresholds.get("coverage", config.coverage_threshold)
        sampling = data.get("sampling", {})
        config.sampling_frequency = sampling.get("frequency", config.sampling_frequency)
        config.sampling_rank_threshold = sampling.get(
            "rank_threshold", config.sampling_rank_threshold
        )

    if name is not None:
        config.project_name = name

    effective: dict[str, object] = {
        "runs_dir": config.runs_dir,
        "thresholds.coverage": config.coverage_threshold,
        "sampling.frequency": config.sampling_frequency,
        "sampling.rank_threshold": config.sampling_rank_threshold,
    }
    if config.project_name is not None:
        effective["name"] = config.project_name
    for tool, path in sorted(config.tools.items()):
        effective[f"tools.{tool}"] = path
    for prefix, replacement in sorted(config.source_map.items()):
        effective[f"source_map.{prefix}"] = replacement
    return config, effective
