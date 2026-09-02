"""The Explanations subject quotes the prompt and the questions verbatim.

Everything this subject publishes is text the product writes: the role
given to the model, the shape of the prompt built from a Run, the
consent question, and the sentence a job log gets instead of advice.
These tests hold each quotation against its writer.
"""

from __future__ import annotations

import io
from pathlib import Path

from nunatak.console import Console
from nunatak.explain import consent, prompt
from nunatak.explain.pi import Identity
from nunatak.explain.prompt import SYSTEM_PROMPT

ROOT = Path(__file__).resolve().parents[1]
SUBJECT = ROOT / "docs" / "guide" / "explanations"
INDEX = (SUBJECT / "index.md").read_text()
HOW_TO = (SUBJECT / "get-advice-on-your-hotspots.md").read_text()
CONTRACT = (SUBJECT / "the-contract-with-the-model.md").read_text()


def test_the_quoted_role_is_the_one_sent():
    """The page publishes the system prompt; a reworded role must not
    leave a stale copy in the documentation."""
    assert SYSTEM_PROMPT.strip() in CONTRACT


def test_the_published_prompt_has_the_sections_the_builder_writes():
    """The prompt shown is a real one; its headings are the builder's."""
    from nunatak.analysis import diagnose
    from nunatak.pivot import SourceExtract
    from tests.test_analysis import hotspot, measurement, run_with

    spot = hotspot("laplacian", file="/src/kernels.c")
    run = run_with([measurement(spot, "task-clock", 2e9, "ns")])
    run.source_extracts = [
        SourceExtract(
            hotspot=spot, file="/src/kernels.c", text="lap[i] = u[i];", start_line=7
        )
    ]
    asked, _ = prompt.requests(run, diagnose(run))
    written = asked[0].prompt
    for heading in ("## Machine", "## Diagnostic for", "## Source ("):
        assert heading in written, heading
        assert heading in CONTRACT, heading
    assert "Explain this behavior and suggest optimizations." in written
    assert "Explain this behavior and suggest optimizations." in CONTRACT


def test_a_hotspot_without_source_is_withheld_with_its_reason():
    """The rule the contract page states as `no source, no explanation`."""
    from nunatak.analysis import diagnose
    from tests.test_analysis import hotspot, measurement, run_with

    spot = hotspot("kernel")
    run = run_with([measurement(spot, "task-clock", 2e9, "ns")])
    asked, withheld = prompt.requests(run, diagnose(run))
    assert asked == []
    assert withheld and withheld[0].reason
    assert "No source, no explanation" in CONTRACT


def test_the_quoted_consent_question_is_the_asked_one(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    monkeypatch.setenv("TERM", "xterm")
    monkeypatch.setenv("NO_COLOR", "1")
    stream = io.StringIO()
    stream.isatty = lambda: True
    asked = []
    consent.obtain(
        Identity(provider="opencode-go", model="deepseek-v4-flash", remote=True),
        "examples",
        Console(stream=stream),
        ask=lambda question: asked.append(question) or "",
    )
    announced = stream.getvalue().strip()
    assert announced in HOW_TO
    assert asked[0].strip() in HOW_TO


def test_the_sentence_a_job_log_gets_is_the_quoted_one():
    console = Console(stream=io.StringIO())
    allowed, why = consent.obtain(
        Identity(provider="hosted", model=None, remote=True), "examples", console
    )
    assert allowed is False
    assert why in HOW_TO


def test_the_subject_is_reachable_and_replaces_the_old_section():
    guide = (ROOT / "docs" / "guide" / "index.md").read_text()
    assert "explanations/index" in guide
    for page in ("get-advice-on-your-hotspots", "the-contract-with-the-model"):
        assert page in INDEX, page
    old = (ROOT / "docs" / "guide" / "getting-started.md").read_text()
    assert "nunatak explain" not in old
    assert not (ROOT / "docs" / "spec" / "09-explication.md").exists()
