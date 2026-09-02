"""The Machine subject quotes thresholds and one downgrade reason.

Every number on those pages is a constant of the calibration or a
sentence the probe writes. A reader who tunes a job around 60 seconds,
or distrusts a ceiling because its repetitions dispersed, is reading
code - these tests keep the two together.
"""

from __future__ import annotations

from pathlib import Path

from nunatak.calibration.kernel import (
    ANOMALY_FACTOR,
    BUDGET_SECONDS,
    DISPERSION_THRESHOLD,
    KERNELS,
    LOAD_PER_CORE_THRESHOLD,
    MILLISECONDS_PER_REPETITION,
    REPETITIONS,
    KernelRun,
    _pollution,
)
from nunatak.probe import _SHARED_MEMORY_REASON

ROOT = Path(__file__).resolve().parents[1]
SUBJECT = ROOT / "docs" / "guide" / "machine"
INDEX = (SUBJECT / "index.md").read_text()
HOW_TO = (SUBJECT / "calibrate-the-machine.md").read_text()
EXPLANATION = (SUBJECT / "what-a-ceiling-is-worth.md").read_text()


def flowed(text):
    """The page's prose with its line wrapping removed."""
    return " ".join(text.split())


def test_the_quoted_budget_and_repetitions_are_the_coded_ones():
    assert f"{BUDGET_SECONDS:.0f} seconds" in flowed(HOW_TO)
    assert f"{BUDGET_SECONDS:.0f}-second budget" in flowed(EXPLANATION)
    assert f"{REPETITIONS} repetitions" in flowed(EXPLANATION)
    assert f"{MILLISECONDS_PER_REPETITION} ms" in flowed(EXPLANATION)


def test_the_quoted_thresholds_are_the_coded_ones():
    page = flowed(EXPLANATION)
    assert f"more than {DISPERSION_THRESHOLD:.0%}" in page
    assert f"above {LOAD_PER_CORE_THRESHOLD:g} per allocated core" in page
    assert f"above {ANOMALY_FACTOR:g}x" in page


def test_the_documented_order_is_the_measured_one():
    """Without DRAM bandwidth and the double-precision peak there is no
    roofline, which is the reason the order is fixed and documented."""
    names = [name for name, _, _ in KERNELS]
    assert names == ["dram_bandwidth", "flops_dp", "flops_sp"]
    position = [HOW_TO.index(name) for name in names]
    assert position == sorted(position)


def test_the_quoted_dispersion_reason_is_the_rendered_one():
    outcome = KernelRun(
        kernel="triad", isa="avx2", threads=32, load=0.0, rates=(100.0, 82.0)
    )
    reasons = _pollution(outcome, threads=32, theoretical=None)
    assert reasons == ["repetitions disperse by 18%"]
    assert reasons[0] in flowed(EXPLANATION)


def test_the_single_node_declaration_is_the_probes_own():
    assert _SHARED_MEMORY_REASON in flowed(EXPLANATION)


def test_the_subject_is_reachable_and_replaces_the_old_sections():
    guide = (ROOT / "docs" / "guide" / "index.md").read_text()
    assert "machine/index" in guide
    for page in ("calibrate-the-machine", "what-a-ceiling-is-worth"):
        assert page in INDEX, page
    old = (ROOT / "docs" / "guide" / "getting-started.md").read_text()
    for heading in ("## Machine ceilings", "## Calibrating the Machine"):
        assert heading not in old, heading
