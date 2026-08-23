"""CLI contract: exit codes, Run directory, JSON outputs, naming cascade."""

import json
import stat
import sys

import pytest

from nunatak.cli import principal
from nunatak.pivot import read_run

OK = [sys.executable, "-c", "raise SystemExit(0)"]


@pytest.fixture(autouse=True)
def in_tmp_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def run_json(capsys, extra=()):
    code = principal(["run", "--json", *extra, "--", *OK])
    summary = json.loads(capsys.readouterr().out)
    return code, summary


class TestExitCodes:
    def test_the_application_exit_code_is_propagated(self):
        assert principal(["run", "--", sys.executable, "-c", "raise SystemExit(7)"]) == 7
        assert principal(["run", "--", *OK]) == 0

    def test_a_missing_command_exits_127(self):
        assert principal(["run", "--", "definitely-not-a-command-xyz"]) == 127

    def test_a_non_executable_file_exits_126(self, tmp_path):
        script = tmp_path / "script.sh"
        script.write_text("#!/bin/sh\n")
        script.chmod(stat.S_IRUSR | stat.S_IWUSR)
        assert principal(["run", "--", str(script)]) == 126

    def test_a_usage_error_exits_125(self):
        assert principal(["run"]) == 125  # no command after --
        assert principal(["frobnicate"]) == 125

    def test_strict_turns_degradations_into_error_121(self, tmp_path, monkeypatch):
        # Force a degradation on every platform: an unusable collector
        # path for Linux's perf and macOS's sample alike.
        site = tmp_path / "site.toml"
        site.write_text(
            '[tools]\nperf = "/nonexistent/perf"\nsample = "/nonexistent/sample"\n'
        )
        monkeypatch.setenv("NUNATAK_SITE_CONFIG", str(site))
        assert principal(["run", "--strict", "--", *OK]) == 121

    def test_without_strict_a_degradation_never_fails_the_run(self):
        assert principal(["run", "--", *OK]) == 0


class TestRunDirectory:
    def test_the_run_is_a_single_self_sufficient_directory(self, tmp_path, capsys):
        code, summary = run_json(capsys)
        assert code == 0
        run = read_run(summary["run"])
        assert run.exit_code == 0
        assert run.passes[0].exit_code == 0
        assert run.provenance.effective_configuration["runs_dir"] == ".nunatak"

    def test_runs_land_under_a_gitignored_runs_dir(self, tmp_path, capsys):
        _, summary = run_json(capsys)
        runs_dir = tmp_path / ".nunatak"
        assert (runs_dir / ".gitignore").read_text() == "*\n"
        assert str(runs_dir) in summary["run"]

    def test_output_flag_names_the_exact_directory(self, tmp_path, capsys):
        _, summary = run_json(capsys, extra=["-o", str(tmp_path / "exact")])
        assert summary["run"] == str(tmp_path / "exact")
        assert not (tmp_path / ".nunatak").exists()

    def test_a_failing_application_still_gets_its_run_written(self, tmp_path, capsys):
        code = principal(
            ["run", "--json", "--", sys.executable, "-c", "raise SystemExit(3)"]
        )
        summary = json.loads(capsys.readouterr().out)
        assert code == 3
        assert read_run(summary["run"]).exit_code == 3


class TestNamingCascade:
    def test_the_project_file_names_the_run(self, tmp_path, capsys):
        (tmp_path / "nunatak.toml").write_text('name = "solver"\n')
        _, summary = run_json(capsys)
        assert summary["name"].startswith("solver-")

    def test_the_name_flag_always_wins(self, tmp_path, capsys):
        (tmp_path / "nunatak.toml").write_text('name = "solver"\n')
        _, summary = run_json(capsys, extra=["--name", "forced"])
        assert summary["name"].startswith("forced-")


class TestDoctor:
    def test_doctor_reports_checks_and_exits_zero(self, capsys):
        assert principal(["doctor", "--json"]) == 0
        report = json.loads(capsys.readouterr().out)
        names = {check["name"] for check in report["checks"]}
        assert "cpu-collector" in names
        assert "llvm" in names

    def test_doctor_inspects_the_target_when_given(self, capsys):
        assert principal(["doctor", "--json", "--", *OK]) == 0
        report = json.loads(capsys.readouterr().out)
        target = [c for c in report["checks"] if c["name"] == "target-binary"]
        assert target and target[0]["status"] == "ok"


class TestLlvmWindow:
    """The validated LLVM window is declared, never enforced: below the
    minimum degrades, above the tested bound only warns."""

    @staticmethod
    def verdict(major):
        from nunatak.cli.doctor import _llvm
        from nunatak.attribution.symbolizer import Symbolizer

        return _llvm(Symbolizer(path="/usr/bin/llvm-symbolizer", major=major))

    def test_inside_the_window_is_plainly_ok(self):
        from nunatak.attribution.symbolizer import RECOMMENDED_LLVM, TESTED_LLVM

        for major in (RECOMMENDED_LLVM, TESTED_LLVM):
            check = self.verdict(major)
            assert check.status == "ok"
            assert check.degradation is None

    def test_above_the_window_warns_without_refusing_or_degrading(self):
        from nunatak.attribution.symbolizer import TESTED_LLVM

        check = self.verdict(TESTED_LLVM + 4)
        assert check.status == "warning"
        assert "not yet validated" in check.detail
        assert str(TESTED_LLVM) in check.remedy
        assert check.degradation is None

    def test_below_the_minimum_still_degrades(self):
        from nunatak.attribution.symbolizer import MINIMUM_LLVM

        check = self.verdict(MINIMUM_LLVM - 1)
        assert check.status == "warning"
        assert check.degradation is not None
        assert check.degradation.name == "llvm-too-old"


class TestAttributionCeiling:
    """doctor announces how far attribution will go, before the run,
    against genuine llvm-readelf section inventories."""

    def checks(self, tmp_path, readelf_stdout=None, readelf_exit=0, symbolizer=True):
        from nunatak.cli.doctor import light_checks
        from nunatak.attribution import Symbolizer
        from nunatak.config import Config
        from tests.support import ScriptedExecutor

        binary = tmp_path / "solver"
        binary.write_bytes(b"\x7fELF")
        executor = ScriptedExecutor()
        if readelf_stdout is not None or readelf_exit:
            executor.on(
                "llvm-readelf", stdout=readelf_stdout or "", exit_code=readelf_exit
            )
        located = (
            Symbolizer(path="/usr/lib/llvm-19/bin/llvm-symbolizer", major=19)
            if symbolizer
            else None
        )
        results = light_checks(
            executor, Config(), [str(binary)], cpu=(None, None), llvm=(located,)
        )
        return {c.name: c for c in results}

    def test_a_debug_build_reaches_line_level(self, tmp_path):
        from tests.support import READELF_WITH_SYMTAB

        check = self.checks(tmp_path, READELF_WITH_SYMTAB)["target-attribution"]
        assert check.status == "ok"
        assert "line-level" in check.detail

    def test_without_debug_information_doctor_claims_g(self, tmp_path):
        from tests.support import READELF_NO_DEBUG

        check = self.checks(tmp_path, READELF_NO_DEBUG)["target-attribution"]
        assert check.status == "warning"
        assert "function level" in check.detail
        assert "-g" in check.remedy

    def test_a_stripped_binary_is_capped_at_symbol_level(self, tmp_path):
        from tests.support import READELF_STRIPPED_LIB

        check = self.checks(tmp_path, READELF_STRIPPED_LIB)["target-attribution"]
        assert check.status == "warning"
        assert "symbol level" in check.detail

    def test_an_uninspectable_binary_is_said_not_guessed(self, tmp_path):
        check = self.checks(tmp_path, readelf_exit=1)["target-attribution"]
        assert check.status == "warning"
        assert "cannot inspect" in check.detail

    def test_without_llvm_no_ceiling_is_claimed(self, tmp_path):
        assert "target-attribution" not in self.checks(tmp_path, symbolizer=False)

    def test_a_missing_target_yields_no_ceiling_row(self, capsys):
        from nunatak.cli.doctor import light_checks
        from nunatak.config import Config
        from tests.support import ScriptedExecutor

        results = light_checks(
            ScriptedExecutor(), Config(), ["/nowhere/solver"], cpu=(None, None), llvm=(None,)
        )
        names = [c.name for c in results]
        assert "target-binary" in names
        assert "target-attribution" not in names
