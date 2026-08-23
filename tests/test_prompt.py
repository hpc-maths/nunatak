"""What the model sees, pinned.

The prompt is a pure function of the measured pivot: these tests hold
the eligibility guards - the dangerous class of bugs is sending what
must be withheld - and freeze the rendered prompt as a snapshot, so any
change to what the model receives becomes a diff read in review.
"""

import os
from pathlib import Path

from nunatak import analysis
from nunatak.explain import SYSTEM_PROMPT, requests
from nunatak.pivot import (
    AddressDetail,
    Hotspot,
    InlineFrame,
    LogicalIdentity,
    LoopAnalysis,
    ResolutionLevel,
    SourceExtract,
)
from tests.test_analysis import balanced, hotspot, measurement, run_with

SNAPSHOT = Path(__file__).parent / "snapshots" / "explanation-prompt.md"


def frame(function, line=None):
    return InlineFrame(function=function, file="/src/app.c", line=line)


def detail(spot, offset, value, frames, counter="task-clock"):
    return AddressDetail(
        hotspot=spot, offset=offset, counter=counter, value=value, frames=tuple(frames)
    )


def extract_for(spot, text="for (int i = 0; i < n; i++)\n    a[i] = b[i] + 3.0 * c[i];"):
    return SourceExtract(
        hotspot=spot, file="/src/app.c", start_line=4, end_line=5, text=text
    )


def prompts_of(measurements, **run_fields):
    run = run_with(measurements)
    for name, value in run_fields.items():
        setattr(run, name, value)
    return run, requests(run, analysis.diagnose(run))


class TestEligibility:
    def test_a_hotspot_with_source_earns_a_prompt(self):
        spot = hotspot()
        _, (asked, withheld) = prompts_of(
            [measurement(spot, "task-clock", 2e9, "ns")],
            source_extracts=[extract_for(spot)],
        )
        assert [request.hotspot for request in asked] == [spot]
        assert withheld == []

    def test_below_the_floor_the_model_never_hears_of_it(self):
        spot, thin = hotspot(), hotspot("thin")
        _, (asked, withheld) = prompts_of(
            [
                measurement(spot, "task-clock", 2e9, "ns"),
                measurement(thin, "task-clock", 1e9, "ns", samples=3),
            ],
            source_extracts=[extract_for(spot), extract_for(thin)],
        )
        mentioned = {request.hotspot for request in asked} | {
            entry.hotspot for entry in withheld
        }
        assert thin not in mentioned

    def test_an_unresolved_hotspot_is_withheld(self):
        nameless = Hotspot(
            logical_identity=LogicalIdentity(module="/app/solver"),
            resolution_level=ResolutionLevel.UNRESOLVED,
        )
        _, (asked, withheld) = prompts_of(
            [measurement(nameless, "task-clock", 2e9, "ns")]
        )
        assert asked == []
        assert "not resolved" in withheld[0].reason

    def test_without_source_no_explanation(self):
        # --no-source and a source-less module meet the same guard: the
        # Run carries no extract, the Hotspot is withheld.
        _, (asked, withheld) = prompts_of(
            [measurement(hotspot(), "task-clock", 2e9, "ns")]
        )
        assert asked == []
        assert "no source available" in withheld[0].reason

    def test_an_absent_extract_keeps_its_recorded_reason(self):
        spot = hotspot()
        refused = SourceExtract(
            hotspot=spot, file="/src/app.c", reason="line table fingerprints disagree"
        )
        _, (asked, withheld) = prompts_of(
            [measurement(spot, "task-clock", 2e9, "ns")],
            source_extracts=[refused],
        )
        assert asked == []
        assert withheld[0].reason == "line table fingerprints disagree"


class TestContent:
    def test_an_unavailable_fact_is_omitted_never_narrated(self):
        # Time only: intensity and envelope are unavailable in the
        # Diagnostic, so their lines must not exist - the report states
        # absences, the model never hears them.
        spot = hotspot()
        _, (asked, _) = prompts_of(
            [measurement(spot, "task-clock", 2e9, "ns")],
            source_extracts=[extract_for(spot)],
        )
        prompt = asked[0].prompt
        assert "unavailable" not in prompt
        assert "DRAM arithmetic intensity" not in prompt
        assert "achieved" not in prompt
        assert "no roofline placement:" in prompt

    def test_a_placed_hotspot_states_its_facts_with_downgrades(self):
        from nunatak.pivot import Quality
        from tests.test_analysis import machine

        spot = hotspot()
        run = run_with(
            balanced(spot, flops=2.4e9, bytes_=1e10, seconds=2.0),
            the_machine=machine(quality=Quality.ESTIMATED),
        )
        run.source_extracts = [extract_for(spot)]
        asked, _ = requests(run, analysis.diagnose(run))
        prompt = asked[0].prompt
        assert "- classification: " in prompt
        assert "- share of the sampled time: 100%" in prompt
        assert "(estimated: theory)" in prompt

    def test_the_loop_facts_are_counts_never_the_stream(self):
        spot = hotspot()
        loop = LoopAnalysis(
            hotspot=spot,
            start_offset=0x40,
            end_offset=0x80,
            instructions=12,
            flops_per_iteration=16.0,
            vector_fp=4,
            scalar_fp=0,
            vector_width_bits=128,
            loaded_bytes=128,
            stored_bytes=64,
            gathers=0,
            cycles_ports=1.8,
            cycles_effective=4.0,
            scheduling_model="znver2",
        )
        _, (asked, _) = prompts_of(
            [measurement(spot, "task-clock", 2e9, "ns")],
            source_extracts=[extract_for(spot)],
            loop_analyses=[loop],
        )
        prompt = asked[0].prompt
        assert "12 instructions per iteration, 16 FLOPs" in prompt
        assert "vectorized: 100% of the FP instructions, 128-bit" in prompt
        assert "cycle bounds (model znver2): 1.8 port-bound, 4 steady state" in prompt

    def test_the_line_distribution_rides_along(self):
        spot = hotspot()
        _, (asked, _) = prompts_of(
            [measurement(spot, "task-clock", 2e9, "ns")],
            address_details=[
                detail(spot, 0x10, 70.0, [frame("main", line=5)]),
                detail(spot, 0x18, 30.0, [frame("main", line=6)]),
            ],
            source_extracts=[extract_for(spot)],
        )
        prompt = asked[0].prompt
        assert "- line 5: 70%" in prompt
        assert "- line 6: 30%" in prompt

    def test_the_source_rides_with_its_place(self):
        spot = hotspot()
        _, (asked, _) = prompts_of(
            [measurement(spot, "task-clock", 2e9, "ns")],
            source_extracts=[extract_for(spot)],
        )
        prompt = asked[0].prompt
        assert "## Source (`/src/app.c`, lines 4-5)" in prompt
        assert "a[i] = b[i] + 3.0 * c[i];" in prompt


class TestSnapshot:
    """The full artifact, frozen. On a legitimate change, regenerate
    with NUNATAK_UPDATE_SNAPSHOTS=1 and read the diff."""

    def test_what_the_model_sees_is_frozen(self):
        spot = hotspot("axpy")
        loop = LoopAnalysis(
            hotspot=spot,
            start_offset=0x40,
            end_offset=0x80,
            instructions=12,
            flops_per_iteration=16.0,
            vector_fp=4,
            scalar_fp=0,
            vector_width_bits=128,
            loaded_bytes=128,
            stored_bytes=64,
            gathers=0,
            cycles_ports=1.8,
            cycles_effective=4.0,
            scheduling_model="znver2",
        )
        run = run_with(balanced(spot, flops=2.4e9, bytes_=1e10, seconds=2.0))
        run.address_details = [
            detail(spot, 0x10, 70.0, [frame("axpy", line=5)]),
            detail(spot, 0x18, 30.0, [frame("axpy", line=4)]),
        ]
        run.source_extracts = [extract_for(spot)]
        run.loop_analyses = [loop]
        asked, withheld = requests(run, analysis.diagnose(run))
        assert withheld == []
        rendered = (
            "# System prompt\n\n" + SYSTEM_PROMPT + "\n"
            + "".join(
                f"\n# Prompt for {request.hotspot.display_name}\n\n{request.prompt}\n"
                for request in asked
            )
        )
        if os.environ.get("NUNATAK_UPDATE_SNAPSHOTS"):
            SNAPSHOT.parent.mkdir(exist_ok=True)
            SNAPSHOT.write_text(rendered, encoding="utf-8")
        assert rendered == SNAPSHOT.read_text(encoding="utf-8")
