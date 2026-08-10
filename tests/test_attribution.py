"""Symbolizer driver, exercised against genuine llvm-symbolizer output.

Every fixture below is the verbatim stdout of llvm-symbolizer 19.1.7
(Ubuntu 25.04, x86_64) invoked with `--output-style=JSON --obj=...` on a
workload compiled with `gcc -O2 -g` (variants: without `-g`, stripped):
these tests exercise the parser against real tool output, never against
our idea of it.
"""

from nunatak.attribution import AttributionChain, Frame, Symbolizer, locate
from nunatak.config import Config
from nunatak.pivot import ResolutionLevel
from tests.support import ScriptedExecutor

SYMBOLIZER = Symbolizer(path="/usr/lib/llvm-19/bin/llvm-symbolizer", major=19)

# gcc -O2 inlined axpy_element into reduce, and reduce into main: one
# address carries the whole chain, innermost first.
INLINE_CHAIN = (
    '[{"Address":"0x1160","ModuleName":"workload","Symbol":[{"Column":14,'
    '"Discriminator":0,"FileName":"/tmp/symshapes/workload.c","FunctionName":'
    '"axpy_element","Line":5,"StartAddress":"","StartFileName":"","StartLine":4},'
    '{"Column":14,"Discriminator":0,"FileName":"/tmp/symshapes/workload.c",'
    '"FunctionName":"reduce","Line":11,"StartAddress":"","StartFileName":"",'
    '"StartLine":8},{"Column":40,"Discriminator":0,"FileName":'
    '"/tmp/symshapes/workload.c","FunctionName":"main","Line":20,"StartAddress":'
    '"0x10c0","StartFileName":"/tmp/symshapes/workload.c","StartLine":15}]}]'
)

# One invocation, several addresses: a single array with one entry each.
BATCH = (
    '[{"Address":"0x10c0","ModuleName":"workload","Symbol":[{"Column":16,'
    '"Discriminator":0,"FileName":"/tmp/symshapes/workload.c","FunctionName":'
    '"main","Line":15,"StartAddress":"0x10c0","StartFileName":'
    '"/tmp/symshapes/workload.c","StartLine":15}]},{"Address":"0x10e8",'
    '"ModuleName":"workload","Symbol":[{"Column":17,"Discriminator":0,'
    '"FileName":"/tmp/symshapes/workload.c","FunctionName":"main","Line":17,'
    '"StartAddress":"0x10c0","StartFileName":"/tmp/symshapes/workload.c",'
    '"StartLine":15}]},{"Address":"0x10f0","ModuleName":"workload","Symbol":'
    '[{"Column":23,"Discriminator":1,"FileName":"/tmp/symshapes/workload.c",'
    '"FunctionName":"main","Line":18,"StartAddress":"0x10c0","StartFileName":'
    '"/tmp/symshapes/workload.c","StartLine":15}]}]'
)

# The same binary compiled without -g: .symtab names the function, no file.
NO_DEBUG = (
    '[{"Address":"0x10c0","ModuleName":"workload-nodebug","Symbol":[{"Column":0,'
    '"Discriminator":0,"FileName":"","FunctionName":"main","Line":0,'
    '"StartAddress":"0x10c0","StartFileName":"","StartLine":0}]}]'
)

# An address in a gap between symbols: the tool answers an empty record
# rather than the neighbouring symbol - the extent rule at work.
GAP = (
    '[{"Address":"0x2","ModuleName":"workload","Symbol":[{"Column":0,'
    '"Discriminator":0,"FileName":"","FunctionName":"","Line":0,'
    '"StartAddress":"","StartFileName":"","StartLine":0}]}]'
)

# Unreadable modules answer a single bare object (no array) and exit 1.
MISSING_MODULE = (
    '{"Address":"0x0","Error":{"Message":"No such file or directory"},'
    '"ModuleName":"/tmp/symshapes/nope"}'
)
NOT_AN_OBJECT = (
    '{"Address":"0x0","Error":{"Message":"The file was not recognized as a '
    'valid object file"},"ModuleName":"workload.c"}'
)

# Demangling is the tool's default: C++ names arrive readable.
CXX = (
    '[{"Address":"0x0","ModuleName":"cxx.o","Symbol":[{"Column":45,'
    '"Discriminator":0,"FileName":"/tmp/symshapes/cxx.cpp","FunctionName":'
    '"ns::fn(int)","Line":1,"StartAddress":"0x0","StartFileName":'
    '"/tmp/symshapes/cxx.cpp","StartLine":1}]}]'
)

VERSION = "llvm-symbolizer\nUbuntu LLVM version 19.1.7\n  Optimized build.\n"


def symbolize(stdout, offsets, exit_code=0, stderr=""):
    executor = ScriptedExecutor().on(
        "llvm-symbolizer", stdout=stdout, stderr=stderr, exit_code=exit_code
    )
    outcome = SYMBOLIZER.symbolize(executor, "workload", offsets)
    return outcome, executor


class TestChains:
    def test_inline_chain_is_innermost_first_with_the_physical_function_last(self):
        outcome, _ = symbolize(INLINE_CHAIN, [0x1160])
        chain = outcome.chains[0x1160]
        assert [f.function for f in chain.frames] == ["axpy_element", "reduce", "main"]
        assert chain.physical.function == "main"
        assert chain.physical.line == 20
        assert chain.physical.declaration_line == 15
        assert chain.physical.start_address == 0x10C0
        assert chain.frames[0].file == "/tmp/symshapes/workload.c"
        assert chain.frames[0].line == 5
        assert chain.frames[0].start_address is None

    def test_a_chain_with_source_positions_reaches_line_level(self):
        outcome, _ = symbolize(INLINE_CHAIN, [0x1160])
        assert outcome.chains[0x1160].resolution_level is ResolutionLevel.LINE

    def test_batched_addresses_come_back_keyed_by_offset(self):
        outcome, _ = symbolize(BATCH, [0x10C0, 0x10E8, 0x10F0])
        assert set(outcome.chains) == {0x10C0, 0x10E8, 0x10F0}
        assert outcome.chains[0x10E8].physical.line == 17
        assert outcome.error is None

    def test_without_debug_information_the_symtab_name_gives_function_level(self):
        outcome, _ = symbolize(NO_DEBUG, [0x10C0])
        chain = outcome.chains[0x10C0]
        assert chain.resolution_level is ResolutionLevel.FUNCTION
        assert chain.physical == Frame(function="main", start_address=0x10C0)

    def test_a_gap_address_yields_an_empty_chain_never_the_neighbour(self):
        outcome, _ = symbolize(GAP, [0x2])
        chain = outcome.chains[0x2]
        assert chain.frames == ()
        assert chain.physical is None
        assert chain.resolution_level is ResolutionLevel.UNRESOLVED

    def test_demangled_names_arrive_as_the_tool_prints_them(self):
        outcome, _ = symbolize(CXX, [0x0])
        assert outcome.chains[0x0].physical.function == "ns::fn(int)"


class TestErrors:
    def test_a_missing_module_reports_the_reason_and_no_chains(self):
        outcome, _ = symbolize(MISSING_MODULE, [0x10], exit_code=1)
        assert outcome.chains == {}
        assert outcome.error == "No such file or directory"

    def test_a_non_object_file_reports_the_reason(self):
        outcome, _ = symbolize(NOT_AN_OBJECT, [0x10], exit_code=1)
        assert outcome.error == "The file was not recognized as a valid object file"

    def test_no_output_at_all_falls_back_to_stderr_then_exit_code(self):
        outcome, _ = symbolize("", [0x10], exit_code=127, stderr="not found")
        assert outcome.error == "not found"
        outcome, _ = symbolize("", [0x10], exit_code=1)
        assert outcome.error == "llvm-symbolizer exited with 1"

    def test_unrecognized_output_is_declared_not_guessed(self):
        outcome, _ = symbolize("segfault gibberish", [0x10])
        assert outcome.chains == {}
        assert "unrecognized llvm-symbolizer output" in outcome.error


class TestInvocation:
    def test_addresses_are_deduplicated_sorted_and_hexadecimal(self):
        _, executor = symbolize(BATCH, [0x10F0, 0x10C0, 0x10E8, 0x10C0])
        (argv,) = executor.calls
        assert argv[:3] == [
            SYMBOLIZER.path,
            "--output-style=JSON",
            "--obj=workload",
        ]
        assert argv[3:] == ["0x10c0", "0x10e8", "0x10f0"]


class TestLocate:
    def test_the_configured_path_is_probed_first_and_wins(self):
        executor = ScriptedExecutor().on("llvm-symbolizer", stdout=VERSION)
        config = Config(tools={"llvm-symbolizer": "/site/llvm/bin/llvm-symbolizer"})
        symbolizer = locate(executor, config)
        assert symbolizer == Symbolizer(
            path="/site/llvm/bin/llvm-symbolizer", major=19
        )
        assert executor.calls[0] == ["/site/llvm/bin/llvm-symbolizer", "--version"]

    def test_a_failing_candidate_is_skipped_for_the_next_one(self):
        executor = (
            ScriptedExecutor()
            .on("llvm-symbolizer", stderr="not found", exit_code=127)
            .on("llvm-symbolizer", stdout=VERSION)
        )
        config = Config(tools={"llvm-symbolizer": "/gone/llvm-symbolizer"})
        symbolizer = locate(executor, config)
        assert symbolizer is not None
        assert symbolizer.major == 19
        assert symbolizer.path == executor.calls[1][0]
        assert symbolizer.path != "/gone/llvm-symbolizer"

    def test_no_usable_candidate_returns_none(self):
        executor = ScriptedExecutor().on(
            "llvm-symbolizer", stderr="not found", exit_code=127
        )
        assert locate(executor, Config()) is None

    def test_unparseable_version_output_is_not_trusted(self):
        executor = (
            ScriptedExecutor()
            .on("llvm-symbolizer", stdout="mystery tool 1.0")
            .on("llvm-symbolizer", stdout=VERSION)
        )
        config = Config(tools={"llvm-symbolizer": "/odd/llvm-symbolizer"})
        symbolizer = locate(executor, config)
        assert symbolizer is not None
        assert symbolizer.path != "/odd/llvm-symbolizer"
