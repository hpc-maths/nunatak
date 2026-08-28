"""The report page and the report verb: self-contained, regenerable.

The stub bundle from conftest keeps these tests hermetic: what is under
test is the embedding, the wiring and the degradation - the app itself
is TypeScript, checked by its own toolchain.
"""

import json
from pathlib import Path

import pytest

from nunatak import analysis
from nunatak.cli import principal
from nunatak.pivot import write_run
from nunatak.report import html
from tests.test_analysis import balanced, hotspot, run_with

SOURCE_FILE = "/src/app.c"


@pytest.fixture
def written_run(tmp_path, monkeypatch):
    """A Run directory under `<cwd>/.nunatak`, cwd moved to tmp_path."""
    monkeypatch.chdir(tmp_path)
    directory = tmp_path / ".nunatak" / "solver-20260811-120000"
    run = run_with(balanced(hotspot(), flops=1.6e10, bytes_=8.0e9, seconds=0.1))
    write_run(directory, run)
    return directory, run


class TestRender:
    def payload(self, run):
        from nunatak import report

        return report.build(run, analysis.diagnose(run))

    def test_the_page_is_self_contained(self, written_run):
        _, run = written_run
        page = html.render(self.payload(run))
        assert page.startswith("<!doctype html>")
        assert '<script type="application/json" id="nunatak-payload">' in page
        assert 'console.log("stub bundle")' in page
        assert "body { color: inherit }" in page
        assert "src=" not in page and "href=" not in page

    def test_the_payload_cannot_close_its_script_element(self, written_run):
        _, run = written_run
        payload = self.payload(run)
        payload["run"]["name"] = "</script><script>alert(1)</script>"
        page = html.render(payload)
        assert "</script><script>alert(1)" not in page
        assert "<\\/script>" in page

    def test_write_report_lands_in_the_run_directory(self, written_run):
        directory, run = written_run
        path = html.write_report(directory, run, analysis.diagnose(run))
        assert path == directory / "report.html"
        assert path.read_text(encoding="utf-8").startswith("<!doctype html>")


class TestReportVerb:
    def test_without_argument_the_most_recent_run_is_taken(self, written_run, capsys):
        directory, _ = written_run
        older = directory.parent / "solver-20260810-080000"
        write_run(older, run_with(balanced(hotspot(), 1.6e10, 8.0e9, 0.1)))
        assert principal(["report", "--json"]) == 0
        paths = json.loads(capsys.readouterr().out)
        assert paths["run"] == str(directory)
        assert Path(paths["report"]).is_file()

    def test_an_explicit_run_directory_wins(self, written_run, capsys):
        directory, _ = written_run
        assert principal(["report", str(directory), "--json"]) == 0
        assert json.loads(capsys.readouterr().out)["run"] == str(directory)

    def test_without_any_run_the_verb_fails_before_launch(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert principal(["report"]) == 125

    def test_a_directory_that_is_not_a_run_fails_before_launch(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "not-a-run").mkdir()
        assert principal(["report", str(tmp_path / "not-a-run")]) == 125

    def test_without_the_compiled_app_the_verb_says_how_to_get_it(
        self, written_run, monkeypatch, tmp_path_factory, capsys
    ):
        monkeypatch.setattr(
            "nunatak.report.html.ASSETS", tmp_path_factory.mktemp("empty")
        )
        assert principal(["report"]) == 125
        assert "report-app/" in capsys.readouterr().err


class TestDoctorCheck:
    def test_the_light_doctor_sees_the_compiled_app(self, capsys):
        assert principal(["doctor", "--json"]) == 0
        report = json.loads(capsys.readouterr().out)
        check = [c for c in report["checks"] if c["name"] == "report-app"]
        assert check and check[0]["status"] == "ok"

    def test_a_missing_bundle_is_a_named_degradation(
        self, monkeypatch, tmp_path_factory, capsys
    ):
        monkeypatch.setattr(
            "nunatak.report.html.ASSETS", tmp_path_factory.mktemp("empty")
        )
        assert principal(["doctor", "--json"]) == 0
        report = json.loads(capsys.readouterr().out)
        names = [d["name"] for d in report["degradations"]]
        assert "report-unavailable" in names


class TestRunWiring:
    ENTRY = (
        Path(__file__).resolve().parent.parent
        / "corpus"
        / "recordings"
        / "perf"
        / "6.14.11"
        / "linux-x86_64"
        / "workload-c-roofline"
    )

    def test_run_ends_on_the_report_path(self, tmp_path, monkeypatch, capsys):
        (tmp_path / "nunatak.toml").write_text(
            '[tools]\nllvm-symbolizer = "/usr/lib/llvm-19/bin/llvm-symbolizer"\n'
        )
        monkeypatch.chdir(tmp_path)
        assert (
            principal(["run", "--replay", str(self.ENTRY), "--json", "--", "./workload"])
            == 0
        )
        captured = capsys.readouterr()
        summary = json.loads(captured.out)
        assert summary["report"] == str(Path(summary["run"]) / "report.html")
        assert Path(summary["report"]).is_file()
        lines = [line for line in captured.err.splitlines() if line]
        assert lines[-1].split(" ", 1)[-1] == f"Report: {summary['report']}"

    def test_without_the_bundle_the_run_still_succeeds(
        self, tmp_path, monkeypatch, tmp_path_factory, capsys
    ):
        monkeypatch.setattr(
            "nunatak.report.html.ASSETS", tmp_path_factory.mktemp("empty")
        )
        (tmp_path / "nunatak.toml").write_text(
            '[tools]\nllvm-symbolizer = "/usr/lib/llvm-19/bin/llvm-symbolizer"\n'
        )
        monkeypatch.chdir(tmp_path)
        assert (
            principal(["run", "--replay", str(self.ENTRY), "--json", "--", "./workload"])
            == 0
        )
        captured = capsys.readouterr()
        assert json.loads(captured.out)["report"] is None
        assert "degraded [report-unavailable]" in captured.err

class TestNoSourceVariant:
    def test_the_variant_gets_its_own_name_and_no_code_leaves(
        self, tmp_path, monkeypatch, capsys
    ):
        from nunatak.pivot import SourceExtract

        monkeypatch.chdir(tmp_path)
        directory = tmp_path / ".nunatak" / "solver-20260811-120000"
        spot = hotspot(file=SOURCE_FILE)
        run = run_with(balanced(spot, flops=1.6e10, bytes_=8.0e9, seconds=0.1))
        run.source_extracts = [
            SourceExtract(
                hotspot=spot,
                file=SOURCE_FILE,
                text="double proprietary_kernel(void);",
                start_line=12,
                end_line=12,
            )
        ]
        write_run(directory, run)

        assert principal(["report", str(directory), "--json"]) == 0
        full = json.loads(capsys.readouterr().out)["report"]
        assert principal(["report", str(directory), "--no-source", "--json"]) == 0
        stripped = json.loads(capsys.readouterr().out)["report"]

        assert stripped.endswith("report-no-source.html")
        assert "proprietary_kernel" in Path(full).read_text(encoding="utf-8")
        page = Path(stripped).read_text(encoding="utf-8")
        assert "proprietary_kernel" not in page
        assert "withheld by --no-source" in page
        # The full report is untouched by the variant.
        assert "proprietary_kernel" in Path(full).read_text(encoding="utf-8")
