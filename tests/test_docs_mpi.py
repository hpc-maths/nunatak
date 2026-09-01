"""The MPI subject quotes what a reader will see in their own terminal:
the launchers nunatak recognises, the threshold that decides who samples,
the two lines the summary prints for a world of ranks, and the directory
each rank writes into. Every one of them is decided in the code, and a
page quoting yesterday's shape teaches a reader to expect it.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from nunatak import analysis, launch, rank, summary
from nunatak.config import Config
from nunatak.ingestion import mpip_report
from tests.test_analysis import aggregate, hotspot, ranked, run_with

ROOT = Path(__file__).resolve().parents[1]
SUBJECT = ROOT / "docs" / "guide" / "mpi"
HOW_TO = (SUBJECT / "profile-an-mpi-job.md").read_text()
EXPLANATION = (SUBJECT / "the-two-collection-layers.md").read_text()
CATALOGUE = (ROOT / "docs" / "reference" / "degradations.md").read_text()
MPIP_FIXTURE = ROOT / "tests" / "fixtures" / "mpi_workload.4.2586003.1.mpiP"

TOPOLOGY = re.compile(
    r"ranks: \d+ \(\d+ sampled\); busiest rank \d+ at \d+\.\d\dx the mean;"
    r" MPI holds \d+% of the time"
)
UNSAMPLED = re.compile(
    r"- \d+ ranks not sampled \([\d, ]+\): their Hotspot measurements are"
    r" unavailable, never extrapolated"
)


def test_the_documented_launchers_are_the_recognised_ones():
    """The how-to lists them by name: one missing sends a reader to
    wrap a launch nunatak would have wrapped anyway."""
    for launcher in launch.MPI_LAUNCHERS:
        assert f"`{launcher}`" in HOW_TO, f"{launcher} fans out ranks and is unstated"


def test_the_documented_threshold_is_the_default():
    threshold = Config().sampling_rank_threshold
    assert threshold == 64
    assert f"beyond {threshold} ranks" in HOW_TO or f"{threshold} ranks" in HOW_TO
    assert f"{threshold} by default" in EXPLANATION


def test_the_documented_topology_line_is_the_one_the_summary_renders():
    run = run_with(
        [aggregate("task-clock", 1e9, rank=0), aggregate("task-clock", 3e9, rank=1)]
        + [aggregate("app_time", 2e9, rank=r) for r in (0, 1)]
        + [aggregate("mpi_time", 1e9, rank=r) for r in (0, 1)]
    )
    (rendered,) = [
        line for line in summary.summarize(run, analysis.diagnose(run))
        if line.startswith("ranks:")
    ]
    assert TOPOLOGY.fullmatch(rendered), rendered
    quoted = [line for line in _quoted() if line.startswith("ranks:")]
    assert quoted, "no page shows the topology line a reader will read"
    for line in quoted:
        assert TOPOLOGY.fullmatch(line), line


def test_the_documented_admission_is_the_one_the_summary_renders():
    run = run_with(
        [ranked(hotspot(), "task-clock", 1e9, "ns", rank=0)]
        + [aggregate("task-clock", 1e9, rank=r) for r in (1, 2)]
    )
    (rendered,) = [
        line.strip() for line in summary.summarize(run, analysis.diagnose(run))
        if "not sampled" in line
    ]
    assert UNSAMPLED.fullmatch(rendered), rendered
    quoted = [line.strip() for line in _quoted() if "not sampled" in line]
    assert quoted, "no page shows what an unsampled rank costs"
    for line in quoted:
        assert UNSAMPLED.fullmatch(line), line


def test_the_documented_mpi_counters_are_the_ingested_ones(tmp_path):
    (tmp_path / MPIP_FIXTURE.name).write_text(MPIP_FIXTURE.read_text())
    measurements, _, _ = mpip_report.ingest_mpip(tmp_path, expected=True)
    for counter in {m.counter for m in measurements}:
        assert f"`{counter}`" in EXPLANATION, f"{counter} reaches a Run and is unstated"


def test_a_rank_writes_where_the_page_says_it_does(tmp_path):
    """The shim is the one thing a reader cannot observe from outside,
    so the page names the directory. Without perf the rank still runs
    the application bare and still writes its metadata there."""
    exit_code = rank.measure(
        tmp_path,
        ["/usr/bin/true"] if os.path.exists("/usr/bin/true") else ["true"],
        {"OMPI_COMM_WORLD_RANK": "3", "OMPI_COMM_WORLD_SIZE": "8",
         "OMPI_COMM_WORLD_LOCAL_RANK": "1"},
    )
    assert exit_code == 0
    assert (tmp_path / "rank-3" / rank.RANK_META).is_file()
    assert "collect/rank-<n>/" in EXPLANATION


def test_the_named_degradations_have_a_catalogue_entry():
    """A degradation name in a page is a name a reader will paste."""
    anchors = set(re.findall(r"^### ([a-z0-9-]+)$", CATALOGUE, re.MULTILINE))
    named = {
        name
        for name in re.findall(r"`([a-z]+(?:-[a-z]+)+)`", HOW_TO + EXPLANATION)
        if name.endswith(("-unavailable", "-missing", "-incomplete"))
    }
    assert named, "the subject names no degradation at all"
    assert named <= anchors, f"named with no entry: {sorted(named - anchors)}"


def _quoted() -> list[str]:
    """Every line of every fenced block in the two pages."""
    lines = []
    for page in (HOW_TO, EXPLANATION):
        for block in re.findall(r"^```.*?^```", page, re.MULTILINE | re.DOTALL):
            lines += block.splitlines()[1:-1]
    return lines
