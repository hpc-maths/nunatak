"""The Getting started section quotes the example programs and the tools.

The sizes, the kernel names and the analytic rate come from `examples/`,
which is compiled by the test lane and edited by whoever learns on it.
The install page quotes doctor's own remedy and the declared Python
floor. These tests keep the four in step.
"""

from __future__ import annotations

import inspect
import json
import re
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from nunatak import summary
from nunatak.cli import doctor
from nunatak.collect.events import FLOP_PERIOD

ROOT = Path(__file__).resolve().parents[1]
SECTION = ROOT / "docs" / "getting-started"
INDEX = (SECTION / "index.md").read_text()
SCOPE = (SECTION / "what-nunatak-is.md").read_text()
COUNTERS = (SECTION / "check-the-counters.md").read_text()


def _gemm_payload():
    """The payload of the report this page publishes and quotes."""
    page = (ROOT / "docs" / "_static" / "example-gemm-report.html").read_text()
    embedded = re.search(
        r'<script[^>]*type="application/json"[^>]*>(.*?)</script>', page, re.S
    )
    assert embedded is not None, "the published gemm report carries no payload"
    return json.loads(embedded.group(1))
INSTALL = (SECTION / "installing.md").read_text()
EXAMPLES = (SECTION / "the-example-programs.md").read_text()
SOURCES = ROOT / "examples"


def flowed(text):
    """The page's prose with its line wrapping removed."""
    return " ".join(text.split())


def _default(source, variable):
    """The default a program falls back on for one of its arguments."""
    pattern = rf"int {variable} = argc > \d+ \? atoi\(argv\[\d+\]\) : (\d+);"
    return int(re.search(pattern, (SOURCES / source).read_text()).group(1))


def test_the_quoted_sizes_are_the_programs_defaults():
    grid = _default("stencil.c", "n")
    steps = _default("stencil.c", "steps")
    order = _default("gemm.c", "n")
    page = flowed(EXAMPLES)
    assert f"{grid} x {grid} grid" in page
    assert f"{steps} explicit time steps" in page
    assert f"n = {order}" in page
    assert f"{2 * order**3}" in page


def test_the_quoted_kernels_are_the_ones_a_profile_will_name():
    kernels = (SOURCES / "kernels.c").read_text()
    for kernel in ("laplacian", "reaction", "update"):
        assert f"void {kernel}(" in kernels, kernel
        assert f"`{kernel}`" in EXAMPLES, kernel


def test_the_analytic_rate_is_the_one_gemm_prints():
    assert "GFLOP/s analytic" in (SOURCES / "gemm.c").read_text()
    assert "GFLOP/s analytic" in EXAMPLES


def test_the_declared_python_floor_is_the_packages_own():
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text())
    floor = metadata["project"]["requires-python"].lstrip(">=")
    assert f"Python {floor} or newer" in flowed(INSTALL)


def test_the_quoted_remedy_is_doctors_own():
    # Adjacent string literals are joined: doctor wraps that remedy over
    # two source lines.
    source = re.sub(r'"\s*\n\s*"', "", inspect.getsource(doctor))
    remedy = (
        "install Node.js and pi (npm install -g "
        "@earendil-works/pi-coding-agent), or set tools.pi in nunatak.toml"
    )
    assert remedy in source
    assert remedy in flowed(INSTALL)


def test_the_section_opens_the_site_and_lists_its_pages():
    landing = (ROOT / "docs" / "index.md").read_text().splitlines()
    entries = [line.strip() for line in landing]
    assert entries.index("getting-started/index") < entries.index("guide/index")
    for page in ("installing", "the-example-programs"):
        assert page in INDEX, page
    assert "getting-started/the-example-programs" in (SOURCES / "README.md").read_text()


def test_the_scope_page_opens_the_section_and_refuses_four_things():
    entries = [line.strip() for line in INDEX.splitlines()]
    assert entries.index("what-nunatak-is") < entries.index("installing")
    for refusal in ("not a tracer", "not a correctness debugger", "not a dashboard"):
        assert refusal in flowed(SCOPE), refusal
    assert "does not replace" in flowed(SCOPE) and "Instruments" in SCOPE


def test_the_scope_page_promises_nothing_unbuilt():
    """The site documents what runs: the GPU rows of the specification
    are a design, and a coverage table is exactly where they would leak
    out as a promise."""
    assert "designed and not built" in flowed(SCOPE)
    for collector in ("nsys", "ncu", "rocprofv3"):
        assert collector not in SCOPE, collector


def test_the_analytic_flop_count_is_the_one_gemm_computes():
    """The control's whole value is that this number is not measured."""
    order = _default("gemm.c", "n")
    assert f"`2 x {order}^3` is {2 * order**3}" in flowed(COUNTERS)
    assert str(2 * order**3) in COUNTERS


def test_the_two_compared_rates_are_within_the_claimed_margin():
    """The page claims the counters and the program's clock agree to
    better than 2%. The claim is arithmetic on two quoted numbers, so it
    is checked rather than proofread."""
    page = flowed(COUNTERS)
    counters, analytic = (
        float(value)
        for value in re.search(
            r"([\d.]+) GFLOP/s from the counters against ([\d.]+) GFLOP/s",
            page,
        ).groups()
    )
    assert abs(counters - analytic) / analytic < 0.02
    assert "under 2% apart" in page


def test_the_quoted_sampling_period_is_the_coded_one():
    assert str(FLOP_PERIOD) in COUNTERS


def test_the_quoted_loop_facts_are_the_published_ones():
    """The same iteration is described on two pages; the loop analysis
    page owns the table."""
    published = flowed(
        (ROOT / "docs" / "guide" / "static-loop-analysis.md").read_text()
    )
    page = flowed(COUNTERS)
    for fact in ("164", "42", "656", "248", "38.8", "39.19"):
        assert fact in published, fact
        assert fact in page, fact


def test_both_tutorials_close_the_section():
    entries = [line.strip() for line in INDEX.splitlines()]
    assert entries.index("tutorial") < entries.index("check-the-counters")
    assert entries.index("the-example-programs") < entries.index("tutorial")
    assert "check-the-counters" in (SECTION / "the-example-programs.md").read_text()


def test_the_counter_page_shows_the_html_output_and_its_roofline():
    """The check ends on a chart, so the page has to reach the page that
    draws it - and the artifact it links has to exist."""
    assert "_static/example-gemm-report.html" in COUNTERS
    assert (ROOT / "docs" / "_static" / "example-gemm-report.html").is_file()
    page = flowed(COUNTERS)
    assert "roofline" in page
    for element in ("ridge point", "double-precision peak", "pale points"):
        assert element in page, element


def test_the_quoted_finding_is_the_published_runs_own():
    """The page quotes the report it publishes, so the two cannot drift:
    every number below is rebuilt through the summary renderer."""
    payload = _gemm_payload()
    coverage = payload["coverage"]
    assert (
        f"{coverage['samples']} samples of {coverage['time_base']}"
        f" over {coverage['seconds']:.3g} s" in COUNTERS
    )
    hotspot = next(h for h in payload["hotspots"] if h["name"] == "gemm")
    share = summary._percent(hotspot["share"]["value"])
    assert (
        f"  gemm ({hotspot['resolution_level']}) - {share} of the sampled time"
        f" - {hotspot['classification']}" in COUNTERS
    )
    assert (
        f"    achieved {summary._flops(hotspot['achieved']['value'])}"
        f" of {summary._flops(hotspot['attainable']['value'])} attainable:"
        f" {summary._percent(hotspot['envelope_fraction']['value'])}"
        " of the envelope" in COUNTERS
    )
    intensity = hotspot["dram_intensity"]
    assert f"    DRAM intensity {intensity['value']:.3g} flop/byte" in COUNTERS
    assert f"downgraded to estimated: {intensity['reason']}" in COUNTERS


def test_the_quoted_loop_facts_are_the_published_runs_own():
    loop = next(
        h for h in _gemm_payload()["hotspots"] if h["name"] == "gemm"
    )["loop"]
    page = flowed(COUNTERS)
    assert f"{loop['instructions']} instructions" in page
    assert f"{loop['flops_per_iteration']:.0f} FLOPs" in page
    assert f"{loop['vector_width_bits']} bits" in page
    assert f"{loop['loaded_bytes']} bytes loaded and {loop['stored_bytes']} stored" in page
    assert f"{loop['l1_intensity']['value']:.3g} flop/byte" in page
    assert f"{loop['cycle_bounds']['ports']} port-bound" in page
    assert f"{loop['cycle_bounds']['steady_state']} in steady" in page


def test_the_measured_ceiling_is_the_one_the_page_names():
    peak = next(
        c
        for c in _gemm_payload()["machine"]["ceilings"]
        if c["name"] == "flops_dp"
    )
    assert peak["quality"] == "measured"
    assert f"{summary._flops(peak['value'])}" in COUNTERS


def test_the_page_publishes_the_run_it_quotes():
    payload = _gemm_payload()
    assert payload["run"]["command"] == ["./examples/gemm"]
    assert "_static/example-gemm-report.html" in COUNTERS
