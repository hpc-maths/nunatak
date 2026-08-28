"""py-spy, the temporal fallback: adapter contract and raw parser.

The collapsed line is verbatim from the capture on the EPYC (py-spy
0.4.2, `--subprocesses` over the exit-witnessing wrapper): process
frames locate the stack, they are not code.
"""

from pathlib import Path

from nunatak.collect.pyspy import EXIT_FILE, RAW_OUTPUT, PySpyAdapter, locate
from nunatak.config import Config
from nunatak.ingestion import ingest, measurements_from_samples
from nunatak.ingestion.pyspy_raw import parse_samples, supports
from nunatak.pivot import ResolutionLevel
from tests.support import ScriptedExecutor

VERBATIM = (
    'process 3732039:"";process 3732041:"python3 hot.py";'
    "<module> (hot.py:19);main (hot.py:16);axpy (hot.py:5) 54\n"
    'process 3732039:"";process 3732041:"python3 hot.py";'
    "<module> (hot.py:19);main (hot.py:13);wave (hot.py:9) 5\n"
)


class TestAdapter:
    def test_the_wrapper_witnesses_the_exit_code(self, tmp_path):
        executor = ScriptedExecutor()
        executor.on("py-spy")
        executor.on("cat", stdout=VERBATIM)   # the raw stacks read back
        executor.on("cat", stdout="7\n")      # then the exit witness
        exit_code, degradations = PySpyAdapter().collect(
            ["python3", "fail.py"], tmp_path, executor, 997
        )
        assert exit_code == 7
        assert degradations == []
        record = executor.calls[0]
        assert record[:3] == ["py-spy", "record", "--subprocesses"]
        assert record[record.index("--rate") + 1] == "997"
        separator = record.index("--")
        assert record[separator + 1:separator + 3] == ["sh", "-c"]
        witness = tmp_path / EXIT_FILE
        assert record[separator + 3] == (
            f'"$@" && echo 0 > {witness} || echo $? > {witness}'
        )
        assert ";" not in record[separator + 3]
        assert record[-2:] == ["python3", "fail.py"]

    def test_no_witness_is_a_named_failure(self, tmp_path):
        executor = ScriptedExecutor()
        executor.on("py-spy", exit_code=1, stderr="boom")
        executor.on("cat", exit_code=1)
        executor.on("cat", exit_code=1)
        exit_code, degradations = PySpyAdapter().collect(
            ["python3", "x.py"], tmp_path, executor, 100
        )
        assert exit_code == 1
        assert degradations[0].name == "python-sampling-failed"

    def test_locate_reads_the_banner(self):
        executor = ScriptedExecutor().on("py-spy", stdout="py-spy 0.4.2\n")
        adapter, version = locate(executor, Config())
        assert version == "0.4.2"
        assert adapter.tool == "py-spy"

    def test_an_absent_pyspy_is_none(self):
        assert locate(ScriptedExecutor(), Config()) is None


class TestParser:
    def test_process_frames_locate_never_appear_as_code(self):
        samples, unparsed = parse_samples(VERBATIM, rate=100)
        assert unparsed == []
        assert len(samples) == 59
        first = samples[0]
        assert first.pid == 3732041
        assert first.module == "hot.py"
        assert first.python_frames[0] == (0, "axpy", "hot.py")
        assert first.python_frames[-1] == (2, "<module>", "hot.py")
        assert first.period == 10_000_000

    def test_the_folding_yields_the_same_python_hotspots(self):
        samples, _ = parse_samples(VERBATIM, rate=100)
        measurements = measurements_from_samples(samples, {}, node="n0")
        by_name = {m.hotspot.display_name: m for m in measurements}
        axpy = by_name["axpy"]
        assert axpy.hotspot.resolution_level is ResolutionLevel.FUNCTION
        assert axpy.counter == "cpu-clock"
        assert axpy.unit == "ns"
        assert axpy.sample_count == 54
        assert axpy.value == 54 * 10_000_000

    def test_the_witness_shell_is_scaffolding_not_code(self):
        line = (
            'process 3732464:"sh -c \"$@\" && echo 0 > /runs/exit '
            '|| echo $? > /runs/exit" 4\n'
        )
        samples, unparsed = parse_samples(line, rate=100)
        assert samples == []
        assert unparsed == []

    def test_an_unrecognized_line_is_declared(self):
        samples, unparsed = parse_samples("not a stack at all\n", rate=100)
        assert samples == []
        assert unparsed == ["not a stack at all"]

    def test_the_version_gate(self):
        assert supports("0.4.2") is True
        assert supports("0.5.0") is False


class TestIngest:
    def test_the_dispatch_reads_rate_and_raw(self, tmp_path):
        (tmp_path / RAW_OUTPUT).write_text(VERBATIM)
        (tmp_path / "pyspy.json").write_text('{"rate": 100}\n')
        measurements, stacks, degradations = ingest(
            "py-spy", "0.4.2", tmp_path, node="n0"
        )
        assert degradations == []
        assert {m.hotspot.display_name for m in measurements} == {"axpy", "wave"}
        named = [frame.function for frame in stacks[0].frames]
        assert named == ["axpy", "main", "<module>"]

    def test_a_missing_raw_is_a_named_absence(self, tmp_path):
        _, _, degradations = ingest("py-spy", "0.4.2", tmp_path, node="n0")
        assert degradations[0].name == "python-sampling-missing"

    def test_a_future_version_is_declared(self, tmp_path):
        (tmp_path / RAW_OUTPUT).write_text(VERBATIM)
        _, _, degradations = ingest("py-spy", "0.5.0", tmp_path, node="n0")
        assert degradations[0].name == "ingestion-unsupported"


ENTRY = (
    Path(__file__).resolve().parent.parent
    / "corpus"
    / "recordings"
    / "pyspy"
    / "0.4.2"
    / "linux-x86_64"
    / "python310-hot"
)


class TestReplayedFallback:
    """The captured reality: the same pure-Python axpy under a real
    CPython 3.10, collected by py-spy because the trampolines do not
    exist there. The decision, the collection and the ingestion all
    replay from the recorded invocations."""

    def test_axpy_emerges_and_the_loss_is_named(self, tmp_path, monkeypatch, capsys):
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
                    [
                        "run", "--replay", str(ENTRY), "--json",
                        "--", "python3.10", "hot.py",
                    ]
                )
                == 0
            )
        capsys.readouterr()
        summary = json.loads(out.getvalue())
        names = {d["name"] for d in summary["degradations"]}
        assert "python-counters-unavailable" in names
        assert "python-hotspots-unavailable" not in names
        run = read_run(summary["run"])
        diagnostics = analysis.diagnose(run)
        top = diagnostics[0]
        assert top.hotspot.display_name == "axpy"
        assert top.hotspot.resolution_level is ResolutionLevel.FUNCTION
        assert top.share.value > 0.9
        clocked = [m for m in run.measurements if m.counter == "cpu-clock"]
        assert clocked and all(m.unit == "ns" for m in clocked)
