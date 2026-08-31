"""The code map is a hand-kept list of generated pages, which is the
shape that drifts: a module appears and nobody adds its three lines.

It had drifted by twenty-one modules, the whole macOS path among them,
before this test existed.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "docs" / "development" / "code-map.md"

# The package itself carries only `__version__`; a page about it would
# say nothing the first paragraph does not.
EXCLUDED = {"nunatak"}


def _modules() -> set[str]:
    """Every importable module of the package."""
    names = set()
    for path in (ROOT / "nunatak").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        parts = path.with_suffix("").relative_to(ROOT).parts
        names.add(".".join(parts[:-1] if parts[-1] == "__init__" else parts))
    return names - EXCLUDED


def _documented() -> set[str]:
    return set(re.findall(r"automodule:: ([\w.]+)", PAGE.read_text()))


def test_every_module_is_on_the_map():
    missing = _modules() - _documented()
    assert not missing, f"these modules are on no page: {sorted(missing)}"


def test_the_map_documents_nothing_that_is_gone():
    invented = _documented() - _modules()
    assert not invented, f"these are documented and do not exist: {sorted(invented)}"
