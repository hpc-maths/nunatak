"""The Counter groups page quotes periods, budgets and one message.

Every number on it is a constant of the sampled event tables or of the
ingestion that judges multiplexing. A reader who computes an interrupt
rate from the periods is reading code, so the two travel together.
"""

from __future__ import annotations

from pathlib import Path

from nunatak.collect.events import (
    DRAM_REASON,
    FILL_PERIOD,
    FLOP_PERIOD,
    L3_MISS_REASON,
    PRECISION_REASON,
)
from nunatak.config import Config

ROOT = Path(__file__).resolve().parents[1]
PAGE = (ROOT / "docs" / "guide" / "counter-groups.md").read_text()


def flowed(text):
    """The page's prose with its line wrapping removed."""
    return " ".join(text.split())


def test_the_quoted_periods_are_the_sampled_ones():
    page = flowed(PAGE)
    assert f"{FLOP_PERIOD:,} retired FLOPs" in page
    assert f"{FILL_PERIOD:,} demand fills" in page


def test_the_quoted_multiplexing_message_is_the_written_one():
    threshold = Config().coverage_threshold
    rendered = (
        f"counters multiplexed: coverage 63% below the {threshold:.0%} threshold"
    )
    assert rendered in PAGE
    assert f"clears {threshold:.0%}" in flowed(PAGE)


def test_the_narrower_truths_are_stated_in_the_measurements_own_words():
    """Each of the three proxies says what it does not count, and the
    page has to make the same three claims."""
    page = flowed(PAGE)
    assert "prefetched traffic is not counted" in DRAM_REASON
    assert "no prefetched traffic" in page
    assert "stores, prefetched" in L3_MISS_REASON
    assert "no stores and no" in page
    assert "double-precision peak" in PRECISION_REASON
    assert "double-precision peak" in page


def test_the_page_is_reachable_and_replaces_the_old_section():
    guide = (ROOT / "docs" / "guide" / "index.md").read_text()
    assert "counter-groups" in guide
    old = (ROOT / "docs" / "guide" / "getting-started.md").read_text()
    assert "## Counter groups" not in old
