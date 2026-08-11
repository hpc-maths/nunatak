"""The terminal summary: the report's first reading level in the log.

Synthetic pivots pin the shape of every section; the replayed milestone
corpus entry holds the whole `run` log to what real PMUs recorded.
"""

import dataclasses
from pathlib import Path

from nunatak import analysis, summary
from nunatak.pivot import (
    Ceiling,
    Hotspot,
    LogicalIdentity,
    PhysicalIdentity,
    Quality,
    ResolutionLevel,
)
from tests.test_analysis import balanced, hotspot, machine, measurement, run_with

ENTRY = (
    Path(__file__).resolve().parent.parent
    / "corpus"
    / "recordings"
    / "perf"
    / "6.14.11"
    / "linux-x86_64"
    / "workload-c-roofline"
)


def summarized(measurements, the_machine=None):
    run = run_with(measurements, the_machine)
    return summary.summarize(run, analysis.diagnose(run))


def placed(spot=None):
    # Intensity 2 flop/byte against a ridge at 10: memory-bound, 80% of
    # the envelope - the same placement the analysis tests pin.
    return balanced(spot or hotspot(), flops=1.6e10, bytes_=8.0e9, seconds=0.1)


class TestHeadline:
    def test_coverage_comes_first_with_samples_and_seconds(self):
        lines = summarized(placed())
        assert lines[0] == (
            "summary: 1 Hotspot above the statistical floor holds 100% of the"
            " sampled time (200 samples of task-clock over 0.2 s)"
        )

    def test_without_any_hotspot_the_floor_is_named(self):
        lines = summarized(
            [measurement(hotspot(), "task-clock", 1e9, "ns", samples=3)]
        )
        assert lines == [
            "summary: no Hotspot above the statistical floor of 30 samples",
            "what this report does not say:",
            '  - 100% of the sampled time sits below the statistical floor'
            ' of 30 samples, aggregated as "others"',
        ]

    def test_a_cycles_time_base_states_samples_but_no_seconds(self):
        lines = summarized([measurement(hotspot(), "cycles", 4e9, "cycle")])
        assert "100 samples of cycles" in lines[0]
        assert " over " not in lines[0]


class TestFindings:
    def test_a_placed_hotspot_shows_its_evidence(self):
        lines = summarized(placed())
        assert lines[1] == "  main (function) - 100% of the sampled time - memory-bound"
        assert lines[2] == (
            "    achieved 160 GFLOP/s of 200 GFLOP/s attainable: 80% of the envelope"
        )
        assert lines[3] == "    DRAM intensity 2 flop/byte"

    def test_an_unplaceable_hotspot_says_why_where_expected(self):
        lines = summarized([measurement(hotspot(), "task-clock", 2e9, "ns")])
        assert lines[1] == (
            "  main (function) - 100% of the sampled time"
            " - no placement: no flops_dp raw counter in this Run"
        )

    def test_an_imbalanced_hotspot_shows_the_ratio(self):
        spot = hotspot()
        lines = summarized(
            [
                measurement(spot, "task-clock", 3e9, "ns", thread=1),
                measurement(spot, "task-clock", 1e9, "ns", thread=2),
            ]
        )
        assert " - imbalance" in lines[1]
        assert lines[2] == "    most-loaded Locus carries 3.0x the least-loaded"

    def test_a_shared_downgrade_reason_appears_once(self):
        # `flops` unsplit by precision downgrades intensity, achieved and
        # the envelope fraction with the same motive: the finding states
        # it a single time.
        spot = hotspot()
        run = run_with(
            [
                measurement(spot, "task-clock", 2e9, "ns"),
                measurement(spot, "flops", 8e9, "flop"),
                measurement(spot, "dram_bytes", 1e9, "byte"),
            ]
        )
        lines = summary.summarize(run, analysis.diagnose(run))
        downgrades = [line for line in lines if "downgraded to estimated" in line]
        assert len(downgrades) == 1
        assert downgrades[0].count("FLOPs not split by precision") == 1

    def test_findings_beyond_the_cap_are_counted_never_dropped_silently(self):
        measurements = []
        for index in range(summary.MAX_FINDINGS + 2):
            measurements.extend(placed(hotspot(f"f{index}")))
        lines = summarized(measurements)
        assert lines[-1] == (
            "  ... and 2 Hotspots above the floor,"
            " holding 17% of the sampled time"
        )


class TestAdmissions:
    def test_unresolved_time_is_admitted(self):
        unresolved = Hotspot(
            logical_identity=LogicalIdentity(module="/usr/lib/libm.so"),
            resolution_level=ResolutionLevel.UNRESOLVED,
            physical_identity=PhysicalIdentity(module_id="abc", offset=0x3A1C),
        )
        lines = summarized(
            [
                measurement(hotspot(), "task-clock", 3e9, "ns"),
                measurement(unresolved, "task-clock", 1e9, "ns"),
            ]
        )
        assert any(
            line.startswith("  libm.so+0x3a1c (unresolved) - 25% of the sampled time")
            for line in lines
        )
        assert (
            "  - 25% of the sampled time is attributed to no name"
            " (unresolved addresses)"
        ) in lines

    def test_estimated_envelope_ceilings_are_admitted_with_their_reason(self):
        lines = summarized(placed(), machine(quality=Quality.ESTIMATED))
        assert "what this report does not say:" in lines
        assert "  - the dram_bandwidth Ceiling is estimated: theory" in lines
        assert "  - the flops_dp Ceiling is estimated: theory" in lines

    def test_ceilings_outside_the_envelope_stay_out_of_the_admissions(self):
        the_machine = machine()
        the_machine = dataclasses.replace(
            the_machine,
            ceilings=the_machine.ceilings
            + (
                Ceiling(
                    name="flops_sp",
                    value=2e12,
                    unit="flop/s",
                    quality=Quality.ESTIMATED,
                    reason="theory",
                ),
            ),
        )
        lines = summarized(placed(), the_machine)
        assert not any("flops_sp" in line for line in lines)

    def test_a_complete_summary_admits_nothing(self):
        lines = summarized(placed())
        assert "what this report does not say:" not in lines


class TestReplayedRun:
    """The milestone Run end to end: the log tells the same story as the
    Diagnostic, downgrade reasons included."""

    def test_the_log_carries_the_findings_and_their_solidity(
        self, tmp_path, monkeypatch, capsys
    ):
        from nunatak.cli import principal

        (tmp_path / "nunatak.toml").write_text(
            '[tools]\nllvm-symbolizer = "/usr/lib/llvm-19/bin/llvm-symbolizer"\n'
        )
        monkeypatch.chdir(tmp_path)
        assert principal(["run", "--replay", str(ENTRY), "--", "./workload"]) == 0
        log = capsys.readouterr().err
        assert "summary: 1 Hotspot above the statistical floor holds" in log
        assert "main (line) - 100% of the sampled time - latency-bound" in log
        assert "of the envelope" in log
        assert "DRAM intensity 1.21 flop/byte" in log
        assert "downgraded to estimated: demand fills only" in log
        # The log ends on the path, after the summary.
        assert log.rstrip().splitlines()[-1].split(" ", 1)[-1].startswith("Run: ")
