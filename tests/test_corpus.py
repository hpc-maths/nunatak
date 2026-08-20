"""Record once, replay forever: the executor-level corpus mechanism."""

import json
import sys

import pytest

from nunatak.cli import principal
from nunatak.corpus import RecordingExecutor, ReplayExecutor, read_meta, write_meta
from support import ScriptedExecutor


def test_record_then_replay_restores_each_invocation(tmp_path):
    entry = tmp_path / "entry"
    scripted = ScriptedExecutor().on("perf", stdout="perf version 6.12\n")
    recording = RecordingExecutor(scripted, entry)
    recording.run(["/usr/bin/perf", "--version"])
    recording.run(["./solver"], capture=False)
    write_meta(entry, ["./solver"], [{"tool": "perf", "version": "6.12"}])

    replay = ReplayExecutor(entry)
    # Absolute paths legitimately differ between machines: match by name.
    version = replay.run(["/opt/other/perf", "--version"])
    assert version.stdout == "perf version 6.12\n"
    solver = replay.run(["./solver"], capture=False)
    assert solver.exit_code == 0 and solver.stdout is None


def test_a_program_the_entry_never_recorded_is_reported_absent(tmp_path):
    entry = tmp_path / "entry"
    RecordingExecutor(ScriptedExecutor(), entry)
    write_meta(entry, ["./solver"], [])
    invocation = ReplayExecutor(entry).run(["nsys", "--version"])
    assert invocation.exit_code == 127
    assert "not recorded" in invocation.stderr


def test_the_replayed_platform_is_the_recorded_one(tmp_path):
    entry = tmp_path / "entry"
    RecordingExecutor(ScriptedExecutor(), entry)
    write_meta(entry, ["./solver"], [])
    meta = read_meta(entry)
    assert ReplayExecutor(entry).system == meta["platform"]["system"]


def test_a_blocked_recording_replays_blocked(tmp_path):
    # An entry captured where sampling was denied must replay down the
    # same degraded path: deciding "allowed" at replay time would ask
    # for collector invocations the entry never recorded.
    entry = tmp_path / "entry"
    recorder = RecordingExecutor(
        ScriptedExecutor(blocked="kernel.perf_event_paranoid=4"), entry
    )
    write_meta(entry, ["./solver"], [], sampling_blocked=recorder.sampling_blocked())
    assert ReplayExecutor(entry).sampling_blocked() == "kernel.perf_event_paranoid=4"


def test_an_entry_written_before_the_verdict_reads_back_unblocked(tmp_path):
    # The real corpus was captured with sampling working; its meta files
    # predate the verdict and must keep replaying as unblocked.
    entry = tmp_path / "entry"
    RecordingExecutor(ScriptedExecutor(), entry)
    write_meta(entry, ["./solver"], [])
    meta = read_meta(entry)
    del meta["sampling_blocked"]
    (entry / "meta.json").write_text(json.dumps(meta))
    assert ReplayExecutor(entry).sampling_blocked() is None


def test_recording_refuses_to_mix_with_an_existing_entry(tmp_path):
    entry = tmp_path / "entry"
    RecordingExecutor(ScriptedExecutor(), entry).run(["perf", "--version"])
    with pytest.raises(ValueError, match="already contains"):
        RecordingExecutor(ScriptedExecutor(), entry)


class TestEndToEnd:
    """A recorded `nunatak run` replays identically, without the tools."""

    @pytest.fixture(autouse=True)
    def in_tmp_cwd(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        return tmp_path

    def test_a_recorded_run_replays_its_exit_code(self, tmp_path, capsys):
        entry = tmp_path / "entry"
        command = [sys.executable, "-c", "raise SystemExit(5)"]
        assert principal(["run", "--record", str(entry), "--json", "--", *command]) == 5
        recorded = json.loads(capsys.readouterr().out)

        assert principal(["run", "--replay", str(entry), "--json", "--", *command]) == 5
        replayed = json.loads(capsys.readouterr().out)
        assert replayed["exit_code"] == recorded["exit_code"]
        assert read_meta(entry)["command"] == command


def test_the_recorded_processor_replays_never_the_hosts(tmp_path):
    # The call-stack ladder keys its lbr rung on the vendor: an entry
    # recorded on AMD must not decide lbr when replayed on an Intel host.
    entry = tmp_path / "entry"
    RecordingExecutor(ScriptedExecutor(), entry)
    write_meta(
        entry, ["./solver"], [], cpu_model="AMD EPYC 7702 64-Core Processor"
    )
    assert (
        ReplayExecutor(entry).cpu_model() == "AMD EPYC 7702 64-Core Processor"
    )


def test_an_entry_written_before_the_model_reads_back_unknown(tmp_path):
    entry = tmp_path / "entry"
    RecordingExecutor(ScriptedExecutor(), entry)
    write_meta(entry, ["./solver"], [])
    meta = read_meta(entry)
    del meta["cpu_model"]
    (entry / "meta.json").write_text(json.dumps(meta))
    assert ReplayExecutor(entry).cpu_model() is None
