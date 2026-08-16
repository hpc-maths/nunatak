"""Ingestion of perf outputs, replayed from the recorded corpus.

The corpus entry was captured by `nunatak run --record` on real Linux
(Debian trixie, perf 6.12.101, aarch64): these tests exercise the parser
against genuine tool output, never against our idea of it.
"""

import json
from pathlib import Path

import pytest

from nunatak.cli import principal
from nunatak.ingestion import ingest, measurements_from_samples
from nunatak.ingestion.perf_script import parse_buildid_list, parse_samples, supports
from nunatak.pivot import Quality, ResolutionLevel, read_run

RECORDINGS = Path(__file__).resolve().parent.parent / "corpus" / "recordings"
CORPUS = RECORDINGS / "perf" / "6.12.101" / "linux-aarch64" / "workload-c"
X86_CORPUS = RECORDINGS / "perf" / "6.14.11" / "linux-x86_64" / "workload-c"
STACKS_CORPUS = RECORDINGS / "perf" / "6.14.11" / "linux-x86_64" / "workload-c-stacks"
WORKLOAD_BUILDID = "c176e72d0b29a13e48d8b5e6a98f2ef6894d7e69"


def recorded_stdout(subcommand: str, entry: Path = CORPUS) -> str:
    for record in sorted((entry / "invocations").glob("*.json")):
        argv = json.loads(record.read_text())["argv"]
        if argv[:2] == ["perf", subcommand]:
            return record.with_suffix(".stdout").read_text()
    raise AssertionError(f"no perf {subcommand} in the corpus entry")


class TestVersionGate:
    def test_versions_with_the_dsoff_field_are_supported(self):
        assert supports("6.12.101")
        assert supports("6.4")

    def test_older_or_unreadable_versions_are_declared_not_guessed(self):
        assert not supports("6.3.9")
        assert not supports("5.15.167")
        assert not supports("who-knows")


class TestParser:
    def test_every_recorded_sample_line_parses(self):
        samples, unparsed = parse_samples(recorded_stdout("script"))
        assert unparsed == []
        assert len(samples) == 692

    def test_offsets_are_module_relative_and_ip_is_discarded(self):
        samples, _ = parse_samples(recorded_stdout("script"))
        workload = [s for s in samples if s.module == "/tmp/workload"]
        assert len(workload) == 691
        assert {s.offset for s in workload} <= set(range(0x6D0, 0x700))
        # The one kernel sample: module known, honest offset inside kcore.
        (kernel,) = [s for s in samples if s.module == "/proc/kcore"]
        assert kernel.offset == 0x800081359684

    def test_the_sampled_counter_is_task_clock_in_a_vm(self):
        samples, _ = parse_samples(recorded_stdout("script"))
        assert {s.counter for s in samples} == {"task-clock"}

    def test_buildid_list_maps_modules_to_their_identity(self):
        module_ids = parse_buildid_list(recorded_stdout("buildid-list"))
        assert module_ids["/tmp/workload"] == WORKLOAD_BUILDID
        assert "[vdso]" in module_ids


class TestAggregation:
    def test_samples_aggregate_into_measured_measurements(self):
        samples, _ = parse_samples(recorded_stdout("script"))
        module_ids = parse_buildid_list(recorded_stdout("buildid-list"))
        measurements = measurements_from_samples(samples, module_ids, node="n0")

        assert len(measurements) == 8  # 7 workload offsets + 1 kernel
        assert all(m.quality is Quality.MEASURED for m in measurements)
        assert all(m.unit == "ns" for m in measurements)
        # Totals are preserved: nothing invented, nothing dropped.
        assert sum(m.value for m in measurements) == sum(s.period for s in samples)
        assert sum(m.sample_count for m in measurements) == len(samples)

    def test_the_hottest_hotspot_is_unresolved_with_physical_identity(self):
        samples, _ = parse_samples(recorded_stdout("script"))
        module_ids = parse_buildid_list(recorded_stdout("buildid-list"))
        top = measurements_from_samples(samples, module_ids, node="n0")[0]

        assert top.hotspot.resolution_level is ResolutionLevel.UNRESOLVED
        assert top.hotspot.display_name == "workload+0x6d0"
        assert top.hotspot.physical_identity.module_id == WORKLOAD_BUILDID
        assert top.sample_count == 405
        assert top.locus.thread == 4013

    def test_an_unsupported_version_is_a_named_degradation(self, tmp_path):
        measurements, degradations = ingest("perf", "6.3", tmp_path, node="n0")
        assert measurements == []
        assert degradations[0].name == "ingestion-unsupported"


class TestReplayedPipeline:
    """The whole `run` pipeline against the corpus, without perf installed."""

    @pytest.fixture(autouse=True)
    def in_tmp_cwd(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

    def test_the_recorded_run_replays_into_a_measured_pivot(self, capsys):
        assert principal(["run", "--replay", str(CORPUS), "--json", "--", "/tmp/workload"]) == 0
        summary = json.loads(capsys.readouterr().out)
        assert summary["measurements"] == 8
        assert summary["hotspots"] == 8

        run = read_run(summary["run"])
        assert run.passes[0].collectors[0].tool == "perf"
        assert run.passes[0].collectors[0].version == "6.12.101"
        samples, _ = parse_samples(recorded_stdout("script"))
        assert sum(m.value for m in run.measurements) == sum(s.period for s in samples)

    def test_the_x86_entry_carries_real_pmu_cycles(self, capsys):
        # Captured on bare metal (AMD EPYC, paranoid lowered to 2): the
        # sampled raw counter is hardware cycles, not a software clock.
        samples, unparsed = parse_samples(recorded_stdout("script", X86_CORPUS))
        assert unparsed == []
        assert {s.counter for s in samples} == {"cycles"}

        assert principal(["run", "--replay", str(X86_CORPUS), "--json", "--", "./workload"]) == 0
        summary = json.loads(capsys.readouterr().out)
        run = read_run(summary["run"])
        assert run.passes[0].collectors[0].version == "6.14.11"
        assert all(m.unit == "cycles" for m in run.measurements)
        assert sum(m.value for m in run.measurements) == sum(s.period for s in samples)


class TestCallchainParser:
    """The verbatim --call-graph fp recording: bare headers, indented
    frames innermost first, one blank line per sample."""

    def test_every_block_parses_into_one_sample(self):
        from tests.support import PERF_SCRIPT_CALLCHAIN

        samples, unparsed = parse_samples(PERF_SCRIPT_CALLCHAIN)
        assert unparsed == []
        assert len(samples) == 5

    def test_the_hit_is_the_innermost_frame_and_callers_follow_outward(self):
        from tests.support import PERF_SCRIPT_CALLCHAIN

        samples, _ = parse_samples(PERF_SCRIPT_CALLCHAIN)
        first = samples[0]
        assert first.module.endswith("/workload-fp")
        assert first.offset == 0x11B8
        assert [module.rsplit("/", 1)[-1] for module, _ in first.callers] == [
            "libc.so.6",
            "libc.so.6",
            "workload-fp",
        ]
        assert first.callers[-1][1] == 0x1225

    def test_flat_recordings_still_carry_no_callers(self):
        samples, _ = parse_samples(recorded_stdout("script"))
        assert all(s.callers == () for s in samples)

    def test_a_header_without_frames_is_unparsed_not_swallowed(self):
        headerless = (
            "workload-fp 1/1 1.000000:    1003009 task-clock:u: \n"
            "\n"
        )
        samples, unparsed = parse_samples(headerless)
        assert samples == []
        assert len(unparsed) == 1


class TestReplayedStacks:
    """The workload-c-stacks entry: recorded by the full new chain on the
    EPYC - prologues probed, fp settled, `--call-graph fp` on the record,
    every sample carrying its stack."""

    @pytest.fixture(autouse=True)
    def in_tmp_cwd(self, tmp_path, monkeypatch):
        from tests.support import WORKLOAD_C

        (tmp_path / "nunatak.toml").write_text(
            '[tools]\nllvm-symbolizer = "/usr/lib/llvm-19/bin/llvm-symbolizer"\n'
        )
        (tmp_path / "workload.c").write_text(WORKLOAD_C)
        monkeypatch.chdir(tmp_path)

    def test_every_stacked_sample_parses_with_its_callers(self):
        samples, unparsed = parse_samples(recorded_stdout("script", STACKS_CORPUS))
        assert unparsed == []
        assert samples
        stacked = [s for s in samples if s.callers]
        assert len(stacked) == len(samples)
        # fp walks from main always reach _start: the outermost caller
        # lives in the workload itself.
        assert all(s.callers[-1][0].endswith("/workload") for s in stacked)

    def test_the_entry_replays_into_a_measured_pivot_without_noise(self, capsys):
        assert (
            principal(
                ["run", "--replay", str(STACKS_CORPUS), "--json",
                 "--no-calibrate", "--", "./workload"]
            )
            == 0
        )
        summary = json.loads(capsys.readouterr().out)
        names = {d["name"] for d in summary["degradations"]}
        assert "perf-script-unparsed" not in names
        assert "call-stacks-unavailable" not in names
        assert summary["measurements"] > 0
        run = read_run(summary["run"])
        assert run.passes[0].collectors[0].version == "6.14.11"
