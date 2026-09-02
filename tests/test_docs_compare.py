"""The compare subject quotes three terminal transcripts.

A transcript in a page is a claim about what the tool prints. These
tests hold the sentences the pages quote against the code that renders
them, so a reworded verdict cannot leave the documentation behind.
"""

from __future__ import annotations

from pathlib import Path

from nunatak.cli.compare import lines
from nunatak.compare import APPEARANCE_FLOOR, compare
from tests.test_analysis import hotspot, measurement
from tests.test_compare import run_of

ROOT = Path(__file__).resolve().parents[1]
SUBJECT = ROOT / "docs" / "guide" / "compare"
INDEX = (SUBJECT / "index.md").read_text()
HOW_TO = (SUBJECT / "compare-two-runs.md").read_text()
EXPLANATION = (SUBJECT / "what-makes-a-delta-real.md").read_text()


def rendered(before_value, after_value, samples=2500):
    """The terminal diff of one function measured on both sides."""
    spot = hotspot("kernel")
    sides = []
    for value in (before_value, after_value):
        if value is None:
            sides.append(run_of([]))
            continue
        one = measurement(spot, "task-clock", value, "ns", samples=samples)
        sides.append(run_of([one]))
    return "\n".join(lines(compare(*sides)))


def test_the_three_quoted_verdicts_are_the_rendered_ones():
    assert "(significant, sampling error ±" in rendered(2.0e9, 1.0e9)
    within = rendered(2.0e9, 2.02e9)
    assert "(within the sampling error of ±" in within
    assert "not a difference" in within
    assert "vanished (was " in rendered(2.0e9, None)
    for verdict in (
        "(significant, sampling error ±",
        "(within the sampling error of ±",
        "not a difference",
        "vanished (was ",
    ):
        assert verdict in HOW_TO, verdict


def test_the_documented_floor_is_the_coded_one():
    """The explanation states the floor as a percentage; it is one
    constant, and a reader who tunes their expectations to it deserves
    the current value."""
    assert f"less than {APPEARANCE_FLOOR:.0%}" in EXPLANATION


def test_the_quoted_warning_is_the_written_one(tmp_path, capsys):
    """The how-to's third transcript opens on a declared finding."""
    import json

    from nunatak.cli import principal
    from nunatak.pivot import write_run

    directories = []
    for name in ("before", "after"):
        run = run_of([measurement(hotspot("kernel"), "task-clock", 2.0e9, "ns")])
        run.name = name
        directory = tmp_path / name
        write_run(directory, run)
        directories.append(directory)
    manifest = json.loads((directories[1] / "manifest.json").read_text())
    manifest["run"]["command"] = ["./stencil", "2048"]
    (directories[1] / "manifest.json").write_text(json.dumps(manifest))

    assert principal(["compare", *map(str, directories)]) == 0
    written = capsys.readouterr().err
    quoted = "not directly comparable [different-commands]: the commands differ ("
    assert quoted in written
    assert quoted in HOW_TO


def test_the_boolean_a_pipeline_reads_is_the_payload_key(tmp_path, capsys):
    import json

    from nunatak.cli import principal
    from nunatak.pivot import write_run

    directories = []
    for name, value in (("before", 2.0e9), ("after", 1.0e9)):
        run = run_of([measurement(hotspot("kernel"), "task-clock", value, "ns")])
        run.name = name
        directory = tmp_path / name
        write_run(directory, run)
        directories.append(directory)
    assert principal(["compare", *map(str, directories), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert "significant" in payload["deltas"][0]
    assert "`significant` boolean" in HOW_TO


def test_the_subject_is_reachable_and_complete():
    guide = (ROOT / "docs" / "guide" / "index.md").read_text()
    assert "compare/index" in guide
    for page in ("compare-two-runs", "what-makes-a-delta-real"):
        assert page in INDEX, page
    old = (ROOT / "docs" / "guide" / "getting-started.md").read_text()
    assert "nunatak compare" not in old, "the verb is documented twice"
