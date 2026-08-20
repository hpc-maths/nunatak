"""Call-stack ladder: which stack collection a launch can afford, decided
cold, before any allocation is consumed.

The ladder has three rungs. `lbr` when the processor offers hardware
branch stacks - Intel in practice: some thirty frames at near-zero cost,
with no requirement on how the application was compiled. Otherwise `fp`
when the target binary and its libraries keep frame pointers, which no
header or section declares: the only witness is the machine code itself,
so the prologues of a sample of functions are read - which yields a rate,
never a yes/no. Otherwise no stacks at all, and that absence is a named
degradation: it loses the attachment of library leaves to user code and
the inclusive time, never the roofline, which only depends on the leaf.

Prologues are disassembled by GNU objdump, executed and never
redistributed. llvm-objdump is deliberately not a candidate: when a
distribution ships separate debug files, it silently substitutes their
section content - all zeros - for the library's and reads no code at all.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from nunatak.collect.execution import Executor
from nunatak.config import Config

# Functions smaller than this are runtime scaffolding (_start,
# register_tm_clones) whose prologues say nothing about how the
# application was compiled; samples land in large functions, so those are
# the ones probed - the biggest first, a handful per module.
SIZE_FLOOR = 64
SAMPLE_PER_MODULE = 8

# A frame-pointer prologue establishes itself within the first few
# instructions; reading one cache line of code per function is enough.
PROLOGUE_BYTES = 0x20
PROLOGUE_WINDOW = 4

# One symbol-table row, `-t` and `-T` alike: value, a fixed-width flag
# field (`F` marks a function), section, then a tab and the size.
_SYMBOL = re.compile(r"^([0-9a-fA-F]+) (.{7}) (\S+)\t([0-9a-fA-F]+)\s*(.*)$")

# One disassembled instruction: address, hex bytes, then the mnemonic and
# its operands in the last tab-separated field.
_INSTRUCTION = re.compile(r"^\s*[0-9a-fA-F]+:\t[0-9a-f ]+\t(.+)$")

# The prologue instruction that establishes the frame pointer, per
# architecture as objdump names it in the `file format` line.
_FRAME_POINTER = {
    "x86-64": re.compile(r"^push\s+%rbp\b"),
    "littleaarch64": re.compile(r"^stp\s+x29,\s*x30\b"),
}


@dataclass(frozen=True)
class ModulePrologues:
    """What probing one module's prologues established."""

    module: str
    probed: int
    keeping: int

    @property
    def rate(self) -> float:
        """Share of probed prologues that establish the frame pointer."""
        return self.keeping / self.probed


@dataclass(frozen=True)
class StackDecision:
    """The rung the ladder settled on, with the evidence.

    `mode` is `lbr`, `fp`, or None for no stacks at all; `detail` states
    the evidence in one sentence and `remedy` the way forward when there
    is one. `modules` carries the per-module prologue counts the fp rate
    was computed from, empty when no probing happened.
    """

    mode: str | None
    detail: str
    remedy: str | None = None
    modules: tuple[ModulePrologues, ...] = ()


def objdump_version(executor: Executor, config: Config) -> tuple[str, str | None]:
    """The configured objdump path and its detected GNU Binutils version,
    None when it cannot run or is not GNU.

    The GNU requirement is behavioral, not a preference: see the module
    docstring for what llvm-objdump does to distribution libraries.
    """
    path = config.tools.get("objdump", "objdump")
    invocation = executor.run([path, "--version"])
    if invocation.exit_code != 0 or not invocation.stdout:
        return path, None
    match = re.search(r"GNU objdump.*?(\d+(?:\.\d+)+)", invocation.stdout)
    return path, match.group(1) if match else None


def shared_libraries(executor: Executor, target: str) -> list[str]:
    """The resolved paths of `target`'s shared library dependencies.

    Pseudo entries without a filesystem path (`linux-vdso.so.1`, the
    loader line) and unresolved `not found` libraries are excluded: there
    is nothing to read their prologues from. A static binary depends on
    nothing.
    """
    invocation = executor.run(["ldd", target])
    if invocation.exit_code != 0 or not invocation.stdout:
        return []
    libraries = []
    for line in invocation.stdout.splitlines():
        _, arrow, resolved = line.partition("=>")
        if not arrow:
            continue
        path = resolved.strip().split(" (")[0].strip()
        if path.startswith("/"):
            libraries.append(path)
    return libraries


def _functions(executor: Executor, objdump: str, module: str) -> list[tuple[int, int]]:
    """The (address, size) of the functions worth probing in `module`:
    the largest ones above the scaffolding floor, one entry per address -
    aliases would count the same prologue twice.

    `.symtab` is consulted first, the dynamic table when a stripped
    library has nothing else.
    """
    for flag in ("-t", "-T"):
        invocation = executor.run([objdump, flag, module])
        if invocation.exit_code != 0 or not invocation.stdout:
            continue
        functions: dict[int, int] = {}
        for line in invocation.stdout.splitlines():
            match = _SYMBOL.match(line)
            if match is None:
                continue
            value, flags, section, size = match.group(1, 2, 3, 4)
            if "F" not in flags or section.startswith("*"):
                continue
            if int(size, 16) >= SIZE_FLOOR:
                functions.setdefault(int(value, 16), int(size, 16))
        if functions:
            ranked = sorted(functions.items(), key=lambda entry: -entry[1])
            return ranked[:SAMPLE_PER_MODULE]
    return []


def _keeps_frame_pointer(disassembly: str) -> bool | None:
    """Whether one disassembled prologue establishes the frame pointer,
    None when no instruction could be read."""
    pattern = None
    for architecture, candidate in _FRAME_POINTER.items():
        if f"file format elf64-{architecture}" in disassembly:
            pattern = candidate
    if pattern is None:
        return None
    instructions = [
        match.group(1)
        for line in disassembly.splitlines()
        if (match := _INSTRUCTION.match(line))
    ]
    if not instructions:
        return None
    return any(pattern.match(i) for i in instructions[:PROLOGUE_WINDOW])


def probe_module(executor: Executor, objdump: str, module: str) -> ModulePrologues:
    """Read the prologues of `module`'s largest functions."""
    probed = keeping = 0
    for address, size in _functions(executor, objdump, module):
        invocation = executor.run(
            [
                objdump, "--disassemble",
                f"--start-address={address:#x}",
                f"--stop-address={address + min(size, PROLOGUE_BYTES):#x}",
                module,
            ]
        )
        if invocation.exit_code != 0 or not invocation.stdout:
            continue
        verdict = _keeps_frame_pointer(invocation.stdout)
        if verdict is None:
            continue
        probed += 1
        keeping += verdict
    return ModulePrologues(module=module, probed=probed, keeping=keeping)


def decide(
    executor: Executor, config: Config, target: str, cpu_model: str | None
) -> StackDecision:
    """Settle the ladder for `target` on this machine.

    The fp rate averages the modules, one vote each: prologue counts
    would let a large libc outvote the one binary the samples will
    actually land in. The decision compares that rate to the configured
    `stacks.fp_threshold` - a threshold can be tuned, it cannot be tuned
    silently.
    """
    if cpu_model is not None and "Intel" in cpu_model:
        return StackDecision(
            mode="lbr",
            detail="lbr: hardware branch stacks, no compile-time requirement",
        )
    objdump, version = objdump_version(executor, config)
    if version is None:
        return StackDecision(
            mode=None,
            detail=f"no hardware branch stacks and no GNU objdump at '{objdump}' "
            "to probe frame pointers with",
            remedy="install binutils, or set tools.objdump in nunatak.toml",
        )
    modules = tuple(
        survey
        for module in [target, *shared_libraries(executor, target)]
        if (survey := probe_module(executor, objdump, module)).probed
    )
    if not modules:
        return StackDecision(
            mode=None,
            detail=f"no prologue could be probed in {target} or its libraries",
            remedy="keep the symbol table: stripped of it, a binary cannot "
            "even be probed for frame pointers",
            modules=modules,
        )
    rate = sum(survey.rate for survey in modules) / len(modules)
    prologues = sum(survey.probed for survey in modules)
    evidence = (
        f"frame pointers kept in {rate:.0%} of prologues "
        f"({prologues} probed across {len(modules)} modules)"
    )
    if rate >= config.stacks_fp_threshold:
        return StackDecision(mode="fp", detail=f"fp: {evidence}", modules=modules)
    worst = min(modules, key=lambda survey: survey.rate)
    return StackDecision(
        mode=None,
        detail=f"{evidence}, below the {config.stacks_fp_threshold:.0%} threshold; "
        f"worst offender: {worst.module} ({worst.rate:.0%})",
        remedy="recompile with -fno-omit-frame-pointer, libraries included, "
        "to walk stacks at sampling cost",
        modules=modules,
    )
