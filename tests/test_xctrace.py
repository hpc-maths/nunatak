"""The macOS nominal collector: xctrace driven, its export parsed.

The fixtures are verbatim from an Apple M5 Max on macOS 26.5.2 with
Xcode's xctrace 16.0: the complete time-profile export of a
seconds-long triad (reference-compressed rows, frames Instruments
could not identify, the closing sentinel row) and the head of the table
of contents of a run whose target exited 7, kept short on purpose: an
export can come back cut short, and the status has to be readable
anyway.
"""

import json
from pathlib import Path

import pytest

from nunatak.collect import cpu_collector
from nunatak.collect.xctrace import XctraceAdapter
from nunatak.config import Config
from nunatak.ingestion import ingest, xctrace_profile
from nunatak.pivot import ResolutionLevel
from tests.support import ScriptedExecutor

FIXTURES = Path(__file__).resolve().parent / "fixtures"
PROFILE = (FIXTURES / "xctrace-time-profile.xml").read_text()
TOC_FAIL = (FIXTURES / "xctrace-toc-fail.xml").read_text()
CORPUS = (
    Path(__file__).resolve().parent.parent
    / "corpus" / "recordings" / "xctrace" / "16.0" / "darwin-arm64" / "triad-c"
)

TRIAD = "/private/tmp/nunatak-capture-darwin/triad"


class TestParser:
    def test_every_row_lands_with_its_weight_and_no_leftovers(self):
        samples, identities, unparsed = xctrace_profile.parse(PROFILE)
        # 410 rows, one of which is the closing sentinel - skipped, not
        # declared: it is the end of the table, not a sample lost.
        assert unparsed == []
        assert len(samples) == 409
        assert all(s.counter == "cpu-clock" and s.period == 1_000_000 for s in samples)
        assert identities[TRIAD].startswith("32C1343E")

    def test_the_leaf_pc_is_untagged_and_instruction_aligned(self):
        samples, _, _ = xctrace_profile.parse(PROFILE)
        axpy = [
            s for s in samples
            if s.module == TRIAD and s.offset is not None
            and 0x4B0 <= s.offset < 0x558
        ]
        # Per-address grain: the distinct offsets sample's aggregated
        # leaves could never give.
        assert len(axpy) > 300 and len({s.offset for s in axpy}) >= 5
        assert all(s.offset % 4 == 0 for s in axpy)

    def test_callers_ride_with_their_binaries(self):
        samples, _, _ = xctrace_profile.parse(PROFILE)
        deep = max(
            (s for s in samples if s.module == TRIAD), key=lambda s: len(s.callers)
        )
        modules = [module for module, _ in deep.callers]
        assert modules[0] == TRIAD  # main, the call site
        assert any(module.endswith("dyld") for module in modules)

    def test_a_frame_without_a_binary_stays_a_pseudo_module(self):
        samples, _, _ = xctrace_profile.parse(PROFILE)
        nameless = [s for s in samples if s.offset is None]
        assert nameless and all(s.module.startswith("0x") for s in nameless)

    def test_an_unreadable_export_is_one_declared_refusal(self):
        samples, identities, unparsed = xctrace_profile.parse("not xml at all")
        assert samples == [] and identities == {}
        assert len(unparsed) == 1 and "unreadable export" in unparsed[0]


class TestAdapter:
    def scripted(self, toc=TOC_FAIL, record_exit=0):
        return (
            ScriptedExecutor(system="Darwin")
            .on("xctrace", exit_code=record_exit)  # record
            .on("xctrace", stdout=PROFILE)  # export --xpath
            .on("xctrace", stdout=toc)  # export --toc
        )

    def test_the_targets_exit_status_comes_from_the_table_of_contents(
        self, tmp_path
    ):
        executor = self.scripted(record_exit=54)
        exit_code, degradations = XctraceAdapter().collect(
            ["./fail"], tmp_path / "collect", executor, frequency=997
        )
        # xctrace itself exited 54; the target's own status is 7, and
        # the recording is not the failure.
        assert exit_code == 7
        assert degradations == []
        record = executor.calls[0]
        assert record[1] == "record"
        assert "--target-stdout" in record and record[-1] == "./fail"
        assert (tmp_path / "collect" / "xctrace-time-profile.xml").read_text() == PROFILE

    def test_without_a_table_of_contents_the_loss_is_declared(self, tmp_path):
        executor = (
            ScriptedExecutor(system="Darwin")
            .on("xctrace", exit_code=54)
            .on("xctrace", stderr="no trace", exit_code=1)
            .on("xctrace", stderr="no trace", exit_code=1)
        )
        exit_code, degradations = XctraceAdapter().collect(
            ["./app"], tmp_path / "c", executor, frequency=997
        )
        # 54 is how xctrace says its target failed, never an application
        # code: it stands because nothing better is known, and it is not
        # passed off as the application's own status.
        assert exit_code == 54
        assert [d.name for d in degradations] == ["exit-status-unavailable"]

    def test_a_successful_recording_answers_for_its_target(self, tmp_path):
        executor = (
            ScriptedExecutor(system="Darwin")
            .on("xctrace", exit_code=0)
            .on("xctrace", stderr="no trace", exit_code=1)
            .on("xctrace", stderr="no trace", exit_code=1)
        )
        exit_code, degradations = XctraceAdapter().collect(
            ["./app"], tmp_path / "c", executor, frequency=997
        )
        assert exit_code == 0
        assert degradations == []

    def test_only_the_launched_process_answers(self, tmp_path):
        # A trace describes every process it saw. An attached one listed
        # first would be read by an unanchored search.
        toc = TOC_FAIL.replace(
            '<process type="launched"',
            '<process type="attached" return-exit-status="9" name="other" '
            'pid="1" termination-reason="exit(9)"/>\n'
            '                <process type="launched"',
        )
        exit_code, _ = XctraceAdapter().collect(
            ["./fail"], tmp_path / "c", self.scripted(toc=toc, record_exit=54),
            frequency=997,
        )
        assert exit_code == 7

    def test_detection_needs_the_real_banner_not_the_shim(self):
        executor = ScriptedExecutor(system="Darwin").on(
            "xctrace", stdout="xctrace version 16.0 (17F113)\n"
        )
        assert XctraceAdapter().detect(executor) == "16.0"
        shim = ScriptedExecutor(system="Darwin").on(
            "xctrace", stderr="requires Xcode", exit_code=1
        )
        assert XctraceAdapter().detect(shim) is None


class TestLadder:
    def test_xctrace_is_the_nominal_when_xcode_answers(self):
        executor = ScriptedExecutor(system="Darwin").on(
            "xctrace", stdout="xctrace version 16.0 (17F113)\n"
        )
        adapter, version = cpu_collector(executor, Config())
        assert adapter.tool == "xctrace" and version == "16.0"

    def test_without_xcode_sample_stands_in(self):
        executor = (
            ScriptedExecutor(system="Darwin")
            .on("xctrace", stderr="requires Xcode", exit_code=1)
            .on("sample", stderr="Usage: sample <pid | partial-process-name>")
            .on("sw_vers", stdout="26.5.2\n")
        )
        adapter, version = cpu_collector(executor, Config())
        assert adapter.tool == "sample" and version == "macOS 26.5.2"


class TestIngestion:
    def test_the_export_becomes_per_address_measurements(self, tmp_path):
        tmp_path.mkdir(exist_ok=True)
        (tmp_path / "xctrace-time-profile.xml").write_text(PROFILE)
        measurements, stacks, degradations = ingest(
            "xctrace", "16.0", tmp_path, node="laptop"
        )
        assert degradations == []
        in_axpy = [
            m for m in measurements
            if m.hotspot.logical_identity.module == TRIAD
            and m.hotspot.offset is not None and 0x4B0 <= m.hotspot.offset < 0x558
        ]
        assert len(in_axpy) >= 5  # one Measurement per sampled address
        assert all(m.unit == "ns" and m.counter == "cpu-clock" for m in in_axpy)
        assert all(m.hotspot.physical_identity is not None for m in in_axpy)
        assert stacks

    def test_a_missing_export_is_a_named_absence(self, tmp_path):
        tmp_path.mkdir(exist_ok=True)
        _, _, (degradation,) = ingest("xctrace", "16.0", tmp_path, node="n")
        assert degradation.name == "xctrace-export-missing"


class TestReplayedNominalRun:
    """The whole `run` pipeline against the recorded macOS entry:
    xctrace and atos replayed from an Apple M5 Max (Xcode 16, triad
    built `cc -O2 -g`, no usable LLVM on the machine)."""

    @pytest.fixture(autouse=True)
    def in_tmp_cwd(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

    def test_the_nominal_macos_entry_replays_on_any_host(self, capsys):
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
        assert summary["exit_code"] == 0
        assert summary["hotspots"] == 4
        assert summary["resolved_hotspots"] == 3
        assert {m.counter for m in run.measurements} == {"cpu-clock"}
        top = max(run.measurements, key=lambda m: m.value or 0)
        assert top.hotspot.display_name == "axpy"
        assert top.hotspot.resolution_level is ResolutionLevel.LINE
        assert run.stacks
        named = {f.function for s in run.stacks for f in s.frames if f.function}
        assert {"axpy", "main"} <= named
