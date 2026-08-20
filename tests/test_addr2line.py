"""The addr2line fallback: same contract as LLVM, extent rule enforced.

Fixtures are verbatim Binutils 2.44 outputs from the EPYC runner. The
decisive case is the gap: GNU addr2line names an address two bytes past
`main`'s extent after `main` itself, with output indistinguishable from
a legitimate hit in a binary compiled without `-g` - only the symbol
table tells them apart, so the fallback reads it first.
"""

from nunatak.attribution import attribute, locate_any
from nunatak.attribution.addr2line import Addr2Line, locate
from nunatak.cli import doctor
from nunatak.config import Config
from nunatak.ingestion import measurements_from_samples
from nunatak.ingestion.samples import Sample
from nunatak.pivot import ResolutionLevel
from tests.support import (
    ADDR2LINE_DEBUG,
    ADDR2LINE_MISSING_STDERR,
    ADDR2LINE_NODBG,
    ADDR2LINE_STRIPPED,
    ADDR2LINE_VERSION,
    GNU_READELF_S_FP,
    GNU_READELF_SYMBOLS_FP,
    GNU_READELF_SYMBOLS_NODBG,
    GNU_READELF_SYMBOLS_STRIPPED,
    LLVM_ADDR2LINE_VERSION,
    ScriptedExecutor,
)

TOOL = Addr2Line(path="/usr/bin/addr2line", version="2.44")


class TestLocate:
    def test_the_first_gnu_addr2line_answers(self):
        executor = ScriptedExecutor().on("addr2line", stdout=ADDR2LINE_VERSION)
        found = locate(executor, Config(tools={"addr2line": "/usr/bin/addr2line"}))
        assert found == TOOL

    def test_a_non_gnu_claimant_is_not_trusted(self):
        # llvm-addr2line answers with an LLVM banner: the parser and the
        # extent workaround are vetted against GNU output only.
        executor = ScriptedExecutor().on("addr2line", stdout=LLVM_ADDR2LINE_VERSION)
        assert locate(executor, Config(tools={"addr2line": "/x/addr2line"})) is None

    def test_readelf_is_the_sibling_of_the_located_tool(self):
        assert TOOL.readelf == "/usr/bin/readelf"
        assert Addr2Line(path="addr2line", version="2.44").readelf == "readelf"

    def test_no_dwarfdump_no_fingerprints(self):
        assert TOOL.dwarfdump is None


class TestSymbolize:
    def _outcome(self, symbols, output):
        executor = (
            ScriptedExecutor()
            .on("readelf", stdout=symbols)
            .on("addr2line", stdout=output)
        )
        return executor, TOOL.symbolize(
            executor, "/tmp/workload", [0x11B8, 0x10C4, 0x2000, 0x11FA]
        )

    def test_chains_come_back_innermost_first_with_the_anchor(self):
        _, outcome = self._outcome(GNU_READELF_SYMBOLS_FP, ADDR2LINE_DEBUG)
        chain = outcome.chains[0x11B8]
        assert [f.function for f in chain.frames] == ["reduce", "main"]
        assert chain.frames[0].line == 10
        assert chain.physical.start_address == 0x10C0
        assert chain.resolution_level is ResolutionLevel.LINE

    def test_the_discriminator_suffix_is_not_part_of_the_line(self):
        _, outcome = self._outcome(GNU_READELF_SYMBOLS_FP, ADDR2LINE_DEBUG)
        assert outcome.chains[0x11B8].frames[0].file == (
            "/tmp/nunatak-stack-ladder/workload.c"
        )

    def test_the_gap_stays_unresolved_despite_the_tools_answer(self):
        # addr2line said `main` for 0x11fa; main's extent ends at 0x11f8.
        _, outcome = self._outcome(GNU_READELF_SYMBOLS_FP, ADDR2LINE_DEBUG)
        assert 0x11FA not in outcome.chains
        assert 0x2000 not in outcome.chains

    def test_a_bare_name_inside_the_extent_is_kept(self):
        executor = (
            ScriptedExecutor()
            .on("readelf", stdout=GNU_READELF_SYMBOLS_NODBG)
            .on("addr2line", stdout=ADDR2LINE_NODBG)
        )
        outcome = TOOL.symbolize(executor, "/tmp/workload-nodbg", [0x10C8])
        chain = outcome.chains[0x10C8]
        assert chain.physical.function == "main"
        assert chain.physical.file is None
        assert chain.resolution_level is ResolutionLevel.FUNCTION

    def test_a_dynsym_only_module_still_carries_extents(self):
        executor = (
            ScriptedExecutor()
            .on("readelf", stdout=GNU_READELF_SYMBOLS_STRIPPED)
            .on("addr2line", stdout=ADDR2LINE_STRIPPED)
        )
        outcome = TOOL.symbolize(executor, "/tmp/libwork.so", [0x1109, 0x1200])
        assert outcome.chains[0x1109].physical.function == "work_axpy"
        assert outcome.chains[0x1109].physical.start_address == 0x1100
        assert 0x1200 not in outcome.chains

    def test_an_unreadable_symbol_table_refuses_to_symbolize_on_trust(self):
        executor = ScriptedExecutor().on("readelf", exit_code=1)
        outcome = TOOL.symbolize(executor, "/gone.so", [0x10])
        assert outcome.chains == {}
        assert "extent rule" in outcome.error

    def test_a_missing_module_reports_the_tools_words(self):
        executor = (
            ScriptedExecutor()
            .on("readelf", stdout=GNU_READELF_SYMBOLS_FP)
            .on("addr2line", stderr=ADDR2LINE_MISSING_STDERR, exit_code=1)
        )
        outcome = TOOL.symbolize(executor, "/nonexistent.so", [0x10])
        assert "No such file" in outcome.error


class TestFallbackInTheChain:
    def _measurements(self):
        samples = [
            Sample(pid=1, tid=1, time_s=1.0, period=1000, counter="task-clock",
                   module="/tmp/workload", offset=0x11B8),
            Sample(pid=1, tid=1, time_s=1.1, period=1000, counter="task-clock",
                   module="/tmp/workload", offset=0x11FA),
        ]
        return measurements_from_samples(samples, {"/tmp/workload": "deadbeef"}, "n0")

    def test_attribute_names_through_the_fallback(self):
        executor = (
            ScriptedExecutor()
            .on("readelf", stdout=GNU_READELF_SYMBOLS_FP)
            .on("addr2line", stdout=ADDR2LINE_DEBUG)
        )
        named, details, degradations = attribute(self._measurements(), TOOL, executor)
        assert degradations == []
        by_name = {m.hotspot.display_name: m for m in named}
        assert "main" in by_name
        assert by_name["main"].hotspot.resolution_level is ResolutionLevel.LINE
        # The anchor came from the symbol table: physical identity holds.
        assert by_name["main"].hotspot.physical_identity.offset == 0x10C0
        # The gap hit stayed unresolved, displayed module+offset.
        assert "workload+0x11fa" in by_name
        assert details

    def test_locate_any_prefers_llvm_and_never_probes_the_fallback(self):
        executor = ScriptedExecutor().on(
            "llvm-symbolizer", stdout="LLVM version 19.1.7\n"
        )
        found = locate_any(
            executor, Config(tools={"llvm-symbolizer": "/x/llvm-symbolizer"})
        )
        assert found.major == 19
        assert all(call[0] != "addr2line" for call in executor.calls)

    def test_locate_any_falls_back_when_llvm_is_absent(self):
        executor = (
            ScriptedExecutor()
            .on("llvm-symbolizer", exit_code=127)
            .on("addr2line", stdout=ADDR2LINE_VERSION)
        )
        config = Config(
            tools={"llvm-symbolizer": "/x/llvm-symbolizer", "addr2line": "/x/addr2line"}
        )
        assert isinstance(locate_any(executor, config), Addr2Line)


class TestDoctorVerdict:
    def test_the_fallback_is_declared_second_choice(self):
        check = doctor._llvm(TOOL)
        assert (check.name, check.status) == ("llvm", "warning")
        assert check.degradation.name == "llvm-missing"
        assert "addr2line 2.44" in check.detail

    def test_gnu_readelf_sections_feed_the_attribution_ceiling(self):
        from nunatak.attribution import inspection

        executor = ScriptedExecutor().on("readelf", stdout=GNU_READELF_S_FP)
        sections = inspection.inspect(executor, "readelf", "/tmp/workload")
        assert sections.debug_info and sections.symtab and sections.dynsym
