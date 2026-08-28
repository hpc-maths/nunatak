"""The deterministic analysis engine: properties, never numbers.

Synthetic pivots exercise every regime; the replayed corpus Run checks
the engine's honesty on real data that carries no FLOP counters yet.
"""

import json

import pytest

from nunatak import analysis
from nunatak.pivot import (
    Allocation,
    Ceiling,
    Hotspot,
    LogicalIdentity,
    Locus,
    Machine,
    Measurement,
    Provenance,
    Quality,
    ResolutionLevel,
    Run,
)


def machine(dram=1.0e11, flops=1.0e12, quality=Quality.MEASURED) -> Machine:
    reason = None if quality is Quality.MEASURED else "theory"
    return Machine(
        system="Linux",
        kernel="6.14",
        architecture="x86_64",
        cpu_model="AMD EPYC 7702",
        logical_cores=32,
        allocation=Allocation(visible_cores=32),
        ceilings=(
            Ceiling(
                name="dram_bandwidth",
                value=dram,
                unit="byte/s",
                quality=quality,
                reason=reason,
            ),
            Ceiling(
                name="flops_dp",
                value=flops,
                unit="flop/s",
                quality=quality,
                reason=reason,
            ),
        ),
    )


def hotspot(name="main", file=None) -> Hotspot:
    """A named Hotspot; `file` makes it the line-level one a source
    extract can attach to."""
    return Hotspot(
        logical_identity=LogicalIdentity(
            module="/app/solver", name=name, source_file=file
        ),
        resolution_level=(
            ResolutionLevel.LINE if file else ResolutionLevel.FUNCTION
        ),
    )


def measurement(spot, counter, value, unit, thread=1, samples=100):
    return Measurement(
        hotspot=spot,
        locus=Locus(node="n0", thread=thread),
        counter=counter,
        value=value,
        unit=unit,
        quality=Quality.MEASURED,
        sample_count=samples,
    )


def run_with(measurements, the_machine=None) -> Run:
    return Run(
        name="r",
        created="2026-08-10T12:00:00+00:00",
        command=["./solver"],
        exit_code=0,
        machine=the_machine if the_machine is not None else machine(),
        provenance=Provenance(),
        measurements=measurements,
    )


def balanced(spot, flops, bytes_, seconds):
    # Two concurrent threads, both busy for the whole duration: each
    # Locus carries the full wall time in cpu-time, the work splits.
    return [
        measurement(spot, "task-clock", seconds * 1e9, "ns", thread=t)
        for t in (1, 2)
    ] + [
        measurement(spot, "flops_dp", flops / 2, "flop", thread=t) for t in (1, 2)
    ] + [
        measurement(spot, "dram_bytes", bytes_ / 2, "byte", thread=t)
        for t in (1, 2)
    ]


class TestEnvelope:
    def test_the_diagonal_stops_at_the_break_point_never_crosses_it(self):
        ceilings = {c.name: c for c in machine().ceilings}
        ridge = 1.0e12 / 1.0e11
        below, _, _, _ = analysis.envelope(ridge / 2, ceilings)
        at, _, _, _ = analysis.envelope(ridge, ceilings)
        far_beyond, _, _, _ = analysis.envelope(ridge * 100, ceilings)
        assert below == 1.0e11 * ridge / 2
        assert at == 1.0e12
        assert far_beyond == 1.0e12

    def test_a_missing_ceiling_yields_no_envelope(self):
        assert analysis.envelope(1.0, {}) is None


class TestPlacement:
    def test_a_memory_bound_hotspot_is_named_as_such(self):
        # Intensity 2 flop/byte, ridge at 10: memory side. Achieved 1.6e11
        # of an attainable 2e11: 80% of the envelope.
        spot = hotspot()
        run = run_with(balanced(spot, flops=1.6e10, bytes_=8.0e9, seconds=0.1))
        (diagnostic,) = analysis.diagnose(run)
        assert diagnostic.dram_intensity.value == 2.0
        assert diagnostic.attainable.value == 2.0e11
        assert diagnostic.envelope_fraction.value == pytest.approx(0.8)
        assert diagnostic.classification == "memory-bound"
        assert diagnostic.share.value == 1.0

    def test_a_compute_bound_hotspot_sits_past_the_ridge(self):
        # Intensity 20, past the ridge: attainable is the flat peak.
        spot = hotspot()
        run = run_with(balanced(spot, flops=8.0e10, bytes_=4.0e9, seconds=0.1))
        (diagnostic,) = analysis.diagnose(run)
        assert diagnostic.attainable.value == 1.0e12
        assert diagnostic.classification == "compute-bound"

    def test_far_below_both_bounds_the_regime_is_latency(self):
        spot = hotspot()
        run = run_with(balanced(spot, flops=2.0e9, bytes_=1.0e9, seconds=0.1))
        (diagnostic,) = analysis.diagnose(run)
        assert diagnostic.envelope_fraction.value == pytest.approx(0.1)
        assert diagnostic.classification == "latency-bound"

    def test_imbalance_speaks_before_the_roofline(self):
        spot = hotspot()
        run = run_with(
            [
                measurement(spot, "task-clock", 9.0e8, "ns", thread=1),
                measurement(spot, "task-clock", 1.0e8, "ns", thread=2),
                measurement(spot, "flops_dp", 1.6e10, "flop", thread=1),
                measurement(spot, "dram_bytes", 8.0e9, "byte", thread=1),
            ]
        )
        (diagnostic,) = analysis.diagnose(run)
        assert diagnostic.imbalance.value == pytest.approx(9.0)
        assert diagnostic.classification == "imbalance"


class TestQualityPropagation:
    def test_estimated_ceilings_make_an_estimated_placement(self):
        spot = hotspot()
        run = run_with(
            balanced(spot, flops=1.6e10, bytes_=8.0e9, seconds=0.1),
            the_machine=machine(quality=Quality.ESTIMATED),
        )
        (diagnostic,) = analysis.diagnose(run)
        assert diagnostic.dram_intensity.quality is Quality.MEASURED
        assert diagnostic.attainable.quality is Quality.ESTIMATED
        assert diagnostic.envelope_fraction.quality is Quality.ESTIMATED

    def test_the_lineage_names_the_sources(self):
        spot = hotspot()
        run = run_with(balanced(spot, flops=1.6e10, bytes_=8.0e9, seconds=0.1))
        (diagnostic,) = analysis.diagnose(run)
        assert diagnostic.dram_intensity.lineage == ("flops_dp", "dram_bytes")
        assert "dram_bandwidth" in diagnostic.attainable.lineage


class TestHonesty:
    def test_without_flop_counters_the_placement_says_why(self):
        spot = hotspot()
        run = run_with(
            [
                measurement(spot, "task-clock", 1.0e8, "ns", thread=t)
                for t in (1, 2)
            ]
        )
        (diagnostic,) = analysis.diagnose(run)
        assert diagnostic.dram_intensity.value is None
        assert "flops_dp" in diagnostic.dram_intensity.reason
        assert diagnostic.classification is None
        assert diagnostic.classification_reason is not None
        # The share and the imbalance survive without FLOPs.
        assert diagnostic.share.value == 1.0
        assert diagnostic.imbalance.value == 1.0

    def test_a_cycles_only_run_keeps_share_but_not_flops_per_second(self):
        spot = hotspot()
        run = run_with(
            [
                measurement(spot, "cycles", 1.0e9, "cycles"),
                measurement(spot, "flops_dp", 1.0e10, "flop"),
                measurement(spot, "dram_bytes", 1.0e9, "byte"),
            ]
        )
        (diagnostic,) = analysis.diagnose(run)
        assert diagnostic.share.value == 1.0
        assert diagnostic.dram_intensity.value == 10.0
        assert diagnostic.achieved.value is None
        assert "time base" in diagnostic.achieved.reason

    def test_the_statistical_floor_filters_noise(self):
        loud, quiet = hotspot("loud"), hotspot("quiet")
        run = run_with(
            [
                measurement(loud, "task-clock", 9.9e8, "ns", samples=990),
                measurement(quiet, "task-clock", 1.0e7, "ns", samples=10),
            ]
        )
        diagnostics = analysis.diagnose(run)
        assert [d.hotspot.display_name for d in diagnostics] == ["loud"]

    def test_diagnostics_come_ordered_by_share(self):
        first, second = hotspot("first"), hotspot("second")
        run = run_with(
            [
                measurement(second, "task-clock", 3.0e8, "ns"),
                measurement(first, "task-clock", 7.0e8, "ns"),
            ]
        )
        names = [d.hotspot.display_name for d in analysis.diagnose(run)]
        assert names == ["first", "second"]

    def test_an_unavailable_derived_metric_is_never_a_number(self):
        with pytest.raises(ValueError, match="not even zero"):
            analysis.Derived(
                name="x", value=1.0, unit="u", quality=Quality.UNAVAILABLE, reason="r"
            )
        with pytest.raises(ValueError, match="says why"):
            analysis.Derived(
                name="x", value=None, unit="u", quality=Quality.UNAVAILABLE
            )


class TestReplayedRun:
    """The engine against the calibrated corpus Run: measured ceilings,
    cycles-only measurements - shares and honest absences."""

    @pytest.fixture(autouse=True)
    def in_tmp_cwd(self, tmp_path, monkeypatch):
        from tests.support import WORKLOAD_C

        (tmp_path / "nunatak.toml").write_text(
            '[tools]\nllvm-symbolizer = "/usr/lib/llvm-19/bin/llvm-symbolizer"\n'
        )
        (tmp_path / "workload.c").write_text(WORKLOAD_C)
        monkeypatch.chdir(tmp_path)

    def test_the_replayed_run_diagnoses_honestly(self, capsys):
        from pathlib import Path

        from nunatak.cli import principal
        from nunatak.pivot import read_run

        entry = (
            Path(__file__).resolve().parent.parent
            / "corpus"
            / "recordings"
            / "perf"
            / "6.14.11"
            / "linux-x86_64"
            / "workload-c-calibrated"
        )
        assert principal(["run", "--replay", str(entry), "--json", "--", "./workload"]) == 0
        summary = json.loads(capsys.readouterr().out)
        run = read_run(summary["run"])

        diagnostics = analysis.diagnose(run)
        assert diagnostics
        main = diagnostics[0]
        assert main.hotspot.display_name == "main"
        assert main.share.value > 0.9
        # The workload's 8 MiB fit inside one CCX's L3 slice: the fill
        # events legitimately count nothing, so there is no DRAM traffic
        # to divide by - the placement is absent with that reason.
        assert main.dram_intensity.value is None
        assert "dram_bytes" in main.dram_intensity.reason
        assert main.classification is None


def aggregate(counter="task-clock", value=1e12, rank=0, unit="ns"):
    return Measurement(
        hotspot=None,
        locus=Locus(node="n0", rank=rank),
        counter=counter,
        value=value,
        unit=unit,
        quality=Quality.MEASURED,
    )


class TestCountingLayer:
    def test_locus_level_aggregates_never_shrink_hotspot_shares(self):
        # Whole-process counts dwarf the sampled sums; mixed into the
        # totals they would push every Hotspot under its real share.
        spot = hotspot()
        sampled = balanced(spot, flops=1.6e10, bytes_=8.0e9, seconds=0.1)
        aggregates = [aggregate(rank=r) for r in range(4)]
        with_counting = analysis.diagnose(run_with(sampled + aggregates))
        without = analysis.diagnose(run_with(sampled))
        assert [d.hotspot for d in with_counting] == [d.hotspot for d in without]
        assert [d.share.value for d in with_counting] == [
            d.share.value for d in without
        ]

    def test_a_counting_only_run_diagnoses_nothing(self):
        run = run_with([aggregate(rank=r) for r in range(2)])
        assert analysis.diagnose(run) == []
        assert analysis.time_base(run) is None


def ranked(spot, counter, value, unit, rank, thread=1, samples=100):
    return Measurement(
        hotspot=spot,
        locus=Locus(node="n0", rank=rank, thread=thread),
        counter=counter,
        value=value,
        unit=unit,
        quality=Quality.MEASURED,
        sample_count=samples,
    )


class TestBalance:
    def test_counted_ranks_state_their_imbalance(self):
        run = run_with(
            [aggregate("task-clock", value, rank=rank) for rank, value in
             enumerate([1e9, 1e9, 1e9, 2e9])]
        )
        verdict = analysis.balance(run)
        assert [rank.rank for rank in verdict.ranks] == [0, 1, 2, 3]
        assert all(rank.time.formula == "counted over the whole rank"
                   for rank in verdict.ranks)
        # max 2e9 over mean 1.25e9
        assert verdict.imbalance.value == 2e9 / 1.25e9
        assert verdict.unsampled == (0, 1, 2, 3)
        assert verdict.mpi_fraction.value is None

    def test_a_sampled_rank_takes_its_time_from_its_own_samples(self):
        spot = hotspot()
        run = run_with(
            [ranked(spot, "task-clock", 0.6e9, "ns", rank=0, thread=1),
             ranked(spot, "task-clock", 0.4e9, "ns", rank=0, thread=2),
             aggregate("task-clock", 1e9, rank=1)]
        )
        verdict = analysis.balance(run)
        zero, one = verdict.ranks
        assert zero.sampled is True
        assert zero.time.value == 1e9
        assert zero.time.formula == "sum of this rank's samples"
        assert one.sampled is False
        assert verdict.unsampled == (1,)
        assert verdict.imbalance.value == 1.0

    def test_mpi_time_and_fraction_come_from_mpip(self):
        run = run_with(
            [aggregate("task-clock", 1e9, rank=0),
             aggregate("task-clock", 1e9, rank=1),
             aggregate("app_time", 1e9, rank=0),
             aggregate("app_time", 1e9, rank=1),
             aggregate("mpi_time", 0.25e9, rank=0),
             aggregate("mpi_time", 0.35e9, rank=1)]
        )
        verdict = analysis.balance(run)
        assert verdict.ranks[0].mpi_time.value == 0.25e9
        assert verdict.mpi_fraction.value == 0.3
        assert verdict.mpi_fraction.quality is Quality.MEASURED

    def test_a_single_process_run_has_no_topology(self):
        run = run_with(balanced(hotspot(), flops=1.6e10, bytes_=8e9, seconds=0.1))
        assert analysis.balance(run) is None

    def test_a_rank_without_time_makes_the_imbalance_unavailable(self):
        run = run_with(
            [aggregate("task-clock", 1e9, rank=0),
             aggregate("cycles", 5e9, rank=1, unit="cycles")]
        )
        verdict = analysis.balance(run)
        assert verdict.imbalance.value is None
        assert verdict.imbalance.reason == "some ranks left no time measurement"
        assert verdict.ranks[1].time.value is None
