"""The explanation layer against a real pi, with a stub model.

Everything below runs the actual pi binary: its process start, its nine
hardening flags, its event stream, and nunatak's reading of it. Only the
model is stood in for - by a loopback endpoint that needs no key - which
is what makes this lane free of credentials, of network and of cost.

The lane opts in with `-m pi`, and a missing pi fails it rather than
skipping: a lane that silently skips is a lane that rots.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from nunatak.explain import consent, store
from nunatak.explain.pi import locate
from tests import pi_stub
from tests.test_analysis import hotspot, measurement, run_with

pytestmark = pytest.mark.pi

SOURCE_FILE = "/src/app.c"


@pytest.fixture
def stub(tmp_path, monkeypatch):
    """A live endpoint, and a nunatak that reads pi's files from the home
    it was written into - both the constants nunatak reads and the HOME
    pi itself resolves."""
    if shutil.which("pi") is None:
        pytest.fail(
            "the pi lane needs pi on PATH: "
            "npm install -g @earendil-works/pi-coding-agent"
        )
    home = tmp_path / "home"
    generator = pi_stub.serve(home)
    provider = next(generator)
    monkeypatch.setattr("nunatak.explain.pi.SETTINGS", provider.settings)
    monkeypatch.setattr("nunatak.explain.pi.MODELS", provider.models)
    monkeypatch.setenv("HOME", str(home))
    # pi refreshes model catalogues at startup otherwise, which is the
    # one thing in this lane that would reach the network.
    monkeypatch.setenv("PI_OFFLINE", "1")
    try:
        yield provider
    finally:
        generator.close()


def eligible_run(directory: Path):
    """A Run with one line-level Hotspot and its source: the shape that
    makes a Hotspot eligible for advice."""
    from nunatak.pivot import SourceExtract, write_run

    spot = hotspot("axpy", file=SOURCE_FILE)
    run = run_with([measurement(spot, "task-clock", 2e9, "ns")])
    run.source_extracts = [
        SourceExtract(
            hotspot=spot,
            file=SOURCE_FILE,
            start_line=4,
            end_line=5,
            text="for (int i = 0; i < n; i++) y[i] = a * x[i] + y[i];",
        )
    ]
    write_run(directory, run)
    return directory


def test_the_stub_provider_is_seen_as_local_and_ready(stub):
    """doctor's row, live: the version pi answers with, the provider its
    settings name, the loopback verdict, and what `pi auth check` says."""
    from nunatak.collect.execution import SubprocessExecutor
    from nunatak.explain import pi as pi_tool

    from nunatak.config import Config

    executor = SubprocessExecutor()
    located = locate(executor, Config())
    assert located is not None, "pi did not answer with a version"
    identity = pi_tool.identity(executor)
    assert identity.provider == pi_stub.PROVIDER
    assert identity.model == pi_stub.MODEL
    assert identity.remote is False, "a loopback base URL is not a remote provider"
    assert pi_tool.readiness(executor, located, identity.provider) == "credentials ready (api_key)"


def test_the_advice_lands_in_the_run_with_no_agreement_asked(stub, tmp_path, monkeypatch, capsys):
    """A local provider sends nothing anywhere, so nothing is asked -
    and the advice arrives with the provider and model that served it."""
    from nunatak.cli import principal

    directory = eligible_run(tmp_path / "run")
    monkeypatch.chdir(tmp_path)
    assert consent.granted("solver", pi_stub.PROVIDER) is False
    assert principal(["explain", str(directory)]) == 0
    log = capsys.readouterr().err
    assert "advice received" in log
    entry = store.read(directory)["explanations"][0]
    assert entry["advice"] == pi_stub.ANSWER
    assert entry["provider"] == pi_stub.PROVIDER
    assert entry["model"] == pi_stub.MODEL
    assert consent.granted("solver", pi_stub.PROVIDER) is False


def test_pi_receives_the_prompt_and_no_tools(stub, tmp_path, monkeypatch, capsys):
    """The hardening flags are ours to pass and pi's to honour, so the
    endpoint is where the guarantee is checked: one user message, which
    is the prompt, and no tool declared for the model to call."""
    from nunatak.cli import principal
    from nunatak.explain.prompt import SYSTEM_PROMPT

    directory = eligible_run(tmp_path / "run")
    monkeypatch.chdir(tmp_path)
    assert principal(["explain", str(directory)]) == 0
    capsys.readouterr()
    assert len(stub.requests) == 1
    body = stub.requests[0]
    assert "tools" not in body, "pi was asked for --no-tools and declared tools anyway"
    system = [m for m in body["messages"] if m["role"] == "system"]
    assert system and system[0]["content"].startswith(SYSTEM_PROMPT[:60])
    (prompt,) = stub.prompts()
    assert "axpy" in prompt
    assert "y[i] = a * x[i] + y[i]" in prompt


def test_the_exchange_leaves_nothing_behind(stub, tmp_path, monkeypatch, capsys):
    """`--no-session` is one of the nine flags, and the home pi resolved
    is where its effect is visible: the prompt and the answer are not
    persisted anywhere but in the Run."""
    from nunatak.cli import principal

    directory = eligible_run(tmp_path / "run")
    monkeypatch.chdir(tmp_path)
    assert principal(["explain", str(directory)]) == 0
    capsys.readouterr()
    written = {path.name for path in (stub.home / ".pi").rglob("*") if path.is_file()}
    # The catalogue cache is pi's own housekeeping; a session is not.
    assert written <= {"models.json", "settings.json", "auth.json", "models-store.json"}, (
        f"pi persisted more than its own catalogue: {sorted(written)}"
    )


def test_the_answer_streams_as_the_model_writes_it(stub, tmp_path, monkeypatch):
    """The endpoint answers in two deltas; the caller must see them as
    fragments rather than as one block at the end."""
    from nunatak.collect.execution import SubprocessExecutor
    from nunatak.config import Config
    from nunatak.explain.generate import generate
    from nunatak.explain.prompt import Request

    located = locate(SubprocessExecutor(), Config())
    fragments: list[str] = []
    explanations, failures = generate(
        SubprocessExecutor(),
        located,
        [Request(hotspot=hotspot("axpy", file=SOURCE_FILE), prompt="explain axpy")],
        on_token=fragments.append,
    )
    assert not failures, failures
    assert explanations[0].advice == pi_stub.ANSWER
    assert len(fragments) > 1, fragments
    assert "".join(fragments) == pi_stub.ANSWER


def test_a_provider_error_is_surfaced_not_swallowed(stub, tmp_path, monkeypatch, capsys):
    """pi exits 0 after its own retries, leaving the failure in the event
    stream as the only witness. The endpoint refuses on purpose, and the
    verb must fail with the provider's own words rather than store an
    empty answer."""
    from nunatak.cli import principal
    from nunatak.exit_codes import FAILURE_BEFORE_LAUNCH

    directory = eligible_run(tmp_path / "run")
    monkeypatch.chdir(tmp_path)
    qualified = f"{pi_stub.PROVIDER}/{pi_stub.ERROR_MODEL}"
    assert principal(["explain", str(directory), "--model", qualified]) == (
        FAILURE_BEFORE_LAUNCH
    )
    log = capsys.readouterr().err
    assert "provider error" in log
    assert "the stub refused" in log
    assert store.read(directory) is None


def test_a_bare_model_id_keeps_the_recipient_unknown(stub, tmp_path, monkeypatch, capsys):
    """`--model` is passed to pi verbatim, and a bare id proves no
    provider: pi's fuzzy matching is pi's own, so the recipient stays
    unknown and the consent path stays on - which is the safe side."""
    from nunatak.cli import principal

    directory = eligible_run(tmp_path / "run")
    monkeypatch.chdir(tmp_path)
    assert principal(["explain", str(directory), "--model", pi_stub.MODEL]) == 0
    log = capsys.readouterr().err
    assert "explanations withheld" in log
    assert "no source was sent" in log
    assert store.read(directory) is None
