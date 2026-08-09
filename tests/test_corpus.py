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
