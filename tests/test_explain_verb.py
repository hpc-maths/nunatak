"""The explain verb: generation through pi, consent, persistence.

The pi event fixtures are verbatim captures from pi 0.84.1: a served
answer, and a provider failure - where pi exits 0 after three internal
retries, leaving `stopReason: "error"` in the event stream as the only
witness.
"""

import io
import json
import os
from pathlib import Path

from nunatak.console import Console
from nunatak.explain import Explanation, Identity, Pi
from nunatak.explain import consent, store
from nunatak.explain.generate import _parse, generate
from nunatak.explain.prompt import SYSTEM_PROMPT, Request
from tests.support import ScriptedExecutor
from tests.test_analysis import hotspot

FIXTURES = Path(__file__).parent / "fixtures"
ANSWER = (FIXTURES / "pi-json-answer.txt").read_text()
PROVIDER_ERROR = (FIXTURES / "pi-json-provider-error.txt").read_text()

PI = Pi(path="pi", version="0.84.1")

ENTRY = (
    Path(__file__).resolve().parent.parent
    / "corpus"
    / "recordings"
    / "pi"
    / "0.84.1"
    / "darwin-arm64"
    / "triad-c"
)


def request(name="main"):
    return Request(hotspot=hotspot(name), prompt=f"explain {name}")


class TestParse:
    def test_the_final_assistant_text_is_the_advice(self):
        text, model, provider = _parse(ANSWER)
        assert text == "Hello!"
        assert model == "deepseek-v4-flash"
        assert provider == "opencode-go"

    def test_a_provider_error_is_surfaced_verbatim_despite_exit_zero(self):
        assert _parse(PROVIDER_ERROR) == "provider error: Connection error."

    def test_an_unreadable_stream_is_reported_not_taken_for_empty(self):
        assert _parse("") == "no assistant answer in pi's output"
        assert _parse("not json at all\n") == "no assistant answer in pi's output"

    def test_an_honestly_empty_answer_is_named_as_such(self):
        message = {
            "type": "message_end",
            "message": {"role": "assistant", "content": [], "stopReason": "stop"},
        }
        assert _parse(json.dumps(message)) == "the model answered with no text"


class TestGenerate:
    def test_a_served_answer_becomes_an_explanation(self):
        executor = ScriptedExecutor().on("pi", stdout=ANSWER)
        explanations, failures = generate(executor, PI, [request()])
        assert failures == []
        assert explanations == [
            Explanation(
                hotspot=hotspot(),
                advice="Hello!",
                model="deepseek-v4-flash",
                provider="opencode-go",
            )
        ]

    def test_pi_is_reduced_to_a_bare_model_call(self):
        executor = ScriptedExecutor().on("pi", stdout=ANSWER)
        generate(executor, PI, [request()], model="somewhere/some-model")
        argv = executor.calls[0]
        for flag in ("--no-session", "--no-tools", "--no-extensions",
                     "--no-skills", "--no-context-files", "--no-prompt-templates"):
            assert flag in argv
        assert argv[argv.index("--system-prompt") + 1] == SYSTEM_PROMPT
        assert argv[argv.index("--model") + 1] == "somewhere/some-model"
        assert argv[-1] == "explain main"

    def test_failures_ride_next_to_successes(self):
        executor = (
            ScriptedExecutor()
            .on("pi", stdout=ANSWER)
            .on("pi", stdout=PROVIDER_ERROR)
        )
        explanations, failures = generate(
            executor, PI, [request("a"), request("b")]
        )
        assert len(explanations) == 1 and len(failures) == 1
        assert failures[0].error == "provider error: Connection error."

    def test_a_dead_pi_is_a_failure_with_its_exit_code(self):
        executor = ScriptedExecutor().on("pi", exit_code=127, stderr="gone")
        _, failures = generate(executor, PI, [request()])
        assert failures[0].error.startswith("pi exited with 127")

    def test_progress_fires_once_per_call(self):
        executor = ScriptedExecutor().on("pi", stdout=ANSWER).on("pi", stdout=ANSWER)
        seen = []
        generate(executor, PI, [request("a"), request("b")], on_done=seen.append)
        assert len(seen) == 2


def terminal_console(monkeypatch):
    monkeypatch.setenv("TERM", "xterm")
    monkeypatch.setenv("NO_COLOR", "1")
    stream = io.StringIO()
    stream.isatty = lambda: True
    return Console(stream=stream), stream


class TestConsent:
    LOCAL = Identity(provider="local", model="tiny", remote=False)
    REMOTE = Identity(provider="hosted", model="big", remote=True)

    def test_a_local_provider_asks_nothing(self):
        console = Console(stream=io.StringIO())
        allowed, why = consent.obtain(self.LOCAL, "proj", console)
        assert (allowed, why) == (True, None)
        assert not consent.directory().exists()

    def test_no_terminal_and_no_memory_withholds_with_the_way_forward(self):
        console = Console(stream=io.StringIO())
        allowed, why = consent.obtain(self.REMOTE, "proj", console)
        assert allowed is False
        assert "login node" in why

    def test_a_yes_is_memorized_for_the_project_and_recipient(self, monkeypatch):
        console, _ = terminal_console(monkeypatch)
        allowed, _ = consent.obtain(
            self.REMOTE, "proj", console, ask=lambda _: "y"
        )
        assert allowed is True
        assert consent.granted("proj", "hosted")

        def never(_):
            raise AssertionError("a memorized agreement must not re-ask")

        again, _ = consent.obtain(self.REMOTE, "proj", console, ask=never)
        assert again is True

    def test_a_no_withholds_and_memorizes_nothing(self, monkeypatch):
        console, _ = terminal_console(monkeypatch)
        allowed, why = consent.obtain(
            self.REMOTE, "proj", console, ask=lambda _: ""
        )
        assert allowed is False
        assert why == "consent declined: no source was sent"
        assert not consent.granted("proj", "hosted")

    def test_switching_providers_asks_again(self, monkeypatch):
        console, _ = terminal_console(monkeypatch)
        consent.record("proj", "hosted")
        other = Identity(provider="elsewhere", model=None, remote=True)
        allowed, _ = consent.obtain(other, "proj", console, ask=lambda _: "")
        assert allowed is False

    def test_the_recipient_is_the_provider_else_the_flag_else_the_default(self):
        assert consent.recipient(self.REMOTE) == "hosted"
        nobody = Identity(provider=None, model="pat", remote=True)
        assert consent.recipient(nobody, "pat") == "pat"
        assert consent.recipient(nobody) == "pi's built-in default provider"


class TestStore:
    def test_the_advice_round_trips_next_to_the_pivot(self, tmp_path):
        explanation = Explanation(
            hotspot=hotspot("axpy"),
            advice="Fuse the loops.",
            model="some-model",
            provider="somewhere",
        )
        path = store.write(tmp_path, [explanation])
        assert path.name == "explanations.json"
        payload = store.read(tmp_path)
        assert payload["format"]["label"] == "advice"
        entry = payload["explanations"][0]
        assert entry["hotspot"]["name"] == "axpy"
        assert entry["advice"] == "Fuse the loops."
        assert entry["provider"] == "somewhere"

    def test_a_future_schema_reads_as_absent(self, tmp_path):
        store.write(tmp_path, [])
        raw = json.loads((tmp_path / store.FILE).read_text())
        raw["format"]["schema"] = store.SCHEMA + 1
        (tmp_path / store.FILE).write_text(json.dumps(raw))
        assert store.read(tmp_path) is None

    def test_regeneration_replaces_wholesale(self, tmp_path):
        first = Explanation(hotspot=hotspot("a"), advice="x", model=None, provider=None)
        second = Explanation(hotspot=hotspot("b"), advice="y", model=None, provider=None)
        store.write(tmp_path, [first])
        store.write(tmp_path, [second])
        names = [e["hotspot"]["name"] for e in store.read(tmp_path)["explanations"]]
        assert names == ["b"]


class TestVerb:
    def test_an_unusable_pi_is_an_error_with_the_remedy(self, tmp_path, monkeypatch, capsys):
        from nunatak.cli import principal
        from nunatak.pivot import SourceExtract, write_run
        from tests.test_analysis import measurement, run_with

        spot = hotspot("axpy")
        run = run_with([measurement(spot, "task-clock", 2e9, "ns")])
        run.source_extracts = [
            SourceExtract(hotspot=spot, file="/src/app.c", text="a[i] = x;")
        ]
        directory = tmp_path / "run"
        write_run(directory, run)
        (tmp_path / "nunatak.toml").write_text('[tools]\npi = "/nonexistent"\n')
        monkeypatch.chdir(tmp_path)
        assert principal(["explain", str(directory)]) == 125
        assert "tools.pi" in capsys.readouterr().err

    def test_without_any_run_the_verb_says_so(self, tmp_path, monkeypatch, capsys):
        from nunatak.cli import principal

        monkeypatch.chdir(tmp_path)
        assert principal(["explain"]) == 125
        assert "no Run" in capsys.readouterr().err


class TestReplayedExplain:
    """The corpus entry: a real deepseek answer recorded through pi on the
    capture Mac, replayed against a synthetic single-Hotspot Run. One
    Hotspot, because a replay serves recordings in order while live
    calls run in parallel."""

    def test_the_recorded_advice_lands_in_the_run(self, tmp_path, monkeypatch, capsys):
        from nunatak.cli import principal
        from nunatak.pivot import SourceExtract, write_run
        from tests.test_analysis import measurement, run_with

        spot = hotspot("axpy")
        run = run_with([measurement(spot, "task-clock", 2e9, "ns")])
        run.source_extracts = [
            SourceExtract(
                hotspot=spot,
                file="/src/app.c",
                start_line=4,
                end_line=5,
                text="for (int i = 0; i < n; i++) y[i] = a * x[i] + y[i];",
            )
        ]
        directory = tmp_path / "run"
        write_run(directory, run)
        # The recorded identity is the capture Mac's: provider
        # opencode-go, remote. The agreement is cache-side, seeded here;
        # the project is the target's base name, ./solver.
        consent.record("solver", "opencode-go")
        monkeypatch.chdir(tmp_path)
        assert principal(["explain", str(directory), "--replay", str(ENTRY)]) == 0
        capsys.readouterr()
        payload = store.read(directory)
        entry = payload["explanations"][0]
        assert entry["hotspot"]["name"] == "axpy"
        assert entry["provider"] == "opencode-go"
        assert entry["model"] == "deepseek-v4-flash"
        assert entry["advice"].startswith("Line 5 is a streaming triad.")

    def test_without_consent_the_replay_withholds_and_sends_nothing(
        self, tmp_path, monkeypatch, capsys
    ):
        from nunatak.cli import principal
        from nunatak.pivot import SourceExtract, write_run
        from tests.test_analysis import measurement, run_with

        spot = hotspot("axpy")
        run = run_with([measurement(spot, "task-clock", 2e9, "ns")])
        run.source_extracts = [
            SourceExtract(hotspot=spot, file="/src/app.c", text="y[i] = a * x[i];")
        ]
        directory = tmp_path / "run"
        write_run(directory, run)
        monkeypatch.chdir(tmp_path)
        assert principal(["explain", str(directory), "--replay", str(ENTRY)]) == 0
        assert "withheld" in capsys.readouterr().err
        assert store.read(directory) is None
