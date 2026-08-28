"""The CPython trampoline path: detection, environment, map retrieval.

Detection keys on argv - the only witness a replay can reproduce - and
the interpreter answers for its own version at the execution boundary.
"""

from pathlib import Path

from nunatak.cli.doctor import _python_target
from nunatak.cli.run import collection_command
from nunatak.collect import interpreter
from nunatak.collect.perf import _retrieve_maps
from nunatak.config import Config
from nunatak.launch import split
from nunatak.rank import application_environment
from tests.support import ScriptedExecutor

# Verbatim frames from the capture on the EPYC (perf 6.14.11, CPython
# 3.13, the adapter's own script fields): the trampoline names its
# Python function and file, and `dsoff` appends the offset to the map
# module inside the parentheses.
SCRIPT_WITH_MAP = """\
python3 3694811 29642769.807088:        594 cycles:Pu:
	    74032b21f106 py::_call_with_frames_removed:<frozen importlib._bootstrap>+0x6 (/tmp/perf-3694811.map+0x74032b21f106)
	          56774f _PyEval_EvalFrameDefault+0x2e0f (/usr/bin/python3.13)
	    7a4b57155e96 py::main:/tmp/explore/hot.py+0x6 (/tmp/perf-3694811.map+0x7a4b57155e96)

python3 3694812 29642769.807128:        681 cycles:Pu:
	    7a4b58000010 py::wave:/tmp/explore/hot.py+0x10 (/tmp/perf-3694812.map)
"""

MAP_CONTENT = "7a4b57155000 b py::_find_and_load:<frozen importlib._bootstrap>\n"


class TestDetect:
    def test_a_named_interpreter_answers_for_its_version(self):
        executor = ScriptedExecutor().on("python3", stdout="Python 3.13.3\n")
        target = interpreter.detect(executor, ["python3", "hot.py"])
        assert target == interpreter.PythonTarget(
            interpreter="python3", version=(3, 13)
        )
        assert target.trampolines is True
        assert target.release == "3.13"

    def test_the_interpreter_is_seen_through_an_mpi_launcher(self):
        # `split` wants a resolvable token behind a launcher: python3
        # exists wherever this suite runs; the version stays canned.
        executor = ScriptedExecutor().on("python3", stderr="Python 3.11.9\n")
        target = interpreter.detect(
            executor, ["mpirun", "-n", "4", "python3", "solver.py"]
        )
        assert target is not None
        assert target.trampolines is False

    def test_a_native_target_probes_nothing(self):
        executor = ScriptedExecutor()
        assert interpreter.detect(executor, ["./solver"]) is None
        assert executor.calls == []

    def test_a_failing_banner_is_no_python(self):
        executor = ScriptedExecutor().on("python", exit_code=127)
        assert interpreter.detect(executor, ["python", "x.py"]) is None


class TestEnvironment:
    def test_the_flag_rides_a_full_environment(self):
        composed = interpreter.environment(base={"PATH": "/usr/bin"})
        assert composed == {"PATH": "/usr/bin", "PYTHONPERFSUPPORT": "1"}

    def test_the_base_is_not_modified(self):
        base = {"PATH": "/usr/bin"}
        interpreter.environment(base=base)
        assert base == {"PATH": "/usr/bin"}


class TestMapRetrieval:
    def test_every_referenced_map_lands_next_to_the_recording(self, tmp_path):
        executor = ScriptedExecutor()
        executor.on("cat", stdout=MAP_CONTENT)
        executor.on("cat", stdout=MAP_CONTENT.replace("7a4b", "7a4c"))
        _retrieve_maps(executor, SCRIPT_WITH_MAP, tmp_path)
        assert (tmp_path / "perf-3694811.map").read_text() == MAP_CONTENT
        assert (tmp_path / "perf-3694812.map").is_file()
        assert executor.calls[0] == ["/bin/cat", "/tmp/perf-3694811.map"]

    def test_a_vanished_map_writes_nothing(self, tmp_path):
        executor = ScriptedExecutor().on("cat", exit_code=1).on("cat", exit_code=1)
        _retrieve_maps(executor, SCRIPT_WITH_MAP, tmp_path)
        assert list(tmp_path.iterdir()) == []

    def test_a_native_script_reads_nothing(self, tmp_path):
        executor = ScriptedExecutor()
        _retrieve_maps(executor, "main+0x4 (/app/solver)\n", tmp_path)
        assert executor.calls == []


class TestShim:
    def test_the_flag_reaches_the_application_environment(self, tmp_path):
        composed = application_environment(
            {"PATH": "/usr/bin"}, None, tmp_path, python_perf=True
        )
        assert composed["PYTHONPERFSUPPORT"] == "1"

    def test_the_flag_and_the_preload_compose(self, tmp_path):
        composed = application_environment(
            {"PATH": "/usr/bin"}, "/lib/libmpiP.so", tmp_path, python_perf=True
        )
        assert composed["PYTHONPERFSUPPORT"] == "1"
        assert composed["LD_PRELOAD"] == "/lib/libmpiP.so"

    def test_without_either_the_environment_is_inherited(self, tmp_path):
        assert application_environment({"A": "1"}, None, tmp_path) is None

    def test_the_shim_receives_the_flag(self):
        command = collection_command(
            split(["mpirun", "-n", "2", "python3", "x.py"]),
            Path("/runs/r/collect"),
            Config(),
            python_perf=True,
        )
        assert "--python-perf" in command


class TestDoctorRow:
    def test_a_trampoline_capable_python_reads_ok(self):
        executor = ScriptedExecutor().on("python3", stdout="Python 3.12.4\n")
        check = _python_target(executor, ["python3", "x.py"])
        assert check.status == "ok"
        assert "PYTHONPERFSUPPORT" in check.detail

    def test_an_old_python_loses_the_python_story_by_name(self):
        executor = ScriptedExecutor().on("python3", stdout="Python 3.10.12\n")
        check = _python_target(executor, ["python3", "x.py"])
        assert check.status == "warning"
        assert check.degradation.name == "python-hotspots-unavailable"
        assert "3.12" in check.degradation.remedy

    def test_a_native_command_has_no_row(self):
        assert _python_target(ScriptedExecutor(), ["./solver"]) is None


class TestMapModule:
    def test_a_perf_map_is_never_sent_to_a_symbolizer(self):
        from nunatak.attribution import _symbolizable

        assert _symbolizable("/tmp/perf-3695742.map") is False
        assert _symbolizable("/app/solver") is True


ENTRY = (
    Path(__file__).resolve().parent.parent
    / "corpus"
    / "recordings"
    / "perf"
    / "6.14.11"
    / "linux-x86_64"
    / "python-hot"
)


class TestReplayedPythonRun:
    """The captured reality: a pure-Python hot loop under CPython 3.13,
    trampolines on. The decision, the collection environment and the
    map retrieval all replay from the recorded invocations."""

    def test_the_map_rides_home_and_nothing_degrades_wrongly(
        self, tmp_path, monkeypatch, capsys
    ):
        import io
        import json
        from contextlib import redirect_stdout

        from nunatak.cli import principal

        monkeypatch.chdir(tmp_path)
        out = io.StringIO()
        with redirect_stdout(out):
            assert (
                principal(
                    ["run", "--replay", str(ENTRY), "--json", "--", "python3", "hot.py"]
                )
                == 0
            )
        capsys.readouterr()
        summary = json.loads(out.getvalue())
        names = {d["name"] for d in summary["degradations"]}
        # 3.13 has trampolines, and a perf map is a pseudo module, not a
        # symbolization failure.
        assert "python-hotspots-unavailable" not in names
        assert "symbolization-failed" not in names
        maps = list((Path(summary["run"]) / "collect").glob("perf-*.map"))
        assert len(maps) == 1
        assert "py::" in maps[0].read_text()
