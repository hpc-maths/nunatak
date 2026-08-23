"""The atos fallback: macOS symbolization at the addr2line contract.

Fixtures are verbatim tool output from an Apple M5 Max on macOS 26.5.2:
`atos -i -offset` blocks (blank-line separated, innermost first) over
binaries built `cc -O2 -g`, and `nm -n` symbol tables whose Mach-O
header row names the module's base.
"""

import pytest

from nunatak.attribution import locate_any
from nunatak.attribution.atos import Atos, _symbol_starts, locate
from nunatak.cli import doctor
from nunatak.config import Config
from nunatak.pivot import ResolutionLevel
from tests.support import ScriptedExecutor

TOOL = Atos(path="/usr/bin/atos", version="macOS 26.5.2")

USAGE = "[invalid usage]: no processes or executables specified"

NM = """\
                 U _free
                 U _malloc
                 U _printf
0000000100000000 T __mh_execute_header
00000001000004b0 T _axpy
0000000100000558 T _main
                 U dyld_stub_binder
"""

# atos -o triad -i -offset 0x514 0x630 0x2000
ANSWERS = """\
axpy (in triad) (triad.c:5)

main (in triad) (triad.c:12)

0x0000000100002000 (in triad)
"""

# atos -o inlined -i -offset 0x5b0: an inline chain, innermost first.
INLINED = """\
poly (in inlined) (symbols.c:22)
axpy (in inlined) (symbols.c:32)
"""

# nm -n inlined: same source force-inlined, main further out.
NM_INLINED = """\
0000000100000000 T __mh_execute_header
00000001000004b0 T _axpy
000000010000063c T _main
"""

# atos -o nodebug -i -offset 0x514: no DWARF, the symbol-plus-offset form.
NODEBUG = "axpy (in nodebug) + 100\n"


def scripted(nm=NM, answers=ANSWERS):
    return (
        ScriptedExecutor(system="Darwin")
        .on("nm", stdout=nm)
        .on("atos", stdout=answers)
    )


class TestSymbolize:
    def test_batched_offsets_come_back_keyed_and_anchored(self):
        executor = scripted()
        outcome = TOOL.symbolize(executor, "/opt/triad", [0x630, 0x514, 0x2000])
        assert outcome.error is None
        axpy = outcome.chains[0x514]
        assert axpy.physical.function == "axpy"
        assert axpy.physical.file == "triad.c" and axpy.physical.line == 5
        # nm's file addresses minus the Mach-O header base anchor the
        # function-grain physical identity.
        assert axpy.physical.start_address == 0x4B0
        assert axpy.resolution_level is ResolutionLevel.LINE
        assert outcome.chains[0x630].physical.start_address == 0x558
        # The requested offsets ride the command line, deduplicated and
        # hexadecimal, after -offset.
        argv = executor.calls[1]
        assert argv[argv.index("-offset") + 1 :] == ["0x514", "0x630", "0x2000"]

    def test_a_bare_hex_answer_is_an_empty_chain_never_a_neighbour(self):
        outcome = TOOL.symbolize(scripted(), "/opt/triad", [0x514, 0x630, 0x2000])
        assert outcome.chains[0x2000].frames == ()
        assert outcome.chains[0x2000].resolution_level is ResolutionLevel.UNRESOLVED

    def test_an_inline_chain_arrives_innermost_first(self):
        executor = scripted(nm=NM_INLINED, answers=INLINED)
        outcome = TOOL.symbolize(executor, "/opt/inlined", [0x5B0])
        chain = outcome.chains[0x5B0]
        assert [frame.function for frame in chain.frames] == ["poly", "axpy"]
        assert chain.physical.function == "axpy"
        assert chain.physical.start_address == 0x4B0

    def test_without_debug_information_the_symbol_name_gives_function_level(
        self,
    ):
        outcome = TOOL.symbolize(scripted(answers=NODEBUG), "/opt/nodebug", [0x514])
        chain = outcome.chains[0x514]
        assert chain.physical.function == "axpy"
        assert chain.physical.file is None
        assert chain.resolution_level is ResolutionLevel.FUNCTION

    def test_an_unreadable_module_is_declared_not_guessed(self):
        executor = ScriptedExecutor(system="Darwin").on(
            "nm", stderr="no symbols", exit_code=1
        )
        outcome = TOOL.symbolize(executor, "/opt/gone", [0x10])
        assert outcome.error is not None and "nm" in outcome.error
        assert outcome.chains == {}

    def test_a_block_count_mismatch_is_an_error_not_a_shift(self):
        executor = scripted(answers="axpy (in triad) (triad.c:5)\n")
        outcome = TOOL.symbolize(executor, "/opt/triad", [0x514, 0x630])
        assert outcome.error is not None and "blocks" in outcome.error


class TestSymbolStarts:
    def test_the_header_row_sets_the_base(self):
        executor = ScriptedExecutor().on("nm", stdout=NM)
        assert _symbol_starts(executor, "/opt/triad") == [0x4B0, 0x558]

    def test_a_dylib_without_a_header_row_keeps_absolute_zero_base(self):
        text = "0000000000000fa0 T _work\n0000000000001000 T _other\n"
        executor = ScriptedExecutor().on("nm", stdout=text)
        assert _symbol_starts(executor, "/opt/lib.dylib") == [0xFA0, 0x1000]


class TestLocate:
    def test_the_platform_tool_answers_with_the_os_release(self):
        executor = (
            ScriptedExecutor(system="Darwin")
            .on("atos", stderr=USAGE, exit_code=1)
            .on("sw_vers", stdout="26.5.2\n")
        )
        located = locate(executor, Config())
        assert located == Atos(path=executor.calls[0][0], version="macOS 26.5.2")

    def test_an_impostor_is_refused(self):
        executor = ScriptedExecutor(system="Darwin").on("atos", stdout="hello")
        assert locate(executor, Config()) is None

    def test_locate_any_falls_back_to_atos_on_darwin_only(self):
        executor = (
            ScriptedExecutor(system="Darwin")
            .on("llvm-symbolizer", stderr="not found", exit_code=127)
            .on("atos", stderr=USAGE, exit_code=1)
            .on("sw_vers", stdout="26.5.2\n")
        )
        config = Config(tools={
            "llvm-symbolizer": "/gone/llvm-symbolizer", "atos": "/usr/bin/atos",
        })
        assert isinstance(locate_any(executor, config), Atos)


class TestDoctorVerdict:
    def test_atos_stands_in_with_the_degradation_named(self):
        check = doctor._llvm(TOOL)
        assert check.status == "warning"
        assert "atos macOS 26.5.2" in check.detail
        assert check.degradation.name == "llvm-missing"

    def test_no_attribution_ceiling_is_claimed_without_a_section_reader(
        self, tmp_path
    ):
        binary = tmp_path / "solver"
        binary.write_bytes(b"\x00")
        assert (
            doctor._attribution_ceiling(
                ScriptedExecutor(system="Darwin"), [str(binary)], TOOL
            )
            is None
        )
