"""Comparison of two Runs: the logical function as the stable unit.

The scenario that fixes the design: a function is optimized, the
recompiled build inlines it, its symbol vanishes - and the diff must
still name it, because the inline frames carry it through. Deltas wear
their own sampling error, and what is not comparable is declared.
"""

from nunatak.compare import APPEARANCE_FLOOR, Side, compare
from nunatak.pivot import (
    AddressDetail,
    Hotspot,
    InlineFrame,
    LogicalIdentity,
    ResolutionLevel,
)
from tests.test_analysis import hotspot, measurement, run_with


def frame(function, file="/src/app.c", line=None):
    return InlineFrame(function=function, file=file, line=line)


def detail(spot, offset, value, frames, samples=None):
    return AddressDetail(
        hotspot=spot,
        offset=offset,
        counter="task-clock",
        value=value,
        frames=tuple(frames),
        sample_count=samples,
    )


def run_of(measurements, details=(), the_machine=None):
    run = run_with(measurements, the_machine=the_machine)
    run.address_details = list(details)
    return run


class TestMatching:
    def test_an_inlined_function_still_matches_across_the_runs(self):
        # Before: axpy is its own symbol. After: the compiler inlined it
        # into main - the symbol is gone, the inline frame carries it.
        axpy = hotspot("axpy")
        before = run_of(
            [measurement(axpy, "task-clock", 2e9, "ns")],
            [detail(axpy, 0x10, 100.0, [frame("axpy")], samples=100)],
        )
        main = hotspot("main")
        after = run_of(
            [measurement(main, "task-clock", 1e9, "ns")],
            [detail(main, 0x40, 100.0, [frame("main"), frame("axpy")], samples=100)],
        )
        comparison = compare(before, after)
        names = {delta.function for delta in comparison.deltas}
        assert "axpy" in names
        axpy_delta = next(d for d in comparison.deltas if d.function == "axpy")
        assert axpy_delta.before is not None and axpy_delta.after is not None
        assert axpy_delta.change == -1e9

    def test_a_hotspot_without_detail_matches_on_its_logical_identity(self):
        before = run_of([measurement(hotspot("solve"), "task-clock", 2e9, "ns")])
        after = run_of([measurement(hotspot("solve"), "task-clock", 1e9, "ns")])
        delta = compare(before, after).deltas[0]
        assert delta.function == "solve"
        assert delta.change == -1e9

    def test_an_unresolved_hotspot_matches_on_its_module(self):
        nameless = Hotspot(
            logical_identity=LogicalIdentity(module="/opt/libfoo.so"),
            resolution_level=ResolutionLevel.UNRESOLVED,
        )
        before = run_of([measurement(nameless, "task-clock", 2e9, "ns")])
        after = run_of([measurement(nameless, "task-clock", 2e9, "ns")])
        delta = compare(before, after).deltas[0]
        assert delta.function == "libfoo.so"
        assert delta.file is None

    def test_a_ventilated_hotspot_splits_its_time_over_its_frames(self):
        spot = hotspot("main")
        run = run_of(
            [measurement(spot, "task-clock", 2e9, "ns")],
            [
                detail(spot, 0x10, 75.0, [frame("main"), frame("axpy")], samples=75),
                detail(spot, 0x20, 25.0, [frame("main")], samples=25),
            ],
        )
        comparison = compare(run, run)
        axpy = next(d for d in comparison.deltas if d.function == "axpy")
        assert axpy.before.value == 1.5e9
        assert axpy.before.samples == 75


class TestSignificance:
    def test_a_delta_within_the_sampling_error_is_not_a_gain(self):
        # 3% apart, each side at 10% relative error: the spec's example.
        before = run_of([measurement(hotspot(), "task-clock", 2.0e9, "ns")])
        after = run_of([measurement(hotspot(), "task-clock", 1.94e9, "ns")])
        delta = compare(before, after).deltas[0]
        assert delta.change is not None
        assert delta.significant is False
        assert delta.combined_error > abs(delta.change)

    def test_a_delta_beyond_the_error_is_significant(self):
        before = run_of(
            [measurement(hotspot(), "task-clock", 2.0e9, "ns", samples=10000)]
        )
        after = run_of(
            [measurement(hotspot(), "task-clock", 1.0e9, "ns", samples=10000)]
        )
        delta = compare(before, after).deltas[0]
        assert delta.significant is True

    def test_one_sided_entities_carry_no_verdict(self):
        before = run_of([measurement(hotspot("gone"), "task-clock", 2e9, "ns")])
        after = run_of([measurement(hotspot("born"), "task-clock", 2e9, "ns")])
        for delta in compare(before, after).deltas:
            assert delta.change is None
            assert delta.significant is False

    def test_the_total_wears_the_same_rule(self):
        before = run_of([measurement(hotspot(), "task-clock", 2.0e9, "ns")])
        after = run_of([measurement(hotspot(), "task-clock", 1.98e9, "ns")])
        total = compare(before, after).total
        assert total.before == Side(value=2.0e9, samples=100)
        assert total.significant is False


class TestChurn:
    def test_below_the_floor_appearances_are_folded_away(self):
        heavy, tiny = hotspot("heavy"), hotspot("tiny")
        before = run_of([measurement(heavy, "task-clock", 1e9, "ns")])
        after = run_of(
            [
                measurement(heavy, "task-clock", 1e9, "ns"),
                measurement(
                    tiny, "task-clock", 1e9 * APPEARANCE_FLOOR / 2, "ns", samples=3
                ),
            ]
        )
        names = {d.function for d in compare(before, after).deltas}
        assert names == {"heavy"}

    def test_deltas_come_heaviest_first(self):
        small, big = hotspot("small"), hotspot("big")
        run = run_of(
            [
                measurement(small, "task-clock", 1e9, "ns", thread=1),
                measurement(big, "task-clock", 3e9, "ns", thread=2),
            ]
        )
        assert [d.function for d in compare(run, run).deltas] == ["big", "small"]


class TestFindings:
    def test_identical_conditions_declare_nothing(self):
        run = run_of([measurement(hotspot(), "task-clock", 2e9, "ns")])
        assert compare(run, run).findings == ()

    def test_two_machines_are_declared_not_masked(self):
        import dataclasses

        one = run_of([measurement(hotspot(), "task-clock", 2e9, "ns")])
        other = run_of([measurement(hotspot(), "task-clock", 2e9, "ns")])
        other.machine = dataclasses.replace(other.machine, cpu_model="Other CPU")
        findings = compare(one, other).findings
        assert {f.name for f in findings} == {"different-machines"}
        assert "Other CPU" in findings[0].message

    def test_two_commands_are_declared(self):
        one = run_of([measurement(hotspot(), "task-clock", 2e9, "ns")])
        other = run_of([measurement(hotspot(), "task-clock", 2e9, "ns")])
        other.command = ["./solver", "--bigger-mesh"]
        findings = {f.name for f in compare(one, other).findings}
        assert "different-commands" in findings

    def test_two_topologies_are_declared(self):
        from nunatak.pivot import Locus, Measurement, Quality

        def ranked(rank):
            return Measurement(
                hotspot=hotspot(),
                locus=Locus(node="n0", rank=rank),
                counter="task-clock",
                value=1e9,
                unit="ns",
                quality=Quality.MEASURED,
                sample_count=100,
            )

        one = run_of([ranked(0), ranked(1)])
        other = run_of([ranked(0), ranked(1), ranked(2), ranked(3)])
        findings = {f.name for f in compare(one, other).findings}
        assert "different-topologies" in findings

    def test_two_time_bases_are_declared(self):
        one = run_of([measurement(hotspot(), "task-clock", 2e9, "ns")])
        other = run_of([measurement(hotspot(), "cpu-clock", 2e9, "ns")])
        findings = {f.name for f in compare(one, other).findings}
        assert "different-time-bases" in findings


class TestUnit:
    def test_a_shared_clock_base_carries_its_unit(self):
        run = run_of([measurement(hotspot(), "task-clock", 2e9, "ns")])
        assert compare(run, run).unit == "ns"

    def test_disagreeing_units_leave_none(self):
        one = run_of([measurement(hotspot(), "task-clock", 2e9, "ns")])
        other = run_of([measurement(hotspot(), "cycles", 4e9, "cycle")])
        assert compare(one, other).unit is None


class TestVerb:
    """The compare verb: terminal first level, full diff for machines."""

    @staticmethod
    def written(tmp_path, name, value, function="axpy"):
        from nunatak.pivot import write_run

        run = run_of([measurement(hotspot(function), "task-clock", value, "ns")])
        run.name = name
        directory = tmp_path / name
        write_run(directory, run)
        return directory

    def test_the_json_diff_carries_verdicts_for_a_ci(self, tmp_path, capsys):
        import json as json_module

        from nunatak.cli import principal

        before = self.written(tmp_path, "before", 2.0e9)
        after = self.written(tmp_path, "after", 1.94e9)
        assert principal(["compare", str(before), str(after), "--json"]) == 0
        payload = json_module.loads(capsys.readouterr().out)
        assert payload["unit"] == "ns"
        delta = payload["deltas"][0]
        assert delta["function"] == "axpy"
        assert delta["significant"] is False
        assert delta["combined_error"] > abs(delta["change"])
        assert payload["total"]["change"] == delta["change"]
        assert payload["findings"] == []

    def test_the_terminal_says_when_a_delta_is_not_a_difference(
        self, tmp_path, capsys
    ):
        from nunatak.cli import principal

        before = self.written(tmp_path, "before", 2.0e9)
        after = self.written(tmp_path, "after", 1.94e9)
        assert principal(["compare", str(before), str(after)]) == 0
        err = capsys.readouterr().err
        assert "compare: before -> after" in err
        assert "not a difference" in err
        assert "2 s -> 1.94 s" in err

    def test_an_unreadable_run_is_a_125(self, tmp_path, capsys):
        from nunatak.cli import principal

        good = self.written(tmp_path, "good", 2.0e9)
        assert principal(["compare", str(tmp_path / "absent"), str(good)]) == 125

    def test_findings_arrive_as_warnings(self, tmp_path, capsys):
        import json as json_module

        from nunatak.cli import principal

        before = self.written(tmp_path, "before", 2.0e9)
        after = self.written(tmp_path, "after", 2.0e9)
        manifest = json_module.loads((after / "manifest.json").read_text())
        manifest["run"]["command"] = ["./solver", "--other-mesh"]
        (after / "manifest.json").write_text(json_module.dumps(manifest))
        assert principal(["compare", str(before), str(after)]) == 0
        err = capsys.readouterr().err
        assert "not directly comparable [different-commands]" in err
