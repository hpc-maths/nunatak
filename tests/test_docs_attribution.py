"""The Attribution subject shows the three rows `doctor` prints about a
binary and the shape an unresolved Hotspot is displayed with. Both are
decided in the code, and a reader compares what they see against what
the page showed them.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from nunatak.attribution import symbolizer
from nunatak.pivot import Hotspot, LogicalIdentity, PhysicalIdentity, ResolutionLevel

ROOT = Path(__file__).resolve().parents[1]
SUBJECT = ROOT / "docs" / "guide" / "attribution"
HOW_TO = (SUBJECT / "get-names-for-your-hotspots.md").read_text()
EXPLANATION = (SUBJECT / "how-attribution-works.md").read_text()
CATALOGUE = (ROOT / "docs" / "reference" / "degradations.md").read_text()


def _check_details(name: str) -> set[str]:
    """The literal `detail` strings a doctor check can answer with."""
    tree = ast.parse((ROOT / "nunatak" / "cli" / "doctor.py").read_text())
    details = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "CheckResult"):
            continue
        keywords = {k.arg: k.value for k in node.keywords}
        checked = keywords.get("name")
        detail = keywords.get("detail")
        if not (isinstance(checked, ast.Constant) and checked.value == name):
            continue
        if isinstance(detail, ast.Constant) and isinstance(detail.value, str):
            details.add(detail.value)
    return details


def test_every_state_of_the_binary_is_documented():
    """The four states differ by what the reader must do about them, so
    a page showing three of them leaves one reader with no answer."""
    details = _check_details("target-attribution")
    assert len(details) == 4, sorted(details)
    for detail in details:
        assert detail in HOW_TO, f"doctor can answer '{detail}' and the page does not"


def test_the_documented_remedies_are_the_ones_doctor_gives():
    page = HOW_TO
    assert "compile with -g to get line numbers, inlining and source extracts" in page


def test_an_unresolved_hotspot_displays_the_documented_way():
    spot = Hotspot(
        logical_identity=LogicalIdentity(module="/usr/lib/libfoo.so"),
        physical_identity=PhysicalIdentity(module_id="b" * 40, offset=0x3A1C),
        resolution_level=ResolutionLevel.UNRESOLVED,
    )
    assert spot.display_name == "libfoo.so+0x3a1c"
    assert "`libfoo.so+0x3a1c`" in EXPLANATION
    assert re.search(r"stencil\+0x[0-9a-f]+ \(unresolved\)", HOW_TO)


def test_the_documented_llvm_window_is_the_declared_one():
    assert f"LLVM {symbolizer.MINIMUM_LLVM} on" in EXPLANATION
    assert (
        f"{symbolizer.MINIMUM_LLVM} to {symbolizer.TESTED_LLVM} today" in EXPLANATION
    )
    assert f"{symbolizer.RECOMMENDED_LLVM} the floor" in EXPLANATION
    assert f"LLVM {symbolizer.RECOMMENDED_LLVM} or newer" in HOW_TO


def test_every_resolution_level_is_named():
    for level in ResolutionLevel:
        assert f"`{level.value}`" in EXPLANATION, level.value


def test_the_named_degradations_have_a_catalogue_entry():
    anchors = set(re.findall(r"^### ([a-z0-9-]+)$", CATALOGUE, re.MULTILINE))
    named = {
        name
        for name in re.findall(r"`([a-z]+(?:-[a-z]+)+)`", HOW_TO + EXPLANATION)
        if name.endswith(("-missing", "-failed", "-too-old"))
    }
    assert named, "the subject names no degradation at all"
    assert named <= anchors, f"named with no entry: {sorted(named - anchors)}"
