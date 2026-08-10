"""Symbolizer driver, exercised against genuine llvm-symbolizer output.

Every fixture below is the verbatim stdout of llvm-symbolizer 19.1.7
(Ubuntu 25.04, x86_64) invoked with `--output-style=JSON --obj=...` on a
workload compiled with `gcc -O2 -g` (variants: without `-g`, stripped):
these tests exercise the parser against real tool output, never against
our idea of it. The end of the file replays a corpus entry recorded on
the same machine through the whole `run` pipeline.
"""

import json
from pathlib import Path

import pytest

from nunatak.attribution import AttributionChain, Frame, Symbolizer, attribute, locate
from nunatak.cli import principal
from nunatak.config import Config
from nunatak.pivot import (
    Hotspot,
    LogicalIdentity,
    Locus,
    Measurement,
    PhysicalIdentity,
    Quality,
    ResolutionLevel,
    read_run,
)
from tests.support import ScriptedExecutor

CORPUS = (
    Path(__file__).resolve().parent.parent
    / "corpus"
    / "recordings"
    / "perf"
    / "6.14.11"
    / "linux-x86_64"
    / "workload-c-debug"
)
WORKLOAD_BUILDID = "4ce402d2f4f91e424538da7cbab70af0d8100e4e"

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


def unresolved(module, offset, value, tid=1, module_id="deadbeef", samples=None):
    physical = (
        PhysicalIdentity(module_id=module_id, offset=offset) if module_id else None
    )
    return Measurement(
        hotspot=Hotspot(
            logical_identity=LogicalIdentity(module=module),
            resolution_level=ResolutionLevel.UNRESOLVED,
            physical_identity=physical,
            offset=offset,
        ),
        locus=Locus(node="n1", thread=tid),
        counter="cycles",
        value=value,
        unit="cycles",
        quality=Quality.MEASURED,
        sample_count=samples,
    )


class TestAttribute:
    def test_sampled_addresses_of_one_function_fuse_into_one_named_hotspot(self):
        measurements = [
            unresolved("/tmp/workload", 0x10C0, 30.0, samples=3),
            unresolved("/tmp/workload", 0x10E8, 50.0, samples=5),
            unresolved("/tmp/workload", 0x10F0, 20.0, samples=2),
        ]
        executor = ScriptedExecutor().on("llvm-symbolizer", stdout=BATCH)
        attributed, degradations = attribute(measurements, SYMBOLIZER, executor)
        assert degradations == []
        (merged,) = attributed
        assert merged.hotspot.display_name == "main"
        assert merged.hotspot.logical_identity.source_file == "/tmp/symshapes/workload.c"
        assert merged.hotspot.resolution_level is ResolutionLevel.LINE
        assert merged.hotspot.physical_identity == PhysicalIdentity("deadbeef", 0x10C0)
        assert merged.hotspot.offset is None
        assert merged.value == 100.0
        assert merged.sample_count == 10

    def test_loci_stay_apart_when_their_hotspot_fuses(self):
        measurements = [
            unresolved("/tmp/workload", 0x10C0, 30.0, tid=1),
            unresolved("/tmp/workload", 0x10E8, 50.0, tid=2),
        ]
        executor = ScriptedExecutor().on("llvm-symbolizer", stdout=BATCH)
        attributed, _ = attribute(measurements, SYMBOLIZER, executor)
        assert len(attributed) == 2
        assert len({m.hotspot for m in attributed}) == 1
        assert {m.locus.thread for m in attributed} == {1, 2}
        (argv,) = executor.calls
        assert argv[3:] == ["0x10c0", "0x10e8"]

    def test_without_a_symbolizer_measurements_come_back_untouched(self):
        measurements = [unresolved("/tmp/workload", 0x10C0, 30.0)]
        executor = ScriptedExecutor()
        attributed, degradations = attribute(measurements, None, executor)
        assert attributed == measurements
        assert degradations == []
        assert executor.calls == []

    def test_pseudo_modules_are_never_symbolized(self):
        measurements = [
            unresolved("/proc/kcore", 0x800081359684, 2.0, module_id=None),
            unresolved("[vdso]", 0x9A0, 1.0, module_id=None),
        ]
        executor = ScriptedExecutor()
        attributed, degradations = attribute(measurements, SYMBOLIZER, executor)
        assert executor.calls == []
        assert degradations == []
        assert all(
            m.hotspot.resolution_level is ResolutionLevel.UNRESOLVED
            for m in attributed
        )

    def test_an_unreadable_module_stays_unresolved_and_says_why(self):
        measurements = [unresolved("/gone/lib.so", 0x10, 5.0)]
        executor = ScriptedExecutor().on(
            "llvm-symbolizer", stdout=MISSING_MODULE, exit_code=1
        )
        attributed, (degradation,) = attribute(measurements, SYMBOLIZER, executor)
        assert attributed == measurements
        assert degradation.name == "symbolization-failed"
        assert "No such file or directory" in degradation.message
        assert "/gone/lib.so" in degradation.message

    def test_a_gap_address_stays_unresolved_with_its_honest_display(self):
        measurements = [unresolved("/tmp/workload", 0x2, 1.0)]
        executor = ScriptedExecutor().on("llvm-symbolizer", stdout=GAP)
        (measurement,), degradations = attribute(measurements, SYMBOLIZER, executor)
        assert degradations == []
        assert measurement.hotspot.resolution_level is ResolutionLevel.UNRESOLVED
        assert measurement.hotspot.display_name == "workload+0x2"


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


class TestReplayedAttribution:
    """The whole `run` pipeline against the recorded corpus entry: perf and
    llvm-symbolizer replayed from a machine that had both (AMD EPYC,
    Ubuntu 25.04, workload compiled `gcc -O2 -g`)."""

    @pytest.fixture(autouse=True)
    def in_tmp_cwd(self, tmp_path, monkeypatch):
        # The pinned symbolizer path keeps the candidate list identical
        # between the recording machine and any replaying one.
        (tmp_path / "nunatak.toml").write_text(
            '[tools]\nllvm-symbolizer = "/usr/lib/llvm-19/bin/llvm-symbolizer"\n'
        )
        monkeypatch.chdir(tmp_path)

    def test_the_replayed_run_carries_named_hotspots(self, capsys):
        assert principal(["run", "--replay", str(CORPUS), "--json", "--", "./workload"]) == 0
        summary = json.loads(capsys.readouterr().out)
        assert summary["degradations"] == []
        assert summary["hotspots"] == 4
        assert summary["resolved_hotspots"] == 3

        run = read_run(summary["run"])
        (main,) = {
            m.hotspot
            for m in run.measurements
            if m.hotspot.display_name == "main"
        }
        assert main.resolution_level is ResolutionLevel.LINE
        assert main.logical_identity.source_file == "/tmp/nunatak-capture-debug/workload.c"
        assert main.physical_identity == PhysicalIdentity(WORKLOAD_BUILDID, 0x10C0)
        assert main.offset is None

    def test_naming_and_fusing_lose_no_measured_value(self, capsys):
        # 204 samples landed on two addresses of one function: the fused
        # Measurement carries their sum, and the Run total is unchanged.
        assert principal(["run", "--replay", str(CORPUS), "--json", "--", "./workload"]) == 0
        summary = json.loads(capsys.readouterr().out)
        run = read_run(summary["run"])

        (fused,) = [m for m in run.measurements if m.hotspot.display_name == "main"]
        assert fused.sample_count == 204

        script = next(
            record.with_suffix(".stdout").read_text()
            for record in sorted((CORPUS / "invocations").glob("*.json"))
            if json.loads(record.read_text())["argv"][:2] == ["perf", "script"]
        )
        from nunatak.ingestion.perf_script import parse_samples

        samples, _ = parse_samples(script)
        assert sum(m.value for m in run.measurements) == sum(s.period for s in samples)

    def test_kernel_samples_stay_honestly_unresolved(self, capsys):
        assert principal(["run", "--replay", str(CORPUS), "--json", "--", "./workload"]) == 0
        summary = json.loads(capsys.readouterr().out)
        run = read_run(summary["run"])
        unresolved = [
            m.hotspot
            for m in run.measurements
            if m.hotspot.resolution_level is ResolutionLevel.UNRESOLVED
        ]
        assert unresolved
        assert all(h.logical_identity.name is None for h in unresolved)
