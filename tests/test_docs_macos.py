"""The macOS subject quotes a real run on Apple Silicon.

The numbers in its tables were read from a Run of the shipped examples
on an M5 Max, so they cannot be recomputed here. What is held is what
the platform's code promises: the two collectors and their counters,
the aggregates powermetrics leaves with the reasons they carry, and the
absence a missing FLOP counter produces.
"""

from __future__ import annotations

import inspect
from pathlib import Path

from nunatak import powerfilter
from nunatak.ingestion import sample_report, xctrace_profile

ROOT = Path(__file__).resolve().parents[1]
SUBJECT = ROOT / "docs" / "guide" / "macos"
INDEX = (SUBJECT / "index.md").read_text()
HOW_TO = (SUBJECT / "profile-on-macos.md").read_text()
EXPLANATION = (SUBJECT / "what-temporal-sampling-can-say.md").read_text()


def flowed(text):
    """The page's prose with its line wrapping removed."""
    return " ".join(text.split())


def test_the_two_counters_are_the_ones_the_rungs_report():
    """`cpu-clock` for Running threads only, `wall-clock` when blocked
    threads are sampled too: the pages name both and say why."""
    assert "cpu-clock" in inspect.getsource(xctrace_profile)
    assert "wall-clock" in inspect.getsource(sample_report)
    assert "cpu-clock" in HOW_TO and "wall-clock" in HOW_TO
    page = flowed(EXPLANATION)
    assert "`cpu-clock`: time on a CPU" in page
    assert "`wall-clock`: time on the" in page


def test_the_energy_reasons_are_the_ones_the_filter_attaches():
    source = inspect.getsource(powerfilter)
    page = flowed(HOW_TO)
    for aggregate in ("energy_impact", "cpu_energy", "gpu_energy"):
        assert aggregate in source, aggregate
        assert f"`{aggregate}`" in page, aggregate
    assert "not joules" in page


def test_the_stated_absence_is_the_one_the_analysis_writes():
    """A macOS Run has no FLOP counter, so the placement is absent with
    that reason rather than empty - the how-to quotes it verbatim."""
    from nunatak.analysis import FLOP_COUNTERS

    assert f"no {FLOP_COUNTERS[0]} raw counter in this Run" in HOW_TO
    assert f"no {FLOP_COUNTERS[0]}\nraw counter in this Run" in EXPLANATION


def test_the_subject_is_reachable_and_replaces_the_old_section():
    guide = (ROOT / "docs" / "guide" / "index.md").read_text()
    assert "macos/index" in guide
    for page in ("profile-on-macos", "what-temporal-sampling-can-say"):
        assert page in INDEX, page
    old = (ROOT / "docs" / "guide" / "getting-started.md").read_text()
    assert "## macOS: the temporal mode" not in old
