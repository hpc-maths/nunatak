"""The three vocabularies a reader meets in the terminal and in the
report - Quality, resolution levels, exit codes - are enumerations in the
code, so the pages that list them are held against the enumerations.

A value added to one of them and left undocumented is a reader landing on
a word the site does not define.
"""

from __future__ import annotations

import re
from pathlib import Path

from nunatak import exit_codes
from nunatak.pivot import model
from nunatak.pivot.model import Quality, ResolutionLevel

REFERENCE = Path(__file__).resolve().parents[1] / "docs" / "reference"


def _first_column(page: str) -> list[str]:
    """The backticked values of a table's first column, in order."""
    text = (REFERENCE / page).read_text()
    return [
        match.group(1)
        for line in text.splitlines()
        if (match := re.match(r"^\| `([^`]+)` \| ", line))
    ]


def test_every_quality_value_is_documented():
    assert _first_column("quality.md")[:3] == [q.value for q in Quality]


def test_every_resolution_level_is_documented():
    assert _first_column("resolution-levels.md") == [r.value for r in ResolutionLevel]


def test_every_reserved_exit_code_is_documented():
    documented = {
        int(value) for value in _first_column("exit-codes.md") if value.isdigit()
    }
    reserved = {
        value
        for name, value in vars(exit_codes).items()
        if name.isupper() and isinstance(value, int)
    }
    assert documented == reserved


def test_every_entity_of_the_diagram_is_one_the_pivot_has():
    """The glossary draws the domain model. An entity drawn there and
    absent from the pivot would be a promise the format does not keep."""
    page = (REFERENCE / "glossary.md").read_text()
    diagram = page.split("```")[1]
    # The parenthesised text is commentary, not an entity name.
    drawn = set(re.findall(r"\b[A-Z][a-z]+\b", re.sub(r"\([^)]*\)", "", diagram)))
    assert drawn, "the glossary draws no diagram"
    for entity in drawn:
        assert hasattr(model, entity), entity
