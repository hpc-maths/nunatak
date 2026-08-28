"""The Python story: interpreter time folded onto Python functions.

The block fixture is verbatim from the python-hot corpus capture (perf
6.14.11, CPython 3.13, the adapter's script fields): an interpreter
leaf, trampoline frames interleaved with `_PyEval_EvalFrameDefault`.
"""

from pathlib import Path

from nunatak.ingestion import (
    Sample,
    measurements_from_samples,
    stacks_from_samples,
)
from nunatak.ingestion.perf_script import parse_samples
from nunatak.pivot import ResolutionLevel

VERBATIM_BLOCK = """\
python3 3696126/3696126 29643715.999910:    1003009                                            task-clock:u:
\t          53f44e PyLong_FromLong+0xe (/usr/bin/python3.13+0x13f44e)
\t          566604 _PyEval_EvalFrameDefault+0x1cc4 (/usr/bin/python3.13+0x166604)
\t    70d5126a7eb6 py::axpy:/tmp/nunatak-capture-python/hot.py+0x6 (/tmp/perf-3696126.map+0x70d5126a7eb6)
\t          56774f _PyEval_EvalFrameDefault+0x2e0f (/usr/bin/python3.13+0x16774f)
\t    70d5126a7e96 py::main:/tmp/nunatak-capture-python/hot.py+0x6 (/tmp/perf-3696126.map+0x70d5126a7e96)
\t          64b1c5 _start+0x25 (/usr/bin/python3.13+0x24b1c5)
"""


def sample_of(module, python_frames=(), callers=()):
    return Sample(
        pid=1, tid=1, time_s=0.0, period=1003009, counter="task-clock",
        module=module, offset=0x10, callers=tuple(callers),
        python_frames=tuple(python_frames),
    )


class TestParser:
    def test_map_frames_keep_their_python_names(self):
        samples, unparsed = parse_samples(VERBATIM_BLOCK)
        assert unparsed == []
        sample = samples[0]
        assert sample.module == "/usr/bin/python3.13"
        assert sample.python_frames == (
            (2, "axpy", "/tmp/nunatak-capture-python/hot.py"),
            (4, "main", "/tmp/nunatak-capture-python/hot.py"),
        )

    def test_a_qualified_name_survives_its_dots(self):
        line = (
            "python3 1/1 1.0: 7 task-clock:u:  70d5126a7010 "
            "py::_ModuleLock.acquire:<frozen importlib._bootstrap>+0x6 "
            "(/tmp/perf-1.map+0x70d5126a7010)"
        )
        samples, _ = parse_samples(line + "\n")
        assert samples[0].python_frames == (
            (0, "_ModuleLock.acquire", "<frozen importlib._bootstrap>"),
        )

    def test_a_py_looking_symbol_outside_a_map_is_native(self):
        line = (
            "solver 1/1 1.0: 7 task-clock:u:  10 "
            "py::fake:/a.py+0x6 (/app/solver+0x10)"
        )
        samples, _ = parse_samples(line + "\n")
        assert samples[0].python_frames == ()


class TestFolding:
    def test_an_interpreter_leaf_folds_onto_the_innermost_python_frame(self):
        sample = sample_of(
            "/usr/bin/python3.13",
            python_frames=[(2, "axpy", "/src/hot.py")],
        )
        measurement = measurements_from_samples([sample], {}, node="n0")[0]
        hotspot = measurement.hotspot
        assert hotspot.display_name == "axpy"
        assert hotspot.logical_identity.source_file == "/src/hot.py"
        assert hotspot.resolution_level is ResolutionLevel.FUNCTION
        assert hotspot.physical_identity is None

    def test_a_trampoline_hit_is_that_function(self):
        sample = sample_of(
            "/tmp/perf-9.map", python_frames=[(0, "wave", "/src/hot.py")]
        )
        measurement = measurements_from_samples([sample], {}, node="n0")[0]
        assert measurement.hotspot.display_name == "wave"

    def test_an_extension_leaf_stays_native(self):
        # numpy's kernels are Hotspots of their own: the Python caller
        # stays visible in the stack, never in the identity.
        sample = sample_of(
            "/usr/lib/python3/dist-packages/numpy/_core/_multiarray_umath.so",
            python_frames=[(3, "main", "/src/hot.py")],
        )
        measurement = measurements_from_samples([sample], {}, node="n0")[0]
        assert measurement.hotspot.resolution_level is ResolutionLevel.UNRESOLVED
        assert measurement.hotspot.logical_identity.module.endswith(".so")

    def test_two_interpreter_leaves_of_one_function_fuse(self):
        samples = [
            sample_of("/usr/bin/python3.13", python_frames=[(1, "axpy", "/src/hot.py")]),
            sample_of("/usr/bin/python3.13", python_frames=[(2, "axpy", "/src/hot.py")]),
        ]
        measurements = measurements_from_samples(samples, {}, node="n0")
        assert len(measurements) == 1
        assert measurements[0].sample_count == 2

    def test_libpython_is_the_interpreter_too(self):
        sample = sample_of(
            "libpython3.13.so.1.0", python_frames=[(1, "f", "/src/a.py")]
        )
        measurement = measurements_from_samples([sample], {}, node="n0")[0]
        assert measurement.hotspot.display_name == "f"


class TestStackNames:
    def test_map_frames_carry_their_names_into_the_stacks(self):
        samples, _ = parse_samples(VERBATIM_BLOCK)
        stacks = stacks_from_samples(samples, node="n0")
        functions = [frame.function for frame in stacks[0].frames]
        assert functions[2] == "axpy"
        assert functions[4] == "main"
        assert functions[0] is None


ENTRY = (
    Path(__file__).resolve().parent.parent
    / "corpus"
    / "recordings"
    / "perf"
    / "6.14.11"
    / "linux-x86_64"
    / "python-hot"
)


class TestReplayedPythonStory:
    """The same corpus entry as the collection brick, replayed through
    the folding: the pure-Python axpy emerges above the floor."""

    def test_axpy_emerges_with_its_python_identity(self, tmp_path, monkeypatch, capsys):
        import io
        import json
        from contextlib import redirect_stdout

        from nunatak import analysis
        from nunatak.cli import principal
        from nunatak.pivot import read_run

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
        run = read_run(summary["run"])
        diagnostics = analysis.diagnose(run)
        names = {d.hotspot.display_name: d for d in diagnostics}
        assert "axpy" in names
        axpy = names["axpy"]
        assert axpy.hotspot.resolution_level is ResolutionLevel.FUNCTION
        assert axpy.hotspot.logical_identity.source_file.endswith("hot.py")
        assert axpy.share.value > 0.5
