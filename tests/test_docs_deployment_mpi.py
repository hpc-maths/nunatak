"""The MPI and debuginfod pages state a cache layout and a search order
that a site engineer will follow literally. Both are decided in the code,
and a page describing yesterday's order sends someone to the wrong
directory.
"""

from __future__ import annotations

import re
from pathlib import Path

from nunatak.attribution import debuginfod
from nunatak.collect import mpip
from nunatak.config import Config

DEPLOYMENT = Path(__file__).resolve().parents[1] / "docs" / "deployment"


def test_the_documented_cache_layout_is_the_real_one(monkeypatch, tmp_path):
    from nunatak import probe

    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    page = (DEPLOYMENT / "mpi-stack.md").read_text()
    tail = probe.cache_directory().relative_to(tmp_path)
    assert f"$XDG_CACHE_HOME/{tail}" in page
    assert mpip.LIBRARY in page


def test_the_documented_search_order_is_the_real_one(tmp_path, monkeypatch):
    """The page promises `tools.mpip`, then LD_LIBRARY_PATH, then the
    conventional prefixes. Only the first two are checkable without
    writing to system directories, and they are the two a site sets."""
    library = tmp_path / mpip.LIBRARY
    library.write_text("")
    configured = Config()
    configured.tools["mpip"] = str(library)
    assert mpip.locate(configured, environment={}) == str(library)
    assert mpip.locate(Config(), environment={"LD_LIBRARY_PATH": str(tmp_path)}) == str(
        library
    )
    page = (DEPLOYMENT / "mpi-stack.md").read_text()
    for prefix in mpip.SEARCH_DIRS:
        assert f"`{prefix}`" in page, f"{prefix} is searched and unstated"


def test_the_documented_debuginfod_variables_are_the_real_ones():
    page = (DEPLOYMENT / "debuginfod.md").read_text()
    assert debuginfod.URLS in page
    assert debuginfod.TIMEOUT in page


def test_the_documented_timeout_is_the_configured_default():
    stated = re.search(r"nunatak writes (\d+) instead", (DEPLOYMENT / "debuginfod.md").read_text())
    assert stated is not None, "the page does not state the timeout it writes"
    assert int(stated.group(1)) == Config().debuginfod_timeout
