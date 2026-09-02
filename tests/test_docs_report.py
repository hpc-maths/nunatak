"""The report subject publishes two artifacts and quotes what they say.

An artifact the reader opens cannot be misrepresented, but it can rot:
these tests hold the published files against the invariants that make
publishing them legitimate, and the quoted sentences against the code
that writes them.
"""

from __future__ import annotations

import re
from pathlib import Path

from nunatak.report.html import NO_SOURCE_REPORT, REPORT
from nunatak.report.payload import SCHEMA

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "docs" / "_static"
SUBJECT = ROOT / "docs" / "guide" / "report"
INDEX = (SUBJECT / "index.md").read_text()
HOW_TO = (SUBJECT / "regenerate-and-share-a-report.md").read_text()
EXPLANATION = (SUBJECT / "the-three-reading-levels.md").read_text()

PUBLISHED = {
    "example-report.html": "nunatak-report",
    "example-compare.html": "nunatak-compare",
}


def test_both_artifacts_are_published_and_linked():
    for name in PUBLISHED:
        assert (STATIC / name).is_file(), f"{name} is documented and absent"
        assert f"_static/{name}" in INDEX, f"{name} is published and unlinked"


def test_a_published_page_reaches_for_nothing():
    """Self-containedness is why publishing one is a file copy rather
    than machinery: a page that fetched anything would break the moment
    it was read offline, which is where reports are read."""
    for name in PUBLISHED:
        text = (STATIC / name).read_text()
        assert "http://" not in text and "https://" not in text, name
        assert "<script" in text, f"{name} carries no application"


def test_the_published_report_declares_the_schema_the_code_writes():
    """A payload that is a contract declares itself, and the published
    file has to be one this nunatak still writes."""
    text = (STATIC / "example-report.html").read_text()
    assert '"name":"nunatak-report"' in text or '"name": "nunatak-report"' in text
    assert f'"schema":{SCHEMA}' in text or f'"schema": {SCHEMA}' in text


def test_the_published_report_names_the_run_it_shows():
    """The provenance drawer answers "which Run am I reading", which is
    what makes an ageing artifact honest rather than misleading."""
    text = (STATIC / "example-report.html").read_text()
    named = re.search(r'"name":\s*"([^"]+)"', text)
    assert named is not None, "the payload names no Run"
    assert named.group(1) in text
    assert "EPYC" in text, "the machine the artifact was produced on is not in it"


def test_the_documented_file_names_are_the_written_ones():
    assert REPORT in HOW_TO
    assert NO_SOURCE_REPORT in HOW_TO
    assert f"`{NO_SOURCE_REPORT}`" in HOW_TO


def test_the_quoted_advice_absence_is_the_rendered_one():
    """The advice panel's own sentence, which is what a reader sees when
    no model answered - and what this page quotes."""
    sentence = "Generate it with"
    written = any(
        sentence in path.read_text()
        for path in (ROOT / "report-app" / "src").rglob("*.ts")
    )
    assert written, "the page no longer says how to get advice"
    assert sentence in EXPLANATION
    assert sentence in (STATIC / "example-report.html").read_text()
