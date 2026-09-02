"""The landing page's five cards are the site's five sections.

A card that points at a section which no longer exists is a dead link
the build catches; a section with no card is a section a reader never
reaches from the front page, and nothing else would catch that.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
LANDING = (DOCS / "index.md").read_text()
CONF = (DOCS / "conf.py").read_text()

# The excluded trees are not sections: `spec` is the residue of the
# French design document and `brand` holds assets.
EXCLUDED = {"spec", "brand", "_build", "_static"}


def _sections():
    """Every top-level directory of the site that carries an index."""
    return {
        path.parent.name
        for path in DOCS.glob("*/index.md")
        if path.parent.name not in EXCLUDED
    }


def test_every_section_has_a_card_and_every_card_a_section():
    linked = set(re.findall(r":link: ([a-z-]+)/index", LANDING))
    assert linked == _sections()
    assert len(re.findall(r"grid-item-card", LANDING)) == len(_sections())


def test_the_cards_and_the_navigation_agree():
    entries = set(re.findall(r"^([a-z-]+)/index$", LANDING, re.MULTILINE))
    assert entries == _sections()


def test_the_banner_says_what_the_reader_is_reading():
    assert "no release yet" in CONF
    assert "development version" in CONF


def test_the_extension_the_cards_need_is_declared():
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text())
    declared = " ".join(metadata["dependency-groups"]["docs"])
    assert "sphinx-design" in declared
    assert "sphinx_design" in CONF
    assert "colon_fence" in CONF, "the `:::` blocks would not be parsed"
