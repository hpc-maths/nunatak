"""The Python subject quotes the rows `doctor` prints, the grain a Python
Hotspot carries and the shapes the parsers key on. All four are decided
in the code, and a page that quotes an older shape teaches a reader to
look for something nunatak no longer prints.
"""

from __future__ import annotations

import re
from pathlib import Path

from nunatak.cli.doctor import _python_target
from nunatak.collect import interpreter
from nunatak.config import Config
from nunatak.ingestion import _python_hotspot
from nunatak.collect.perf import _PERF_MAP
from nunatak.ingestion.perf_script import _python_name
from nunatak.pivot import ResolutionLevel
from tests.support import ScriptedExecutor

ROOT = Path(__file__).resolve().parents[1]
SUBJECT = ROOT / "docs" / "guide" / "python"
HOW_TO = (SUBJECT / "profile-a-python-application.md").read_text()
EXPLANATION = (SUBJECT / "the-two-python-paths.md").read_text()
CATALOGUE = (ROOT / "docs" / "reference" / "degradations.md").read_text()


def test_the_documented_version_is_the_one_that_opens_the_door():
    major, minor = interpreter.TRAMPOLINES
    assert f"CPython {major}.{minor}" in EXPLANATION or f"{major}.{minor}" in EXPLANATION
    assert f"CPython {major}.{minor}" in HOW_TO


def test_the_documented_doctor_row_is_the_rendered_one():
    executor = ScriptedExecutor().on("python3", stdout="Python 3.13.3\n")
    row = _python_target(executor, Config(), ["python3", "solver.py"])
    assert row.status == "ok"
    assert f"{row.name}      " in HOW_TO, "the page quotes no python-target row"
    assert row.detail in HOW_TO, row.detail


def test_the_documented_fallback_row_is_the_rendered_one(monkeypatch):
    from nunatak.collect import pyspy

    monkeypatch.setattr(
        pyspy, "locate", lambda executor, config: (pyspy.PySpyAdapter(), "0.4.2")
    )
    executor = ScriptedExecutor().on("python3", stdout="Python 3.10.21\n")
    row = _python_target(executor, Config(), ["python3", "solver.py"])
    assert row.status == "warning"
    assert row.detail in HOW_TO, row.detail
    assert row.degradation.name in HOW_TO


def test_the_documented_silent_row_is_the_rendered_one(monkeypatch):
    """The row nobody captured live: without py-spy, the Python story is
    lost by name and the page shows what that row says."""
    from nunatak.collect import pyspy

    monkeypatch.setattr(pyspy, "locate", lambda executor, config: None)
    executor = ScriptedExecutor().on("python3", stdout="Python 3.10.21\n")
    row = _python_target(executor, Config(), ["python3", "solver.py"])
    assert row.degradation.name == "python-hotspots-unavailable"
    assert row.detail in HOW_TO, row.detail


def test_the_documented_trampoline_symbol_is_the_parsed_one():
    quoted = re.search(r"`py::([^`]+)`", EXPLANATION)
    assert quoted is not None, "the page shows no trampoline symbol"
    assert quoted.group(1) == "<function>:<file>"
    assert _python_name("py::sweep:/tmp/solver.py+0x6", "/tmp/perf-42.map+0x7a4b") == (
        "sweep", "/tmp/solver.py"
    )


def test_the_documented_map_path_is_the_retrieved_one():
    quoted = re.search(r"`(/tmp/perf-[^`]+)`", EXPLANATION)
    assert quoted is not None, "the page names no perf map"
    concrete = quoted.group(1).replace("<pid>", "3694811")
    assert _PERF_MAP.search(f"({concrete})"), quoted.group(1)


def test_the_documented_grain_is_the_hotspot_that_is_built():
    spot = _python_hotspot("sweep", "solver.py")
    assert spot.resolution_level is ResolutionLevel.FUNCTION
    assert spot.physical_identity is None
    assert spot.logical_identity.name == "sweep"
    assert spot.logical_identity.source_file == "solver.py"
    assert "`(file, function)`" in EXPLANATION


def test_the_named_degradations_have_a_catalogue_entry():
    anchors = set(re.findall(r"^### ([a-z0-9-]+)$", CATALOGUE, re.MULTILINE))
    named = {
        name
        for name in re.findall(r"`?([a-z]+(?:-[a-z]+)+)`?", HOW_TO + EXPLANATION)
        if name.startswith("python-")
        and name.endswith(("-unavailable", "-failed", "-missing", "-unparsed"))
    }
    assert named, "the subject names no degradation at all"
    assert named <= anchors, f"named with no entry: {sorted(named - anchors)}"
