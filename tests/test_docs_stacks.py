"""The Call stacks subject quotes the row doctor writes and four numbers.

The how-to tells a reader to recompile and to read a percentage; both
sentences come from the ladder's own code, and the numbers that bound
the probing are constants. These tests keep the page and the decision
together.
"""

from __future__ import annotations

from pathlib import Path

from nunatak.cli.run import DWARF_FREQUENCY
from nunatak.collect import stacks
from nunatak.config import Config
from tests.test_stacks import EPYC, _ladder_executor
from tests.support import OBJDUMP_PROLOGUE_NOFP, OBJDUMP_SYMTAB_NOFP

ROOT = Path(__file__).resolve().parents[1]
SUBJECT = ROOT / "docs" / "guide" / "stacks"
INDEX = (SUBJECT / "index.md").read_text()
HOW_TO = (SUBJECT / "get-call-stacks.md").read_text()
EXPLANATION = (SUBJECT / "the-call-stack-ladder.md").read_text()


def flowed(text):
    """The page's prose with its line wrapping removed."""
    return " ".join(text.split())


def test_the_quoted_remedy_and_threshold_are_the_ladders_own():
    decision = stacks.decide(
        _ladder_executor(OBJDUMP_SYMTAB_NOFP, OBJDUMP_PROLOGUE_NOFP),
        Config(),
        "/tmp/workload",
        EPYC,
    )
    assert decision.mode is None
    assert decision.remedy in flowed(HOW_TO)
    threshold = f"below the {Config().stacks_fp_threshold:.0%} threshold"
    assert threshold in decision.detail
    assert threshold in HOW_TO


def test_the_quoted_frequencies_are_the_coded_ones():
    assert f"{DWARF_FREQUENCY} Hz" in HOW_TO
    assert f"{DWARF_FREQUENCY} Hz" in flowed(EXPLANATION)
    assert f"{Config().sampling_frequency} Hz" in flowed(HOW_TO)


def test_the_quoted_sampling_bounds_are_the_coded_ones():
    page = flowed(EXPLANATION)
    assert f"under {stacks.SIZE_FLOOR} bytes" in page
    assert f"{stacks.SAMPLE_PER_MODULE} largest functions of each module" in page


def test_the_documented_key_is_the_configured_one():
    assert "fp_threshold" in HOW_TO
    assert f"fp_threshold = {Config().stacks_fp_threshold}" in HOW_TO


def test_the_subject_is_reachable_and_replaces_the_old_section():
    guide = (ROOT / "docs" / "guide" / "index.md").read_text()
    assert "stacks/index" in guide
    for page in ("get-call-stacks", "the-call-stack-ladder"):
        assert page in INDEX, page
    old = (ROOT / "docs" / "guide" / "getting-started.md").read_text()
    assert "### The call-stack ladder" not in old
    assert "--call-graph dwarf" not in old
