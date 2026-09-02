"""The tutorial quotes one published Run, line by line.

Every number on the page comes from `docs/_static/example-report.html` -
the Run the reader can open - or from the source of `examples/stencil`.
The renderers that format those numbers are exercised here too, so a
change to either the payload or the formatting fails the page rather
than ageing it silently.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from nunatak import summary
from nunatak.analysis import STATISTICAL_FLOOR_SAMPLES

ROOT = Path(__file__).resolve().parents[1]
TUTORIAL = (ROOT / "docs" / "getting-started" / "tutorial.md").read_text()
SECTION = (ROOT / "docs" / "getting-started" / "index.md").read_text()
MAP = (ROOT / "docs" / "guide" / "getting-started.md").read_text()
COMPARE_HOW_TO = (
    ROOT / "docs" / "guide" / "compare" / "compare-two-runs.md"
).read_text()


def flowed(text):
    """The page's prose with its line wrapping removed."""
    return " ".join(text.split())


def _published_payload():
    """The payload embedded in the report this page tells you to open."""
    page = (ROOT / "docs" / "_static" / "example-report.html").read_text()
    embedded = re.search(
        r'<script[^>]*type="application/json"[^>]*>(.*?)</script>', page, re.S
    )
    assert embedded is not None, "the published report carries no payload"
    return json.loads(embedded.group(1))


PAYLOAD = _published_payload()
HOTSPOTS = {hotspot["name"]: hotspot for hotspot in PAYLOAD["hotspots"]}


def test_the_quoted_coverage_is_the_published_runs_own():
    coverage = PAYLOAD["coverage"]
    headline = (
        f"{coverage['samples']} samples of {coverage['time_base']}"
        f" over {coverage['seconds']:.3g} s"
    )
    assert headline in TUTORIAL
    assert f"{len(PAYLOAD['hotspots'])} Hotspots above the statistical floor" in TUTORIAL
    assert PAYLOAD["floor_samples"] == STATISTICAL_FLOOR_SAMPLES
    assert PAYLOAD["run"]["name"] in TUTORIAL


def test_every_quoted_finding_is_the_one_the_report_carries():
    for name in ("reaction", "update", "laplacian"):
        hotspot = HOTSPOTS[name]
        share = summary._percent(hotspot["share"]["value"])
        head = (
            f"  {name} ({hotspot['resolution_level']})"
            f" - {share} of the sampled time - {hotspot['classification']}"
        )
        assert head in TUTORIAL, head
        evidence = (
            f"    achieved {summary._flops(hotspot['achieved']['value'])}"
            f" of {summary._flops(hotspot['attainable']['value'])} attainable:"
            f" {summary._percent(hotspot['envelope_fraction']['value'])}"
            " of the envelope"
        )
        assert evidence in TUTORIAL, evidence
        intensity = f"    DRAM intensity {hotspot['dram_intensity']['value']:.3g} flop/byte"
        assert intensity in TUTORIAL, intensity


def test_the_unplaceable_hotspots_are_quoted_with_their_reasons():
    for name in ("main", "[unknown]"):
        hotspot = HOTSPOTS[name]
        reason = hotspot["classification_reason"]
        assert f"no placement: {reason}" in TUTORIAL, name


def test_the_quoted_downgrade_reason_is_the_payloads_own():
    reason = HOTSPOTS["laplacian"]["dram_intensity"]["reason"]
    assert f"downgraded to estimated: {reason}" in TUTORIAL
    assert reason.split(";")[0] in flowed(TUTORIAL)


def test_the_quoted_loop_facts_are_the_measured_ones():
    loop = HOTSPOTS["laplacian"]["loop"]
    page = flowed(TUTORIAL)
    total = loop["loaded_bytes"] + loop["stored_bytes"]
    assert (
        f"{loop['instructions']} instructions, {loop['flops_per_iteration']:.0f} flops"
        f" and {total} bytes per iteration" in page
    )
    assert f"{loop['loaded_bytes']} loaded, {loop['stored_bytes']} stored" in page
    assert f"{loop['l1_intensity']['value']:.3g} flop/byte" in page
    assert loop["vector_fp"] == 0 and loop["scalar_fp"] == 4


def test_the_quoted_line_shares_are_the_measured_ones():
    lines = HOTSPOTS["laplacian"]["lines"]
    hottest = max(lines, key=lambda entry: entry["share"])
    page = flowed(TUTORIAL)
    assert f"Line {hottest['line']}, the inner `for`, holds" in page
    assert f"holds {hottest['share']:.0%} of this Hotspot's samples" in page


def test_the_quoted_source_is_the_source_the_run_carries():
    extract = HOTSPOTS["laplacian"]["source"]["text"]
    # The extract spans lines around the Hotspot, so it opens mid-header
    # and runs into the next function: the quoted block is the function.
    start = extract.index("void laplacian")
    body = extract[start : extract.index("\n}", start) + 2]
    assert body in TUTORIAL
    assert body in (ROOT / "examples" / "kernels.c").read_text()


def test_the_quoted_degradation_is_the_one_the_run_declared():
    stacks = next(
        degradation
        for degradation in PAYLOAD["degradations"]
        if degradation["name"] == "call-stacks-unavailable"
    )
    assert stacks["message"] in TUTORIAL
    assert stacks["remedy"] in TUTORIAL


def test_the_comparison_is_quoted_from_the_page_that_owns_it():
    """The same Run pair appears in the compare how-to: one transcript,
    two readers, and no room for the two to drift apart."""
    for line in (
        "total: 8.53 s -> 6.17 s: -27.7% (significant, sampling error ±1.4%)",
        "laplacian (kernels.c) vanished (was 2.42 s)",
    ):
        assert line in TUTORIAL, line
        assert line in COMPARE_HOW_TO, line


def test_the_tutorial_closes_the_section_and_the_old_page_is_a_map():
    assert "tutorial" in SECTION
    assert "getting-started/tutorial" in MAP
    for subject in ("mpi", "python", "attribution", "source", "report", "compare"):
        assert f"{subject}/index.md" in MAP, subject
    assert "## " not in MAP, "the map page argues where it should point"
