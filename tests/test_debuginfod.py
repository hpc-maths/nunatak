"""debuginfod controls: used if configured, never required, never slow.

The client lives in the tools, not in nunatak: these tests check the
environment the symbolizers are invoked under, because that environment
is the whole control surface - the command lines never change, which is
what keeps recorded corpus entries replaying identically.
"""

from nunatak.attribution import attribute, debuginfod
from nunatak.attribution.addr2line import Addr2Line
from nunatak.cli import doctor
from nunatak.config import Config, load
from nunatak.ingestion import measurements_from_samples
from nunatak.ingestion.samples import Sample
from tests.support import (
    ADDR2LINE_DEBUG,
    GNU_READELF_SYMBOLS_FP,
    ScriptedExecutor,
)

SERVER = {"DEBUGINFOD_URLS": "https://debuginfod.ubuntu.com", "PATH": "/usr/bin"}


class TestEnvironment:
    def test_without_a_server_there_is_nothing_to_control(self):
        assert debuginfod.environment(Config(), {"PATH": "/usr/bin"}) is None

    def test_an_empty_urls_variable_is_no_server(self):
        assert debuginfod.environment(Config(), {"DEBUGINFOD_URLS": ""}) is None

    def test_the_default_bounds_the_wait(self):
        composed = debuginfod.environment(Config(), SERVER)
        assert composed["DEBUGINFOD_TIMEOUT"] == "10"
        assert composed["DEBUGINFOD_URLS"] == SERVER["DEBUGINFOD_URLS"]

    def test_the_timeout_is_configuration(self, tmp_path):
        (tmp_path / "nunatak.toml").write_text("[debuginfod]\ntimeout = 3\n")
        config, effective = load(tmp_path)
        assert debuginfod.environment(config, SERVER)["DEBUGINFOD_TIMEOUT"] == "3"
        assert effective["debuginfod.timeout"] == 3

    def test_an_explicit_user_timeout_is_an_explicit_choice(self):
        environment = dict(SERVER, DEBUGINFOD_TIMEOUT="120")
        composed = debuginfod.environment(Config(), environment)
        assert composed["DEBUGINFOD_TIMEOUT"] == "120"

    def test_disabled_strips_the_client_trigger(self, tmp_path):
        (tmp_path / "nunatak.toml").write_text("[debuginfod]\nenabled = false\n")
        config, effective = load(tmp_path)
        composed = debuginfod.environment(config, SERVER)
        assert "DEBUGINFOD_URLS" not in composed
        assert composed["PATH"] == "/usr/bin"
        assert effective["debuginfod.enabled"] is False


class TestThroughSymbolization:
    def test_the_controls_reach_the_tool_invocation(self):
        executor = (
            ScriptedExecutor()
            .on("readelf", stdout=GNU_READELF_SYMBOLS_FP)
            .on("addr2line", stdout=ADDR2LINE_DEBUG)
        )
        samples = [
            Sample(pid=1, tid=1, time_s=1.0, period=1000, counter="task-clock",
                   module="/tmp/workload", offset=0x11B8),
        ]
        measurements = measurements_from_samples(samples, {}, "n0")
        tool = Addr2Line(path="/usr/bin/addr2line", version="2.44")
        attribute(
            measurements, tool, executor,
            environment=debuginfod.environment(Config(), SERVER),
        )
        addr2line_call = next(
            env for argv, env in zip(executor.calls, executor.environments)
            if argv[0] == "/usr/bin/addr2line"
        )
        assert addr2line_call["DEBUGINFOD_TIMEOUT"] == "10"


class TestDoctor:
    def test_a_configured_server_is_reported(self, monkeypatch):
        monkeypatch.setenv("DEBUGINFOD_URLS", "https://a https://b")
        check = doctor._debuginfod(Config())
        assert check.status == "ok"
        assert "2 server(s)" in check.detail

    def test_no_server_is_no_finding(self, monkeypatch):
        monkeypatch.delenv("DEBUGINFOD_URLS", raising=False)
        assert doctor._debuginfod(Config()) is None

    def test_disabled_is_said_in_the_report(self, monkeypatch):
        monkeypatch.setenv("DEBUGINFOD_URLS", "https://a")
        check = doctor._debuginfod(Config(debuginfod_enabled=False))
        assert "disabled by nunatak.toml" in check.detail
