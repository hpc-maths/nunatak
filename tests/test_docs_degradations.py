"""The degradation catalogue is what a reader lands on after pasting a
name nunatak printed, so a name that reaches a Run and not the page is a
dead end.

Both tests read the `Degradation(...)` call sites: the names are literal
there, which is what makes the catalogue checkable at all.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOGUE = ROOT / "docs" / "reference" / "degradations.md"


def _call_sites() -> list[tuple[str, ast.Call]]:
    """Every `Degradation(...)` built from a literal name.

    One site reconstructs a degradation a rank already named, from its
    recorded JSON; it introduces no name of its own and is skipped.
    """
    sites = []
    for source in sorted((ROOT / "nunatak").rglob("*.py")):
        tree = ast.parse(source.read_text())
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "Degradation"):
                continue
            keywords = {k.arg: k.value for k in node.keywords}
            name = keywords.get("name")
            if isinstance(name, ast.Constant) and isinstance(name.value, str):
                sites.append((name.value, node))
    return sites


def _documented() -> set[str]:
    """The anchors of the catalogue, one per name."""
    return set(re.findall(r"^### ([a-z0-9-]+)$", CATALOGUE.read_text(), re.MULTILINE))


def test_every_degradation_is_documented():
    raised = {name for name, _ in _call_sites()}
    documented = _documented()
    assert raised <= documented, (
        f"these names reach a Run and no entry answers for them: "
        f"{sorted(raised - documented)}"
    )
    assert documented <= raised, (
        f"these entries name degradations nothing raises: {sorted(documented - raised)}"
    )


def test_every_degradation_carries_a_remedy():
    without = {
        name
        for name, call in _call_sites()
        if "remedy" not in {k.arg for k in call.keywords}
    }
    assert not without, (
        f"a degradation states what is missing and how to get past it; these "
        f"state only the first: {sorted(without)}"
    )
