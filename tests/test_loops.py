"""Static loop analysis: the hot inner loop, counted from real code.

Fixtures are verbatim objdump outputs of four real loops built on the
EPYC: scalar, SSE, AVX2+FMA and an intrinsics gather - the counts below
are exact per-iteration truths of that machine code, checked by hand.
"""

from pathlib import Path

import pytest

from nunatak.attribution import loops
from nunatak.config import Config
from nunatak.pivot import (
    AddressDetail,
    Hotspot,
    InlineFrame,
    LogicalIdentity,
    PhysicalIdentity,
    ResolutionLevel,
)
from tests.support import (
    DIS_AXPY_AVX2,
    DIS_AXPY_SCALAR,
    DIS_AXPY_SSE,
    DIS_GATHER,
    GNU_READELF_WORKLOAD_VEC,
    OBJDUMP_VERSION,
    ScriptedExecutor,
)


class TestHotLoop:
    def test_the_weighted_backward_branch_is_the_loop(self):
        instructions = loops.parse(DIS_AXPY_SCALAR)
        loop = loops.hot_loop(instructions, {0x1385: 100.0})
        assert (loop.start, loop.end) == (0x1380, 0x139A)

    def test_weight_outside_every_loop_is_no_loop(self):
        instructions = loops.parse(DIS_AXPY_SCALAR)
        assert loops.hot_loop(instructions, {0x1360: 100.0}) is None

    def test_the_heavier_loop_wins(self):
        instructions = loops.parse(DIS_AXPY_SCALAR)
        # The reduction tail loop (13e0-13f6) carries more weight here.
        loop = loops.hot_loop(instructions, {0x1385: 10.0, 0x13EB: 90.0})
        assert (loop.start, loop.end) == (0x13E0, 0x13F6)


class TestCounts:
    def _counts(self, fixture, hot):
        _, counts = loops.analyze_function(fixture, {hot: 100.0})
        return counts

    def test_the_scalar_loop_says_scalar(self):
        counts = self._counts(DIS_AXPY_SCALAR, 0x1385)
        assert counts == {
            "flops": 2.0, "vector_fp": 0, "scalar_fp": 2,
            "vector_width_bits": None,
            "loaded_bytes": 16, "stored_bytes": 8, "gathers": 0,
        }

    def test_the_sse_loop_says_128_bits(self):
        counts = self._counts(DIS_AXPY_SSE, 0x142A)
        assert counts["vector_fp"] == 2 and counts["scalar_fp"] == 0
        assert counts["vector_width_bits"] == 128
        assert counts["flops"] == 4.0
        assert (counts["loaded_bytes"], counts["stored_bytes"]) == (32, 16)

    def test_the_fma_counts_two_flops_per_lane(self):
        counts = self._counts(DIS_AXPY_AVX2, 0x1425)
        assert counts["flops"] == 8.0
        assert counts["vector_width_bits"] == 256
        assert (counts["loaded_bytes"], counts["stored_bytes"]) == (64, 32)

    def test_the_gather_is_an_indirect_access(self):
        counts = self._counts(DIS_GATHER, 0x50)
        assert counts["gathers"] == 1
        assert counts["loaded_bytes"] == 48

    def test_an_unknown_isa_yields_no_counts_not_guesses(self):
        foreign = loops.parse(
            "    700:\t9101a3bd \tfmla\tv0.2d, v1.2d, v2.2d\n"
            "    704:\t54ffffe1 \tb.ne\t700 <x>\n"
        )
        assert loops.classify(foreign) is None


def _hotspot(module):
    return Hotspot(
        logical_identity=LogicalIdentity(module=module, name="axpy"),
        resolution_level=ResolutionLevel.LINE,
        physical_identity=PhysicalIdentity(module_id="deadbeef", offset=0x1360),
    )


def _detail(spot, offset, value, samples=200):
    return AddressDetail(
        hotspot=spot, offset=offset, counter="task-clock", value=value,
        frames=(InlineFrame(function="main"),), sample_count=samples,
    )


class TestAnalyze:
    def test_the_chain_from_details_to_persisted_counts(self, tmp_path):
        module = tmp_path / "workload"
        module.write_bytes(b"\x7fELF")
        spot = _hotspot(str(module))
        executor = (
            ScriptedExecutor()
            .on("objdump", stdout=OBJDUMP_VERSION)
            .on("readelf", stdout=GNU_READELF_WORKLOAD_VEC)
            .on("objdump", stdout=DIS_AXPY_SCALAR)
        )
        analyses, degradations = loops.analyze(
            executor, Config(), [_detail(spot, 0x1385, 90.0)], floor_samples=100
        )
        assert degradations == []
        (analysis,) = analyses
        assert (analysis.start_offset, analysis.end_offset) == (0x1380, 0x139A)
        assert analysis.scalar_fp == 2
        assert analysis.flops_per_iteration == 2.0
        assert analysis.loaded_bytes == 16 and analysis.stored_bytes == 8
        disassemble = executor.calls[-1]
        assert disassemble[0] == "objdump"
        assert "--start-address=0x1360" in disassemble
        assert "--stop-address=0x1406" in disassemble

    def test_an_absent_module_skips_the_analysis_whole(self):
        spot = _hotspot("/nonexistent/workload")
        executor = ScriptedExecutor()
        analyses, degradations = loops.analyze(
            executor, Config(), [_detail(spot, 0x1385, 90.0)], floor_samples=100
        )
        assert (analyses, degradations) == ([], [])
        assert executor.calls == []

    def test_below_the_floor_nothing_is_disassembled(self, tmp_path):
        module = tmp_path / "workload"
        module.write_bytes(b"\x7fELF")
        spot = _hotspot(str(module))
        executor = ScriptedExecutor()
        analyses, _ = loops.analyze(
            executor, Config(), [_detail(spot, 0x1385, 90.0, samples=3)],
            floor_samples=100,
        )
        assert analyses == [] and executor.calls == []

    def test_no_gnu_objdump_is_the_declared_loss(self, tmp_path):
        module = tmp_path / "workload"
        module.write_bytes(b"\x7fELF")
        executor = ScriptedExecutor().on("objdump", exit_code=127)
        analyses, (degradation,) = loops.analyze(
            executor, Config(), [_detail(_hotspot(str(module)), 0x1385, 90.0)],
            floor_samples=100,
        )
        assert analyses == []
        assert degradation.name == "loop-analysis-unavailable"
