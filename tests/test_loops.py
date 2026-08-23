"""Static loop analysis: the hot inner loop, counted from real code.

Fixtures are verbatim objdump outputs of four real loops built on the
EPYC: scalar, SSE, AVX2+FMA and an intrinsics gather - the counts below
are exact per-iteration truths of that machine code, checked by hand.
"""

from pathlib import Path

import pytest

from nunatak.attribution import loops

FIXTURES = Path(__file__).resolve().parent / "fixtures"
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


class TestCycleBounds:
    """llvm-mca's two verdicts against real reports from the EPYC: what
    the ports allow, and what the simulated steady state reaches - the
    gather loop's gap between the two is the dependency chain speaking."""

    def test_the_port_and_steady_state_bounds_are_read(self):
        from tests.support import MCA_AVX2

        ports, effective = loops.parse_mca(MCA_AVX2)
        assert ports == 1.3
        assert effective == pytest.approx(1.41)

    def test_the_gather_loop_is_dependency_bound(self):
        from tests.support import MCA_GATHER

        ports, effective = loops.parse_mca(MCA_GATHER)
        assert ports == 1.8
        assert effective == pytest.approx(103.12)

    def test_a_report_without_the_numbers_is_none(self):
        assert loops.parse_mca("no report here") is None

    def test_known_cpus_come_from_the_tools_own_list(self):
        from tests.support import MCA_MCPU_HELP

        executor = ScriptedExecutor().on("llvm-mca", stdout=MCA_MCPU_HELP)
        cpus = loops._known_cpus(executor, "/usr/lib/llvm-19/bin/llvm-mca")
        assert "znver2" in cpus and "skylake" in cpus
        assert "made-up-cpu" not in cpus

    def test_the_fallback_symbolizer_offers_no_model(self):
        from nunatak.attribution.addr2line import Addr2Line

        assert loops._mca_path(Addr2Line(path="/usr/bin/addr2line", version="2.44")) is None
        assert loops._mca_path(None) is None

    def test_an_unknown_mcpu_is_the_upgrade_reason(self, tmp_path):
        from nunatak.attribution.symbolizer import Symbolizer
        from tests.support import MCA_MCPU_HELP

        module = tmp_path / "workload"
        module.write_bytes(b"\x7fELF")
        spot = _hotspot(str(module))
        executor = (
            ScriptedExecutor()
            .on("objdump", stdout=OBJDUMP_VERSION)
            .on("llvm-mca", stdout=MCA_MCPU_HELP)
            .on("readelf", stdout=GNU_READELF_WORKLOAD_VEC)
            .on("objdump", stdout=DIS_AXPY_SCALAR)
        )
        (analysis,) = loops.analyze(
            executor, Config(), [_detail(spot, 0x1385, 90.0)],
            floor_samples=100,
            symbolizer=Symbolizer(path="/usr/lib/llvm-19/bin/llvm-symbolizer", major=19),
            microarchitecture="zen5-imaginary",
            directory=tmp_path,
        )[0]
        assert analysis.cycles_ports is None
        assert "no scheduling model to pick" in analysis.bounds_reason

    def test_the_full_chain_writes_the_listing_and_reads_the_bounds(self, tmp_path):
        from nunatak.attribution.symbolizer import Symbolizer
        from tests.support import MCA_MCPU_HELP, MCA_SCALAR

        module = tmp_path / "workload"
        module.write_bytes(b"\x7fELF")
        spot = _hotspot(str(module))
        executor = (
            ScriptedExecutor()
            .on("objdump", stdout=OBJDUMP_VERSION)
            .on("llvm-mca", stdout=MCA_MCPU_HELP)
            .on("readelf", stdout=GNU_READELF_WORKLOAD_VEC)
            .on("objdump", stdout=DIS_AXPY_SCALAR)
            .on("llvm-mca", stdout=MCA_SCALAR)
        )
        (analysis,) = loops.analyze(
            executor, Config(), [_detail(spot, 0x1385, 90.0)],
            floor_samples=100,
            symbolizer=Symbolizer(path="/usr/lib/llvm-19/bin/llvm-symbolizer", major=19),
            microarchitecture="zen2",
            directory=tmp_path,
        )[0]
        assert analysis.scheduling_model == "znver2"
        assert analysis.cycles_ports == 1.5
        assert analysis.cycles_effective == pytest.approx(1.71)
        listing = tmp_path / "loops" / "0.s"
        assert listing.is_file()
        assert "mulsd %xmm1,%xmm0" in listing.read_text()
        assert "jne" not in listing.read_text()


class TestMachoArm64Flavor:
    """The Darwin flavor against verbatim Xcode llvm-objdump output from
    an Apple M5 Max: the NEON triad loop (`fmla.2d`, Apple's
    mnemonic-suffix dialect) and its scalar sibling built with
    vectorization off (`fmadd d`)."""

    NEON = (FIXTURES / "objdump-macho-axpy-neon.txt").read_text()
    SCALAR = (FIXTURES / "objdump-macho-axpy-scalar.txt").read_text()
    BASE = 0x100000000

    def test_rows_are_rebased_and_stripped_of_annotations(self):
        rows = loops.parse_arm64(self.NEON, self.BASE)
        assert rows[0].offset == 0x4B0
        branch = next(r for r in rows if r.mnemonic.startswith("b."))
        assert "<" not in branch.operands

    def test_the_backward_branch_draws_the_loop(self):
        rows = loops.parse_arm64(self.NEON, self.BASE)
        found = loops.loops_arm64(rows, self.BASE)
        assert any(loop.start == 0x4EC and loop.end == 0x518 for loop in found)
        # The forward b.lt at the top draws nothing.
        assert all(loop.end > loop.start for loop in found)

    def test_the_neon_fmla_loop_counts_exactly(self):
        rows = loops.parse_arm64(self.NEON, self.BASE)
        outcome = loops.analyze_function_arm64(
            self.NEON, {0x4FC: 100.0}, self.BASE
        )
        assert outcome is not None
        loop, counts = outcome
        assert (loop.start, loop.end) == (0x4EC, 0x518)
        # Four fmla.2d: 2 lanes x 2 (an FMA counts two) each; four
        # ldp q (32 B) in, two stp q out.
        assert counts["flops"] == 16.0
        assert counts["vector_fp"] == 4 and counts["scalar_fp"] == 0
        assert counts["vector_width_bits"] == 128
        assert counts["loaded_bytes"] == 128
        assert counts["stored_bytes"] == 64
        assert counts["gathers"] == 0

    def test_the_scalar_fmadd_loop_counts_exactly(self):
        outcome = loops.analyze_function_arm64(
            self.SCALAR, {0x4C4: 10.0}, self.BASE
        )
        loop, counts = outcome
        assert (loop.start, loop.end) == (0x4BC, 0x4D0)
        assert counts["flops"] == 2.0
        assert counts["vector_fp"] == 0 and counts["scalar_fp"] == 1
        assert counts["vector_width_bits"] is None
        assert counts["loaded_bytes"] == 16
        assert counts["stored_bytes"] == 8

    def test_weights_outside_every_loop_yield_nothing(self):
        assert (
            loops.analyze_function_arm64(self.NEON, {0x4B0: 5.0}, self.BASE)
            is None
        )

    def test_calls_never_draw_loops(self):
        text = (
            "0000000100000400 <_f>:\n"
            "100000400: 94000000\tbl\t0x100000300 <_g>\n"
            "100000404: d65f03c0\tret\n"
        )
        rows = loops.parse_arm64(text, self.BASE)
        assert loops.loops_arm64(rows, self.BASE) == []

    def test_the_darwin_objdump_gate_needs_the_llvm_banner(self):
        from tests.support import ScriptedExecutor
        from nunatak.config import Config

        apple = ScriptedExecutor(system="Darwin").on(
            "objdump", stdout="Apple LLVM version 21.0.0\n  Optimized build.\n"
        )
        assert loops._darwin_objdump(apple, Config())[1] == "21.0.0"
        gnu = ScriptedExecutor(system="Darwin").on(
            "objdump", stdout="GNU objdump (GNU Binutils) 2.44\n"
        )
        assert loops._darwin_objdump(gnu, Config())[1] is None
