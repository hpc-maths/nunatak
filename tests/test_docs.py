"""The command reference is generated from the parser, so an option can
never be missing from it. What can be missing is the paragraph saying why
the option exists, and that is what these tests hold.

A new flag fails them until someone decides which of the two it is:
worth a paragraph, or self-evident from its help string.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from nunatak.cli import build_parser

REFERENCE = Path(__file__).resolve().parents[1] / "docs" / "reference" / "commands.md"

# Options whose help string says everything there is to say. Adding a flag
# here is a decision, not a formality: it states that a reader who sees the
# generated line needs nothing more.
SELF_EVIDENT = {
    ("nunatak", "--version"),
    ("nunatak", "--help"),
    ("run", "--help"),
    ("run", "--output"),
    ("run", "--json"),
    ("doctor", "--help"),
    ("doctor", "--json"),
    ("explain", "--help"),
    ("report", "--help"),
    ("report", "--json"),
    ("compare", "--help"),
    ("compare", "--json"),
    ("calibrate", "--help"),
    ("calibrate", "--json"),
}

# Hidden from `--help` and from the reference alike: the corpus surface,
# used by hardware campaigns and by nothing a reader will ever type.
HIDDEN = {"--record", "--replay"}


def _verbs(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return dict(action.choices)
    raise AssertionError("the parser declares no verbs")


def _options(parser: argparse.ArgumentParser) -> set[str]:
    """The long option strings a reader can type, hidden ones excluded."""
    names = set()
    for action in parser._actions:
        if action.help is argparse.SUPPRESS:
            continue
        names.update(o for o in action.option_strings if o.startswith("--"))
    return names


def _hidden(parser: argparse.ArgumentParser) -> set[str]:
    names = set()
    for action in parser._actions:
        if action.help is argparse.SUPPRESS:
            names.update(action.option_strings)
    return names


def _explained() -> set[str]:
    """The options carrying a prose block in the reference page."""
    pattern = re.compile(r"^\s+(--[a-z-]+)\s*:\s*@\w+\s*$", re.MULTILINE)
    return set(pattern.findall(REFERENCE.read_text()))


def test_every_option_is_explained_or_declared_self_evident():
    parser = build_parser()
    explained = _explained()

    missing = set()
    for name, verb in [("nunatak", parser), *_verbs(parser).items()]:
        for option in _options(verb):
            if (name, option) in SELF_EVIDENT or option in explained:
                continue
            missing.add(f"{name} {option}")

    assert not missing, (
        "these options reach the reference with nothing but their help "
        f"string: {sorted(missing)}. Write a `@after` block in "
        "docs/reference/commands.md, or add the option to SELF_EVIDENT."
    )


def test_the_corpus_surface_stays_out_of_the_reference():
    parser = build_parser()
    hidden = set()
    for verb in _verbs(parser).values():
        hidden |= _hidden(verb)
    assert hidden == HIDDEN, (
        "the set of options hidden from --help changed; the reference "
        "generates from the parser, so a newly hidden option silently "
        "leaves the page and a newly shown one silently enters it"
    )

    page = REFERENCE.read_text()
    for option in HIDDEN:
        assert option not in page, f"{option} is hidden from --help but named in the reference"
