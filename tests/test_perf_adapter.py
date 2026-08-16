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


class TestRecordingLadder:
    """perf validates its options before launching: a rejection fails
    fast, the adapter walks down its own ladder, and the application
    runs exactly once - in the attempt perf accepts."""

    def test_the_decided_stack_mode_rides_the_record(self, tmp_path):
        executor = (
            ScriptedExecutor()
            .on("perf", exit_code=0)  # record
            .on("perf", stdout="lines\n")  # script
            .on("perf", stdout="")  # buildid-list
        )
        PerfAdapter().collect(
            ["./solver"], tmp_path, executor, frequency=997, call_graph="fp"
        )
        record = executor.calls[0]
        assert record[record.index("--call-graph") + 1] == "fp"

    def test_a_rejected_stack_mode_is_dropped_and_named(self, tmp_path):
        executor = (
            ScriptedExecutor()
            .on("perf", exit_code=129)  # record with --call-graph: rejected
            .on("perf", exit_code=1)  # script: nothing to read
            .on("perf", exit_code=0)  # record without stacks
            .on("perf", stdout="lines\n")  # script
            .on("perf", stdout="")  # buildid-list
        )
        exit_code, degradations = PerfAdapter().collect(
            ["./solver"], tmp_path, executor, frequency=997, call_graph="lbr"
        )
        assert exit_code == 0
        assert [d.name for d in degradations] == ["call-stacks-rejected"]
        retried = executor.calls[2]
        assert "--call-graph" not in retried
        assert (tmp_path / "perf-script.txt").read_text() == "lines\n"

    def test_stacks_and_events_can_fall_in_sequence(self, tmp_path):
        executor = ScriptedExecutor()
        for _ in range(2):
            executor.on("perf", exit_code=129).on("perf", exit_code=1)
        executor.on("perf", exit_code=0).on("perf", stdout="lines\n")
        executor.on("perf", stdout="")  # buildid-list
        event = type("Event", (), {"selector": "cycles"})()
        exit_code, degradations = PerfAdapter().collect(
            ["./solver"], tmp_path, executor, frequency=997,
            events=(event,), call_graph="fp",
        )
        assert exit_code == 0
        assert [d.name for d in degradations] == [
            "call-stacks-rejected",
            "counter-events-rejected",
        ]
        bare = executor.calls[4]
        assert "--call-graph" not in bare and "-e" not in bare

    def test_an_application_failure_never_trips_the_ladder(self, tmp_path):
        executor = (
            ScriptedExecutor()
            .on("perf", exit_code=3)  # record: the application exited with 3
            .on("perf", stdout="lines\n")  # script reads the data fine
            .on("perf", stdout="")  # buildid-list
        )
        exit_code, degradations = PerfAdapter().collect(
            ["./solver"], tmp_path, executor, frequency=997, call_graph="fp"
        )
        assert exit_code == 3
        assert degradations == []
        assert len(executor.calls) == 3
