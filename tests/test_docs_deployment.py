"""The deployment pages state versions and paths that live in the
packaging metadata and in the configuration loader. Both drift silently,
and a site engineer following a stale number installs the wrong thing.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - the floor this file is about
    import tomli as tomllib

from nunatak.attribution.symbolizer import MINIMUM_LLVM
from nunatak.config import SITE_CONFIG

ROOT = Path(__file__).resolve().parents[1]
DEPLOYMENT = ROOT / "docs" / "deployment"


def _metadata() -> dict:
    with (ROOT / "pyproject.toml").open("rb") as stream:
        return tomllib.load(stream)["project"]


def test_the_documented_python_floor_is_the_declared_one():
    stated = re.search(
        r"nunatak itself needs (\d+\.\d+) or newer",
        (DEPLOYMENT / "installing.md").read_text(),
    )
    assert stated is not None, "the page does not state a Python floor"
    assert f">={stated.group(1)}" == _metadata()["requires-python"]


def test_the_documented_runtime_dependency_is_the_declared_one():
    page = (DEPLOYMENT / "installing.md").read_text()
    declared = {
        re.split(r"[<>=; ]", requirement)[0]
        for requirement in _metadata()["dependencies"]
        if "python_version" not in requirement
    }
    for name in declared:
        assert f"`{name}`" in page, f"{name} is a runtime dependency and unstated"


def test_the_documented_llvm_fallback_floor_is_the_real_one():
    page = (DEPLOYMENT / "installing.md").read_text()
    stated = re.search(r"(\d+) and (\d+) symbolize completely", page)
    assert stated is not None, "the page does not state the tolerated versions"
    assert int(stated.group(1)) == MINIMUM_LLVM


def test_the_documented_site_path_is_the_real_one():
    page = (DEPLOYMENT / "site-configuration.md").read_text()
    assert f"`{SITE_CONFIG}`" in page
    assert "NUNATAK_SITE_CONFIG" in page
