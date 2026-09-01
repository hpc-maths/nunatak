"""The classification catalogue is where a verdict printed beside a
Hotspot leads. A regime the engine can state and the page does not
answer for is a dead end, and a threshold quoted from an older constant
teaches the reader to expect the wrong verdict.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from nunatak import analysis

ROOT = Path(__file__).resolve().parents[1]
PAGE = (ROOT / "docs" / "reference" / "classifications.md").read_text()


def _stated() -> list[str]:
    """Every regime `_classify` can return, in the order it tries them."""
    tree = ast.parse((ROOT / "nunatak" / "analysis.py").read_text())
    function = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_classify"
    )
    returns = sorted(
        (node for node in ast.walk(function) if isinstance(node, ast.Return)),
        key=lambda node: node.lineno,
    )
    regimes: list[str] = []
    for node in returns:
        if not isinstance(node.value, ast.Tuple):
            continue
        first = node.value.elts[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            regimes.append(first.value)
        elif isinstance(first, ast.IfExp):
            # `memory-bound if intensity < ridge else compute-bound`:
            # the two sides of the ridge, in the order they are written.
            regimes += [
                branch.value
                for branch in (first.body, first.orelse)
                if isinstance(branch, ast.Constant)
            ]
    return regimes


def test_every_regime_the_engine_states_has_an_entry():
    documented = re.findall(r"^## ([a-z-]+)$", PAGE, re.MULTILINE)
    stated = _stated()
    assert set(stated) == set(documented), (
        f"stated with no entry: {sorted(set(stated) - set(documented))}; "
        f"entries for nothing: {sorted(set(documented) - set(stated))}"
    )


def test_the_entries_are_in_the_order_the_engine_tries_them():
    """The page says so, and a reader uses it to know which verdict
    wins when two conditions hold."""
    documented = re.findall(r"^## ([a-z-]+)$", PAGE, re.MULTILINE)
    assert documented == _stated()


def test_the_documented_thresholds_are_the_engine_s():
    assert f"**{analysis.IMBALANCE_RATIO:.1f}x**" in PAGE
    assert analysis.LATENCY_FRACTION == 0.5
    assert "below **half**" in PAGE


def test_the_documented_ridge_is_the_one_the_envelope_uses():
    quoted = re.search(r"`(flops_dp / dram_bandwidth)`", PAGE)
    assert quoted is not None, "the page states no ridge point"
    numerator, denominator = quoted.group(1).split(" / ")
    source = (ROOT / "nunatak" / "analysis.py").read_text()
    assert f'ceilings["{numerator}"], ceilings["{denominator}"]' in source


def test_the_page_says_what_replaces_a_missing_verdict():
    assert "no placement:" in PAGE
