"""The call-stack ladder: lbr > fp > none, decided cold.

The fixtures are verbatim GNU objdump and ldd outputs captured on the
EPYC 7702 runner (Binutils 2.44, Ubuntu 25.04): the workload compiled
with and without frame pointers, and the distribution's own libc - whose
8 largest functions keep the frame pointer in all but one prologue, a
real mixed-rate library.
"""

import sys
from pathlib import Path

from nunatak.cli import doctor
from nunatak.collect import stacks
from nunatak.config import Config
from tests.support import (
    LDD_WORKLOAD,
    LIBC_PROLOGUES,
    LLVM_OBJDUMP_VERSION,
    OBJDUMP_PROLOGUE_ARM_FP,
    OBJDUMP_PROLOGUE_ARM_NOFP,
    OBJDUMP_PROLOGUE_FP,
    OBJDUMP_PROLOGUE_NOFP,
    OBJDUMP_SYMTAB_FP,
    OBJDUMP_SYMTAB_LIBC,
    OBJDUMP_SYMTAB_NOFP,
    OBJDUMP_VERSION,
    ScriptedExecutor,
)

LIBC_DYNSYM = (Path(__file__).parent / "fixtures" / "objdump-dynsym-libc.txt").read_text()

INTEL = "Intel(R) Xeon(R) Platinum 8375C CPU @ 2.90GHz"
EPYC = "AMD EPYC 7702 64-Core Processor"


def _ladder_executor(symtab, prologue):
    """An executor scripted for a full decide(): the target described by
    `symtab`/`prologue`, then the libc dependency and its 8 prologues."""
    executor = ScriptedExecutor()
    executor.on("objdump", stdout=OBJDUMP_VERSION)
    executor.on("ldd", stdout=LDD_WORKLOAD)
    executor.on("objdump", stdout=symtab)
    executor.on("objdump", stdout=prologue)
    executor.on("objdump", stdout=OBJDUMP_SYMTAB_LIBC)
    executor.on("objdump", stdout=LIBC_DYNSYM)
    for disassembly in LIBC_PROLOGUES.values():
        executor.on("objdump", stdout=disassembly)
    return executor


class TestPrologues:
    def test_a_frame_pointer_prologue_is_recognized_on_x86_64(self):
        assert stacks._keeps_frame_pointer(OBJDUMP_PROLOGUE_FP) is True

    def test_an_omitted_frame_pointer_is_recognized_on_x86_64(self):
        assert stacks._keeps_frame_pointer(OBJDUMP_PROLOGUE_NOFP) is False

    def test_a_frame_pointer_prologue_is_recognized_on_aarch64(self):
        assert stacks._keeps_frame_pointer(OBJDUMP_PROLOGUE_ARM_FP) is True

    def test_saving_the_link_register_without_x29_is_not_a_frame_pointer(self):
        assert stacks._keeps_frame_pointer(OBJDUMP_PROLOGUE_ARM_NOFP) is False

    def test_no_instructions_is_no_verdict(self):
        header_only = "\n/tmp/x:\tfile format elf64-x86-64\n\n"
        assert stacks._keeps_frame_pointer(header_only) is None
        assert stacks._keeps_frame_pointer("") is None


class TestSharedLibraries:
    def test_only_resolved_paths_count(self):
        executor = ScriptedExecutor().on("ldd", stdout=LDD_WORKLOAD)
        libraries = stacks.shared_libraries(executor, "/tmp/workload")
        assert libraries == ["/lib/x86_64-linux-gnu/libc.so.6"]

    def test_a_static_binary_depends_on_nothing(self):
        executor = ScriptedExecutor().on(
            "ldd", stderr="\tnot a dynamic executable\n", exit_code=1
        )
        assert stacks.shared_libraries(executor, "/tmp/static") == []


class TestProbeModule:
    def test_scaffolding_below_the_size_floor_is_never_probed(self):
        executor = (
            ScriptedExecutor()
            .on("objdump", stdout=OBJDUMP_SYMTAB_FP)
            .on("objdump", stdout=OBJDUMP_PROLOGUE_FP)
        )
        survey = stacks.probe_module(executor, "objdump", "/tmp/workload-fp")
        assert (survey.probed, survey.keeping) == (1, 1)
        # main is 312 bytes at 0x10c0; _start (38 bytes) stays under the
        # floor, so exactly one bounded disassembly was asked for.
        assert executor.calls[-1] == [
            "objdump", "--disassemble",
            "--start-address=0x10c0", "--stop-address=0x10e0",
            "/tmp/workload-fp",
        ]

    def test_a_stripped_library_is_probed_through_its_dynamic_table(self):
        executor = (
            ScriptedExecutor()
            .on("objdump", stdout=OBJDUMP_SYMTAB_LIBC)
            .on("objdump", stdout=LIBC_DYNSYM)
        )
        for disassembly in LIBC_PROLOGUES.values():
            executor.on("objdump", stdout=disassembly)
        survey = stacks.probe_module(executor, "objdump", "/lib/libc.so.6")
        assert (survey.probed, survey.keeping) == (8, 7)
        # Aliases of one address (strxfrm_l/__strxfrm_l) collapse into a
        # single probe, largest function first.
        assert executor.calls[2][2] == "--start-address=0xbcb80"
        assert len(executor.calls) == 10


class TestDecide:
    def test_intel_hardware_offers_lbr_without_probing_anything(self):
        executor = ScriptedExecutor()
        decision = stacks.decide(executor, Config(), "/tmp/workload", INTEL)
        assert decision.mode == "lbr"
        assert executor.calls == []

    def test_frame_pointers_everywhere_settle_the_fp_rung(self):
        executor = _ladder_executor(OBJDUMP_SYMTAB_FP, OBJDUMP_PROLOGUE_FP)
        decision = stacks.decide(executor, Config(), "/tmp/workload-fp", EPYC)
        assert decision.mode == "fp"
        assert [survey.rate for survey in decision.modules] == [1.0, 7 / 8]
        assert "94%" in decision.detail

    def test_an_fp_less_target_loses_the_ladder_and_is_named(self):
        executor = _ladder_executor(OBJDUMP_SYMTAB_NOFP, OBJDUMP_PROLOGUE_NOFP)
        decision = stacks.decide(executor, Config(), "/tmp/workload-nofp", EPYC)
        assert decision.mode is None
        assert "worst offender: /tmp/workload-nofp (0%)" in decision.detail
        assert "-fno-omit-frame-pointer" in decision.remedy

    def test_the_threshold_is_configuration_never_a_constant(self):
        executor = _ladder_executor(OBJDUMP_SYMTAB_FP, OBJDUMP_PROLOGUE_FP)
        config = Config(stacks_fp_threshold=0.95)
        decision = stacks.decide(executor, config, "/tmp/workload-fp", EPYC)
        assert decision.mode is None

    def test_without_gnu_objdump_prologues_cannot_be_probed(self):
        executor = ScriptedExecutor().on("objdump", exit_code=127)
        decision = stacks.decide(executor, Config(), "/tmp/workload", EPYC)
        assert decision.mode is None
        assert "binutils" in decision.remedy

    def test_llvm_objdump_is_not_a_substitute(self):
        # llvm-objdump silently swaps in the separate debug file's
        # sections - all zeros - when a distribution ships one: a machine
        # whose `objdump` answers as LLVM cannot probe prologues.
        executor = ScriptedExecutor().on("objdump", stdout=LLVM_OBJDUMP_VERSION)
        decision = stacks.decide(executor, Config(), "/tmp/workload", EPYC)
        assert decision.mode is None

    def test_nothing_probeable_is_a_named_dead_end(self):
        executor = (
            ScriptedExecutor()
            .on("objdump", stdout=OBJDUMP_VERSION)
            .on("ldd", exit_code=1)
            .on("objdump", stdout=OBJDUMP_SYMTAB_LIBC)
            .on("objdump", exit_code=1)
        )
        decision = stacks.decide(executor, Config(), "/tmp/stripped", EPYC)
        assert decision.mode is None
        assert "symbol table" in decision.remedy


class TestDoctor:
    def test_the_ladder_is_meaningless_outside_linux(self):
        executor = ScriptedExecutor(system="Darwin")
        check = doctor._call_stacks(executor, Config(), [sys.executable], INTEL)
        assert check is None

    def test_a_missing_target_leaves_nothing_to_probe(self):
        executor = ScriptedExecutor()
        check = doctor._call_stacks(
            executor, Config(), ["/nonexistent/binary"], INTEL
        )
        assert check is None

    def test_a_settled_rung_is_an_ok_check(self):
        check = doctor._call_stacks(
            ScriptedExecutor(), Config(), [sys.executable], INTEL
        )
        assert (check.name, check.status) == ("call-stacks", "ok")
        assert check.detail.startswith("lbr")

    def test_no_rung_is_the_named_degradation(self):
        executor = ScriptedExecutor().on("objdump", exit_code=127)
        check = doctor._call_stacks(executor, Config(), [sys.executable], None)
        assert check.status == "missing"
        assert check.degradation.name == "call-stacks-unavailable"
