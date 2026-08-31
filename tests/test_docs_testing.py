"""The testing page describes the suite a contributor is about to run:
its markers, its matrix, and the two corpora. All three are declared
elsewhere and all three move.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "docs" / "development" / "testing.md"


def test_the_documented_markers_are_the_declared_ones():
    with (ROOT / "pyproject.toml").open("rb") as stream:
        declared = {
            marker.split(":")[0]
            for marker in tomllib.load(stream)["tool"]["pytest"]["ini_options"]["markers"]
        }
    page = PAGE.read_text()
    for marker in declared:
        assert f"-m {marker}" in page, f"the {marker} lane is undocumented"


def test_the_documented_matrix_is_the_real_one():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    page = PAGE.read_text()
    for row in re.findall(r"os: \[(.+?)\]", workflow)[0].split(","):
        image = row.strip()
        assert f"`{image}`" in page, f"{image} runs tier 1 and is unstated"
    versions = re.findall(r'python: \[(.+?)\]', workflow)[0]
    for version in re.findall(r'"([\d.]+)"', versions):
        assert version in page, f"CPython {version} runs tier 1 and is unstated"


def test_both_corpora_are_where_the_page_says():
    page = PAGE.read_text()
    for corpus in re.findall(r"`(corpus/[a-z]+/)`", page):
        assert (ROOT / corpus).is_dir(), f"{corpus} is documented and absent"
    assert (ROOT / "corpus" / "recordings").is_dir()
    assert (ROOT / "corpus" / "binaries").is_dir()
