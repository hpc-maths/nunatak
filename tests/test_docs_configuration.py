"""The configuration reference is written by hand, so it can go stale in
two ways: a key can be added to the loader and never documented, and a
default can be changed and never updated.

Both are held here against the loader itself, and against the mapping the
loader records in the Run's provenance, which is the same list a reader
sees in the report.
"""

from __future__ import annotations

import re
from pathlib import Path

from nunatak.config import load

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "docs" / "reference" / "configuration.md"

# Documented as families rather than as one key each: their names are the
# user's, not ours.
FAMILIES = {"name", "tools.<tool>", "source_map.<prefix>"}


def _documented() -> dict[str, str]:
    """The key table of the reference, as {key: default}."""
    rows = re.findall(r"^\| `([^`]+)` \| (.+?) \| .+ \|$", REFERENCE.read_text(), re.MULTILINE)
    return {key: default.strip() for key, default in rows}


def _rendered(value: object) -> str:
    """A default as the page writes it, inside backticks."""
    if isinstance(value, bool):
        return f"`{str(value).lower()}`"
    return f"`{value}`"


def _looked_up_tools() -> set[str]:
    """The tool names the code resolves through `config.tools`."""
    names = set()
    pattern = re.compile(r'tools(?:\.get|\[)\("([a-z0-9_-]+)"|"([a-z0-9_-]+)" in config\.tools')
    for source in (ROOT / "nunatak").rglob("*.py"):
        for direct, membership in pattern.findall(source.read_text()):
            names.add(direct or membership)
    return names


def test_every_key_of_the_cascade_is_documented(tmp_path):
    _, effective = load(tmp_path, site_config=tmp_path / "absent.toml")
    documented = _documented()

    undocumented = set(effective) - set(documented)
    assert not undocumented, (
        f"these keys reach the Run's provenance and are documented nowhere: "
        f"{sorted(undocumented)}"
    )

    invented = set(documented) - set(effective) - FAMILIES
    assert not invented, (
        f"these keys are documented and the loader never reads them: {sorted(invented)}"
    )


def test_every_documented_default_is_the_real_one(tmp_path):
    _, effective = load(tmp_path, site_config=tmp_path / "absent.toml")
    documented = _documented()

    wrong = {
        key: (documented[key], _rendered(value))
        for key, value in effective.items()
        if documented[key] != _rendered(value)
    }
    assert not wrong, f"documented default, real default: {wrong}"


def test_the_documented_tool_names_are_the_ones_looked_up():
    row = _documented_row_for_tools()
    documented = set(re.findall(r"`([a-z0-9_-]+)`", row))
    assert documented == _looked_up_tools(), (
        "the `tools` row lists names the code does not resolve, or misses "
        "names it does"
    )


def _documented_row_for_tools() -> str:
    for line in REFERENCE.read_text().splitlines():
        if line.startswith("| `tools.<tool>`"):
            return line.split("|")[3]
    raise AssertionError("the reference has no `tools` row")
