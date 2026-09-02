"""The Getting started section quotes the example programs and the tools.

The sizes, the kernel names and the analytic rate come from `examples/`,
which is compiled by the test lane and edited by whoever learns on it.
The install page quotes doctor's own remedy and the declared Python
floor. These tests keep the four in step.
"""

from __future__ import annotations

import inspect
import re
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from nunatak.cli import doctor

ROOT = Path(__file__).resolve().parents[1]
SECTION = ROOT / "docs" / "getting-started"
INDEX = (SECTION / "index.md").read_text()
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
