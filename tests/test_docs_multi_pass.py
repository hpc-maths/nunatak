"""The Multi-pass subject quotes a witness verdict and a threshold.

The pages promise two things a reader cannot check by hand: that the
groups are the ones the tables define, and that a disagreement between
passes downgrades every fused quantity with a stated reason. Both are
held here against the analysis that produces them.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

from nunatak.analysis import (
    WITNESS_COUNTERS,
    Derived,
    WitnessVerdict,
    _fused,
)
from nunatak.config import Config
from nunatak.pivot import Quality
from tests.test_analysis import hotspot, measurement

_MEASUREMENT = measurement(hotspot(), "flops", 1.0, "flop")

ROOT = Path(__file__).resolve().parents[1]
SUBJECT = ROOT / "docs" / "guide" / "multi-pass"
INDEX = (SUBJECT / "index.md").read_text()
HOW_TO = (SUBJECT / "run-a-multi-pass-acquisition.md").read_text()
EXPLANATION = (SUBJECT / "the-witness-between-passes.md").read_text()


def flowed(text):
    """The page's prose with its line wrapping removed."""
    return " ".join(text.split())


def test_the_quoted_disagreement_reason_is_the_rendered_one():
    verdict = WitnessVerdict(
        counter="flops",
        totals=((0, 100.0), (1, 112.0)),
        spread=0.12,
        threshold=Config().passes_witness_threshold,
    )
    assert not verdict.consistent
    quantity = Derived(
        name="dram_intensity",
        value=1.0,
        unit="flop/byte",
        quality=Quality.MEASURED,
    )
    fused = _fused(
        quantity,
        {"flops": _in_pass(0), "dram_bytes": _in_pass(1)},
        ("flops", "dram_bytes"),
        verdict,
    )
    assert fused.quality is Quality.ESTIMATED
    assert fused.reason in flowed(EXPLANATION)


def _in_pass(index):
    """Two Measurement stand-ins, one per pass, as `_fused` reads them."""
    return [dataclasses.replace(_MEASUREMENT, pass_index=index)]


def test_the_documented_witnesses_are_the_coded_ones():
    page = flowed(EXPLANATION)
    for counter in WITNESS_COUNTERS:
        assert f"retired {counter.replace('flops', 'FLOPs')}" in page, counter


def test_the_documented_threshold_is_the_configured_one():
    threshold = Config().passes_witness_threshold
    assert f"witness = {threshold}" in HOW_TO
    assert f"{threshold:.0%} threshold" in flowed(HOW_TO)
    assert f"{threshold:.0%} threshold" in flowed(EXPLANATION)


def test_the_subject_is_reachable_and_replaces_the_old_section():
    guide = (ROOT / "docs" / "guide" / "index.md").read_text()
    assert "multi-pass/index" in guide
    for page in ("run-a-multi-pass-acquisition", "the-witness-between-passes"):
        assert page in INDEX, page
    old = (ROOT / "docs" / "guide" / "getting-started.md").read_text()
    assert "## Multi-pass runs" not in old
    assert "--multi-pass" not in old
