"""The explanation access layer: locating pi and reading its identity.

pi's configuration is the single source of providers and models; these
tests pin what nunatak reads from it - and that every verdict it cannot
prove falls on the safe side: remote.
"""

from nunatak.cli.doctor import _explanation
from nunatak.config import Config
from nunatak.explain import Identity, Pi, identity, locate, readiness
from nunatak.explain.pi import _lenient
from tests.support import ScriptedExecutor

# The shape of ~/.pi/agent/settings.json: plain JSON, the default
# provider and model among unrelated settings.
SETTINGS = """\
{
  "theme": "dark",
  "defaultProvider": "team-cluster",
  "defaultModel": "some-coder-32b",
  "lastChangelogVersion": "0.84.1"
}
"""

# The shape of ~/.pi/agent/models.json: JSON5 as pi accepts it - line
# and block comments, trailing commas, `//` inside the URLs a naive
# comment scrub would amputate. Keys are invented.
MODELS = """\
{
    "providers": {
        "team-cluster": {
            "baseUrl": "https://llm.example.org/v1",
            "api": "openai-completions",
            "apiKey": "sk-not-a-real-key",
            "models": [
                {
                    "id": "some-coder-32b",
                    "contextWindow": 256000,
                },
            ]
        },
        "local": {
            "baseUrl": "http://127.0.0.1:1234/v1",
            "api": "openai-completions",
            "apiKey": "sk-not-a-real-key-either",
            "models": [
                {
                    "id": "tiny-model"
                    // "reasoning": true
                },
            ],
        }, /* a block comment */
    }
}
"""


def executor_with_pi(settings=SETTINGS, models=MODELS):
    """An executor where pi answers, with pi's files as given."""
    executor = ScriptedExecutor()
    executor.on("pi", stdout="0.84.1\n")
    executor.on("cat", stdout=settings)
    executor.on("cat", stdout=models)
    return executor


class TestLocate:
    def test_a_version_banner_is_the_proof_pi_runs(self):
        executor = ScriptedExecutor().on("pi", stdout="0.84.1\n")
        located = locate(executor, Config())
        assert located == Pi(path="pi", version="0.84.1")

    def test_the_tools_override_replaces_the_default(self):
        executor = ScriptedExecutor().on("pi", stdout="0.84.1\n")
        located = locate(executor, Config(tools={"pi": "/opt/pi/bin/pi"}))
        assert located.path == "/opt/pi/bin/pi"
        assert executor.calls[0][0] == "/opt/pi/bin/pi"

    def test_an_absent_or_failing_pi_is_none(self):
        executor = ScriptedExecutor().on("pi", exit_code=127, stderr="not found")
        assert locate(executor, Config()) is None

    def test_something_else_answering_at_that_name_is_not_pi(self):
        executor = ScriptedExecutor().on("pi", stdout="usage: pi [options]\n")
        assert locate(executor, Config()) is None


class TestIdentity:
    def test_reads_the_default_provider_and_model_from_pi(self):
        who = identity(executor_with_pi())
        assert who.provider == "team-cluster"
        assert who.model == "some-coder-32b"

    def test_an_https_endpoint_is_remote(self):
        assert identity(executor_with_pi()).remote is True

    def test_a_loopback_endpoint_is_provably_local(self):
        settings = SETTINGS.replace("team-cluster", "local")
        who = identity(executor_with_pi(settings=settings))
        assert who.remote is False

    def test_a_builtin_provider_absent_from_models_json_is_remote(self):
        # pi's hosted catalog never appears in the user file: nothing
        # proves such a provider local.
        settings = SETTINGS.replace("team-cluster", "some-hosted-service")
        who = identity(executor_with_pi(settings=settings))
        assert who.provider == "some-hosted-service"
        assert who.remote is True

    def test_missing_settings_leave_pi_its_builtin_default(self):
        executor = ScriptedExecutor()
        executor.on("cat", exit_code=1, stderr="No such file")
        who = identity(executor)
        assert who == Identity(provider=None, model=None, remote=True)

    def test_an_unparseable_models_file_cannot_prove_local(self):
        who = identity(executor_with_pi(models='{"providers": broken'))
        assert who.remote is True


class TestLenientJson:
    def test_comments_and_trailing_commas_are_pi_liberties(self):
        parsed = _lenient(MODELS)
        assert parsed["providers"]["local"]["models"][0]["id"] == "tiny-model"

    def test_double_slashes_inside_strings_survive(self):
        parsed = _lenient(MODELS)
        assert parsed["providers"]["local"]["baseUrl"] == "http://127.0.0.1:1234/v1"

    def test_a_comment_between_comma_and_bracket_is_still_trailing(self):
        parsed = _lenient('{"a": [1, // said\n]}')
        assert parsed == {"a": [1]}


class TestReadiness:
    def test_the_credential_verdict_is_displayed_verbatim(self):
        executor = ScriptedExecutor().on(
            "pi",
            stdout='{"status":"ready","provider":"team-cluster","authType":"api_key"}\n',
        )
        sentence = readiness(executor, Pi(path="pi", version="0.84.1"), "team-cluster")
        assert sentence == "credentials ready (api_key)"
        assert executor.calls[0][:4] == ["pi", "auth", "check", "--provider"]

    def test_an_unreadable_answer_is_no_verdict(self):
        executor = ScriptedExecutor().on("pi", stdout="TypeError: boom\n")
        assert readiness(executor, Pi(path="pi", version="0.84.1"), "x") is None


class TestExplanationCheck:
    def test_absence_degrades_by_name_and_names_the_path(self):
        executor = ScriptedExecutor().on("pi", exit_code=127)
        check = _explanation(executor, Config(tools={"pi": "/nonexistent"}))
        assert check.status == "missing"
        assert check.degradation is not None
        assert check.degradation.name == "explanation-unavailable"
        assert "/nonexistent" in check.degradation.message

    def test_presence_names_provider_locality_model_and_credentials(self):
        executor = executor_with_pi()
        executor.on(
            "pi",
            stdout='{"status":"ready","provider":"team-cluster","authType":"api_key"}\n',
        )
        check = _explanation(executor, Config())
        assert check.status == "ok"
        assert check.degradation is None
        assert "provider team-cluster (remote)" in check.detail
        assert "model some-coder-32b" in check.detail
        assert "credentials ready" in check.detail

    def test_a_local_provider_reads_local(self):
        executor = executor_with_pi(
            settings=SETTINGS.replace("team-cluster", "local")
        )
        executor.on("pi", stdout='{"status":"ready","authType":"api_key"}\n')
        check = _explanation(executor, Config())
        assert "provider local (local)" in check.detail

    def test_no_default_provider_is_still_ok_and_treated_as_remote(self):
        executor = ScriptedExecutor()
        executor.on("pi", stdout="0.84.1\n")
        executor.on("cat", exit_code=1)
        check = _explanation(executor, Config())
        assert check.status == "ok"
        assert "treated as remote" in check.detail
