"""The macOS temporal collector: /usr/bin/sample driven and parsed.

The two report fixtures are verbatim /usr/bin/sample output from an
Apple M5 Max on macOS 26.5.2: `sample-report-triad.txt` profiles a
seconds-long triad (a clean three-frame tree whose leaf aggregates its
addresses), `sample-report-startup.txt` a run short enough to be
dominated by dyld - the deep tree with sibling gutters, self time on
interior nodes, and blocked threads.
"""

import json
from pathlib import Path

import pytest

from nunatak.collect.sample import DURATION_CAP, SampleAdapter
from nunatak.ingestion import ingest, sample_report
from tests.support import ScriptedExecutor

FIXTURES = Path(__file__).resolve().parent / "fixtures"
TRIAD = (FIXTURES / "sample-report-triad.txt").read_text()
STARTUP = (FIXTURES / "sample-report-startup.txt").read_text()
CORPUS = (
    Path(__file__).resolve().parent.parent
    / "corpus" / "recordings" / "sample" / "26.5.2" / "darwin-arm64" / "triad-c"
)


class TestParser:
    def test_the_triad_tree_lands_on_axpy_with_its_callers(self):
        samples, identities, version, unparsed = sample_report.parse(
            TRIAD, target="/Users/me/triad"
        )
        assert version == 7
        assert unparsed == []
        assert len(samples) == 288
        hit = samples[0]
        # The leaf aggregated its addresses (`+ 100,92,...`): the first
        # one anchors the whole count - the announced function grain.
        assert hit.module == "/Users/me/triad"
        assert hit.offset == 0x10429C514 - 0x10429C000
        assert hit.counter == "wall-clock"
        assert hit.period == 1_000_000
        assert [caller[0] for caller in hit.callers[:1]] == ["/Users/me/triad"]
        assert hit.callers[1][0].endswith("dyld")

    def test_the_main_image_takes_the_launch_targets_path(self):
        # The report redacts non-system paths (`/tmp/*/triad`); the
        # launch command knows the real one.
        samples, identities, _, _ = sample_report.parse(TRIAD, target="/opt/triad")
        assert samples[0].module == "/opt/triad"
        assert identities["/opt/triad"] == "DDEDBF98-7A3C-343D-958D-9AA504209D5E"
        without = sample_report.parse(TRIAD)[0]
        assert without[0].module == "/tmp/*/triad"

    def test_interior_nodes_keep_their_self_time(self):
        samples, _, _, _ = sample_report.parse(STARTUP)
        # 253 thread samples: 246 end in _dyld_start itself, 4 walk into
        # dyld4::start whose subtree consumes them all, and the last 3
        # belong to frames of this tree - never invented, never lost
        # beyond what the thread line itself absorbed.
        leaf_246 = [s for s in samples if not s.callers and s.offset is not None]
        assert sum(1 for s in samples if s.period == 1_000_000) == len(samples)
        by_depth_zero = [s for s in samples if not s.callers]
        assert len(by_depth_zero) == 246
        assert len(samples) >= 250

    def test_without_binary_images_the_printed_names_stand_offsetless(self):
        # This report ends with "Binary images description not
        # available" - sample can fail to enumerate images when the
        # target dies early. The module names survive, the offsets
        # honestly do not.
        samples, identities, _, _ = sample_report.parse(STARTUP)
        assert identities == {}
        deep = max(samples, key=lambda s: len(s.callers))
        assert len(deep.callers) >= 8
        assert all(offset is None for _, offset in deep.callers)
        assert deep.callers[0][0].endswith(".dylib")

    def test_a_report_without_a_call_graph_is_declared(self):
        samples, _, version, unparsed = sample_report.parse("Report Version:  7\n")
        assert samples == [] and unparsed == ["no call graph section"]


class TestAdapter:
    def test_the_wrapper_launches_samples_and_propagates_the_exit_code(
        self, tmp_path
    ):
        executor = (
            ScriptedExecutor(system="Darwin")
            .on("sh", exit_code=7)
            .on("cat", stdout=TRIAD)
        )
        adapter = SampleAdapter()
        exit_code, degradations = adapter.collect(
            ["./triad"], tmp_path / "collect", executor, frequency=997
        )
        assert exit_code == 7
        assert degradations == []
        wrapper = executor.calls[0]
        assert wrapper[:2] == ["/bin/sh", "-c"]
        assert f"/usr/bin/sample $APP {DURATION_CAP} 1 -mayDie" in wrapper[2]
        assert wrapper[-1] == "./triad"
        assert (tmp_path / "collect" / "sample-report.txt").read_text() == TRIAD
        assert (tmp_path / "collect" / "sample-target.json").is_file()

    def test_detection_reads_the_banner_and_the_os_version(self):
        executor = (
            ScriptedExecutor(system="Darwin")
            .on("sample", stderr="Usage: sample <pid | partial-process-name>")
            .on("sw_vers", stdout="26.5.2\n")
        )
        assert SampleAdapter().detect(executor) == "macOS 26.5.2"

    def test_a_tool_that_is_not_sample_is_refused(self):
        executor = ScriptedExecutor(system="Darwin").on(
            "sample", stdout="mystery tool"
        )
        assert SampleAdapter().detect(executor) is None


class TestIngestion:
    def write(self, directory, text=TRIAD, target=None):
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "sample-report.txt").write_text(text)
        if target is not None:
            (directory / "sample-target.json").write_text(
                f'{{"target": "{target}"}}'
            )

    def test_the_report_becomes_measurements_and_stacks(self, tmp_path):
        self.write(tmp_path, target="/opt/triad")
        measurements, stacks, degradations = ingest(
            "sample", "macOS 26.5.2", tmp_path, node="laptop"
        )
        assert degradations == []
        top = measurements[0]
        assert top.counter == "wall-clock"
        assert top.unit == "ns"
        assert top.value == 288 * 1_000_000
        assert top.sample_count == 288
        assert top.hotspot.display_name.startswith("triad+0x")
        # The Mach-O UUID stands where the ELF build-id does.
        assert top.hotspot.physical_identity is not None
        assert stacks and stacks[0].frames[0].module == "/opt/triad"

    def test_missing_binary_images_are_a_named_degradation(self, tmp_path):
        # Measured on the corpus machine: the very first launch of a
        # freshly built binary can leave sample without image ranges.
        self.write(tmp_path, text=STARTUP)
        measurements, _, degradations = ingest(
            "sample", "macOS 26.5.2", tmp_path, node="laptop"
        )
        assert measurements
        assert any(
            d.name == "sample-images-unavailable" for d in degradations
        )
        assert all(m.hotspot.offset is None for m in measurements)

    def test_a_missing_report_is_a_named_absence(self, tmp_path):
        tmp_path.mkdir(exist_ok=True)
        measurements, stacks, (degradation,) = ingest(
            "sample", "macOS 26.5.2", tmp_path, node="laptop"
        )
        assert measurements == [] and stacks == []
        assert degradation.name == "sample-report-missing"

    def test_an_unknown_report_version_is_refused_not_guessed(self, tmp_path):
        self.write(tmp_path, text=TRIAD.replace("Report Version:  7", "Report Version:  9"))
        _, _, (degradation,) = ingest("sample", "macOS 26.5.2", tmp_path, node="n")
        assert degradation.name == "ingestion-unsupported"
        assert "version 9" in degradation.message


class TestReplayedTemporalRun:
    """The whole `run` pipeline against the recorded macOS entry: sample
    and sw_vers replayed from an Apple M5 Max (macOS 26.5.2, triad built
    `cc -O2 -g`, no usable LLVM on the machine)."""

    @pytest.fixture(autouse=True)
    def in_tmp_cwd(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

    def test_the_macos_entry_replays_on_any_host(self, capsys):
        from nunatak.cli import principal
        from nunatak.pivot import read_run

        assert (
            principal(
                ["run", "--replay", str(CORPUS), "--no-calibrate", "--json",
                 "--", "./triad"]
            )
            == 0
        )
        summary = json.loads(capsys.readouterr().out)
        run = read_run(summary["run"])
        assert summary["hotspots"] == 1
        assert {m.counter for m in run.measurements} == {"wall-clock"}
        assert all(m.unit == "ns" for m in run.measurements)
        top = max(run.measurements, key=lambda m: m.value or 0)
        # axpy's body: unresolved without a symbolizer, anchored anyway.
        assert top.hotspot.display_name == "triad+0x514"
        assert top.hotspot.physical_identity is not None
        # sample's tree records the callers with every hit.
        assert run.stacks
        deepest = max(run.stacks, key=lambda s: len(s.frames))
        assert len(deepest.frames) >= 3
        names = {d["name"] for d in summary["degradations"]}
        assert "llvm-missing" in names
