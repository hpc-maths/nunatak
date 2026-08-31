"""The architecture page draws the shape of the package, so it goes stale
the moment the shape moves.

A module that appears, disappears or is renamed and is not reflected here
fails, which is the only way a page describing a layout can stay true.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "docs" / "development" / "architecture.md"

# Named nowhere on the page on purpose: `powerfilter` is the filter a
# subprocess runs, reached by `python -m`, not a component of the shape.
NOT_A_COMPONENT = {"__init__", "powerfilter"}


def _components() -> set[str]:
    """The top-level modules and packages of nunatak."""
    package = ROOT / "nunatak"
    names = {path.stem for path in package.glob("*.py")}
    names |= {path.name for path in package.iterdir() if (path / "__init__.py").is_file()}
    return names - NOT_A_COMPONENT


def _named() -> set[str]:
    """The components the page names. `pivot.model` names `pivot`."""
    return {
        name.split(".")[0]
        for name in re.findall(r"`([a-z_][a-z_.]*)`", PAGE.read_text())
    }


def test_every_component_is_on_the_page():
    missing = _components() - _named()
    assert not missing, f"these components are not named anywhere: {sorted(missing)}"


def test_the_page_names_no_component_that_is_gone():
    package = ROOT / "nunatak"
    plausible = {
        name
        for name in _named()
        if (package / f"{name}.py").exists() or (package / name).is_dir()
    }
    invented = {
        name
        for name in _named()
        if name not in plausible
        and name not in {"mpirun", "n", "solver", "doctor", "perf", "xctrace", "sample", "pyspy"}
    }
    assert not invented, f"these read as components and are not: {sorted(invented)}"
