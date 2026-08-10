"""perf adapter: detection and command-line construction."""

from nunatak.collect import cpu_collector
from nunatak.collect.perf import PerfAdapter
from nunatak.config import Config
from support import ScriptedExecutor


def test_detect_extracts_the_version():
    executor = ScriptedExecutor().on("perf", stdout="perf version 6.12.9\n")
    assert PerfAdapter().detect(executor) == "6.12.9"


def test_detect_reports_an_unusable_tool():
    executor = ScriptedExecutor().on("perf", exit_code=127)
    assert PerfAdapter().detect(executor) is None


def test_collect_records_then_extracts_what_nunatak_consumes(tmp_path):
    executor = (
        ScriptedExecutor()
        .on("perf", exit_code=3)  # record: the application exited with 3
        .on("perf", stdout="sample lines\n")  # script
        .on("perf", stdout="deadbeef /opt/solver\n")  # buildid-list
    )
    exit_code, degradations = PerfAdapter().collect(
        ["./solver", "--steps", "10"], tmp_path / "collect", executor, frequency=997
    )

    assert exit_code == 3
    assert degradations == []
    record, script, buildid = executor.calls
    assert record[1] == "record"
    assert record[record.index("--freq") + 1] == "997"
    assert record[record.index("--") + 1 :] == ["./solver", "--steps", "10"]
    assert script[1] == "script"
    assert "--fields" in script
    assert buildid[1] == "buildid-list"
    assert (tmp_path / "collect" / "perf-script.txt").read_text() == "sample lines\n"
    assert (tmp_path / "collect" / "perf-buildid-list.txt").read_text() == "deadbeef /opt/solver\n"


def test_the_cpu_collector_is_linux_only():
    executor = ScriptedExecutor(system="Darwin")
    assert cpu_collector(executor, Config()) == (None, None)
    assert executor.calls == []  # not even probed


def test_blocked_sampling_degrades_instead_of_failing_the_launch():
    # kernel.perf_event_paranoid>=3 (Ubuntu default): the tool is present
    # and its version detected, but no adapter is selected - the run then
    # proceeds without a collector rather than dying inside perf record.
    executor = ScriptedExecutor(
        blocked="kernel.perf_event_paranoid=4 forbids unprivileged profiling"
    ).on("perf", stdout="perf version 6.14.11\n")
    assert cpu_collector(executor, Config()) == (None, "6.14.11")


def test_the_blocked_reason_reaches_the_doctor_degradation():
    from nunatak.cli.doctor import light_checks

    executor = ScriptedExecutor(
        blocked="kernel.perf_event_paranoid=4 forbids unprivileged profiling"
    )
    (check,) = [
        c
        for c in light_checks(executor, Config(), [], cpu=(None, "6.14.11"))
        if c.name == "cpu-collector"
    ]
    assert check.degradation is not None
    assert "perf 6.14.11 found" in check.degradation.message
    assert "perf_event_paranoid=4" in check.degradation.message


def test_the_configured_perf_path_is_used():
    executor = ScriptedExecutor().on("perf", stdout="perf version 6.8\n")
    adapter, version = cpu_collector(
        executor, Config(tools={"perf": "/opt/tools/perf"})
    )
    assert version == "6.8"
    assert adapter.path == "/opt/tools/perf"
    assert executor.calls == [["/opt/tools/perf", "--version"]]
