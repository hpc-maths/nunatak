"""The Workflows recipes quote flags, codes, thresholds and payload keys.

Each recipe tells a reader to type a command and to read a field of a
JSON payload. Both come from code that moves, so the quotations are
checked against their source rather than proofread.
"""

from __future__ import annotations

import inspect
from pathlib import Path

from nunatak.cli import build_parser
from nunatak.cli.compare import _delta
from nunatak.compare import Delta, Side, _findings
from nunatak.config import Config
from nunatak.exit_codes import STRICT_VIOLATION
from nunatak.explain import consent
from tests.test_docs import _verbs

ROOT = Path(__file__).resolve().parents[1]
GROUP = ROOT / "docs" / "guide" / "workflows"
INDEX = (GROUP / "index.md").read_text()
SCHEDULER = (GROUP / "profile-a-job-on-a-scheduler.md").read_text()
CI = (GROUP / "gate-performance-in-ci.md").read_text()
NO_EGRESS = (GROUP / "profile-where-source-cannot-leave.md").read_text()
PITFALLS = (GROUP / "common-pitfalls.md").read_text()


def flowed(text):
    """The page's prose with its line wrapping removed."""
    return " ".join(text.split())


def _options(verb):
    """Every option string the parser accepts for one verb."""
    actions = _verbs(build_parser())[verb]._actions
    return {option for action in actions for option in action.option_strings}


def test_the_quoted_flags_are_the_parsers_own():
    for flag in ("--strict", "--json", "--name", "-o", "--no-calibrate"):
        assert flag in _options("run"), flag
    assert "--no-source" in _options("report")
    assert "--no-explain" in _options("run")
    assert "--json" in _options("compare")


def test_the_quoted_strict_exit_code_is_the_reserved_one():
    assert f"exits {STRICT_VIOLATION}" in flowed(CI)
    assert f"exits {STRICT_VIOLATION}" in flowed(SCHEDULER)


def test_the_quoted_thresholds_are_the_configured_ones():
    config = Config()
    assert f"{config.coverage_threshold:.0%} coverage" in flowed(PITFALLS)
    assert f"beyond {config.sampling_rank_threshold} ranks" in flowed(SCHEDULER)


def test_the_gate_reads_keys_the_payload_carries():
    payload_keys = _delta(
        Delta("laplacian", "kernels.c", Side(2.0, 1000), Side(1.0, 1000))
    )
    for key in ("function", "file", "change", "change_fraction", "significant"):
        assert key in payload_keys, key
        assert f".{key}" in CI, key


def test_the_named_non_comparability_is_one_the_diff_can_raise():
    assert "different-machines" in PITFALLS
    assert '"different-machines"' in inspect.getsource(_findings)


def test_the_consent_file_is_where_agreements_live():
    assert consent.directory().parts[-2:] == ("nunatak", "consents")
    assert "~/.cache/nunatak/consents" in NO_EGRESS


def test_the_group_opens_the_guide_and_lists_its_recipes():
    guide = (ROOT / "docs" / "guide" / "index.md").read_text()
    lines = [line.strip() for line in guide.splitlines()]
    assert lines.index("workflows/index") < lines.index("reading-what-nunatak-tells-you")
    for page in (
        "profile-a-job-on-a-scheduler",
        "gate-performance-in-ci",
        "profile-where-source-cannot-leave",
        "common-pitfalls",
    ):
        assert page in INDEX, page
