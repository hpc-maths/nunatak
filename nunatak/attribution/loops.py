"""Static loop analysis: what the hot loop's machine code says.

Covers the CQA/MAQAO use cases without depending on MAQAO. The product's
own work is deliberately small: disassemble the physical function the
samples named, find the innermost loop carrying the sampled weight -
the address distribution already says where the time goes - and count
what the instruction stream asks for: vector versus scalar floating
point, the bytes each iteration demands, the indirect accesses. These
counts depend on nothing but a disassembler; the cycle bounds that need
a scheduling model are a separate concern with its own availability
rule.

The disassembler is GNU objdump, the same choice the prologue probing
made and for the same measured reason: llvm-objdump silently substitutes
a separate debug file's empty sections for the library's own code. The
counts describe the machine code - exact facts about instructions, never
about the execution: everything derived from them is `estimated` at
best, by invariant I6 a static analysis never produces `measured`.

Two flavors live here, dispatched by the executor's platform. Linux is
GNU objdump over ELF, x86-64 AT&T syntax. macOS is Xcode's llvm-objdump
over Mach-O, aarch64: the measured reason for refusing llvm-objdump on
Linux - it silently disassembles a separate debug file's empty NOBITS
sections - is an ELF mechanism with no Mach-O counterpart, so the
refusal does not travel. An ISA with no classifier of its own still
yields no counts: skipped with its reason, never guessed.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from nunatak.collect.execution import Executor
from nunatak.config import Config
from nunatak.pivot import Degradation, LoopAnalysis

# LLVM's -mcpu name for each table microarchitecture: the scheduling
# model the cycle bounds are computed against. The availability rule is
# mechanical because llvm-mca can list what it knows: an installed LLVM
# that does not know the name yields `unavailable` with the upgrade as
# the remedy, never a bound computed against a neighbouring model.
_MCPU = {
    "zen": "znver1",
    "zen2": "znver2",
    "zen3": "znver3",
    "zen4": "znver4",
    "zen5": "znver5",
    "skylake": "skylake",
    "skylake-sp": "skylake-avx512",
    "icelake-sp": "icelake-server",
    "sapphire-rapids": "sapphirerapids",
    "emerald-rapids": "emeraldrapids",
    "granite-rapids": "graniterapids",
    "haswell/broadwell": "haswell",
}

# llvm-mca's two verdicts on one loop body: what the ports allow, and
# what the simulated steady state actually reaches - the dependency
# chains are the gap between the two.
_MCA_CYCLES = re.compile(r"^Total Cycles:\s+(\d+)", re.M)
_MCA_ITERATIONS = re.compile(r"^Iterations:\s+(\d+)", re.M)
_MCA_RTHROUGHPUT = re.compile(r"^Block RThroughput:\s+([\d.]+)", re.M)

# One objdump row: address, encoded bytes, mnemonic, operands, and an
# optional `# comment` annotation. Continuation rows (bytes only) and
# bare labels do not match, which is exactly right.
_ROW = re.compile(
    r"^\s+(?P<offset>[0-9a-f]+):\t[0-9a-f ]+\t"
    r"(?P<mnemonic>\S+)(?:\s+(?P<operands>[^#<]*?))?\s*(?:[#<].*)?$"
)

# Padding and prefixes the classifier ignores entirely.
_PADDING = {"nop", "nopl", "nopw", "endbr64", "data16", "cs", "lea"}

# Floating-point arithmetic, AT&T: an optional VEX `v`, the operation,
# an optional FMA ordering suffix, then packed/scalar and element size.
_FP = re.compile(
    r"^v?(?P<op>add|sub|mul|div|sqrt|min|max|fn?m(?:add|sub)(?:132|213|231)?)"
    r"(?P<shape>[sp])(?P<element>[sd])$"
)

_GATHER = re.compile(r"^v[p]?gather")

# Plain data movement between memory and registers; arithmetic with a
# memory operand is caught separately by its parenthesised operand.
_MOVE = re.compile(r"^v?mov")

_ELEMENT_BYTES = {"s": 4, "d": 8}
_REGISTER_BYTES = (("%zmm", 64), ("%ymm", 32), ("%xmm", 16))


@dataclass(frozen=True)
class Instruction:
    """One disassembled instruction: where it sits and what it says."""

    offset: int
    mnemonic: str
    operands: str


@dataclass(frozen=True)
class Loop:
    """One loop of the control flow: a backward branch and its target."""

    start: int
    end: int

    def covers(self, offset: int) -> bool:
        """Whether `offset` lies inside this loop's body."""
        return self.start <= offset <= self.end


def parse(text: str) -> list[Instruction]:
    """The instruction rows of one `objdump --disassemble` output."""
    rows = []
    for line in text.splitlines():
        match = _ROW.match(line)
        if match is None:
            continue
        rows.append(
            Instruction(
                offset=int(match.group("offset"), 16),
                mnemonic=match.group("mnemonic"),
                operands=(match.group("operands") or "").strip(),
            )
        )
    return rows


def loops(instructions: list[Instruction]) -> list[Loop]:
    """Every loop the branches draw: a jump landing at or before itself.

    The control-flow graph of spec 08, reduced to what the question
    needs: a loop is a backward branch, its body the addresses between
    the target and the branch.
    """
    offsets = {i.offset for i in instructions}
    found = []
    for instruction in instructions:
        if not instruction.mnemonic.startswith("j"):
            continue
        target = instruction.operands.split()[0] if instruction.operands else ""
        try:
            landing = int(target, 16)
        except ValueError:
            continue
        if landing <= instruction.offset and landing in offsets:
            found.append(Loop(start=landing, end=instruction.offset))
    return found


def hot_loop(
    instructions: list[Instruction],
    weights: dict[int, float],
    candidates: list[Loop] | None = None,
) -> Loop | None:
    """The innermost loop carrying the sampled weight, None when the
    samples fall outside every loop - straight-line code has no loop to
    analyze, and pretending otherwise would analyze the wrong thing.
    `candidates` lets another flavor's branch reader supply the loops;
    by default the x86 one does."""
    if candidates is None:
        candidates = loops(instructions)
    weighted = [
        (
            sum(value for offset, value in weights.items() if loop.covers(offset)),
            -(loop.end - loop.start),
            loop,
        )
        for loop in candidates
    ]
    weighted = [entry for entry in weighted if entry[0] > 0]
    if not weighted:
        return None
    # Max weight first; among nested loops of equal weight, the smallest
    # span is the innermost.
    weighted.sort(key=lambda entry: (-entry[0], -entry[1]))
    return weighted[0][2]


def _register_bytes(text: str) -> int | None:
    """The widest vector register named in `text`, None without one."""
    for name, width in _REGISTER_BYTES:
        if name in text:
            return width
    return None


def _memory_bytes(instruction: Instruction) -> int:
    """How many bytes one execution of this instruction moves per
    memory operand: the element size for scalar shapes, the register
    width for packed ones."""
    match = _FP.match(instruction.mnemonic.lstrip("v"))
    if match is None:
        match = _FP.match(instruction.mnemonic)
    if match is not None:
        if match.group("shape") == "s":
            return _ELEMENT_BYTES[match.group("element")]
        return _register_bytes(instruction.operands) or 16
    # Data movement: suffix decides for scalars, the register for the rest.
    if instruction.mnemonic.endswith(("sd", "si64")):
        return 8
    if instruction.mnemonic.endswith("ss"):
        return 4
    return _register_bytes(instruction.operands) or 8


def _flops(instruction: Instruction) -> tuple[int, bool] | None:
    """(FLOPs per execution, packed?) for one instruction, None when it
    is not floating-point arithmetic. An FMA counts two."""
    mnemonic = instruction.mnemonic
    match = _FP.match(mnemonic) or (
        _FP.match(mnemonic[1:]) if mnemonic.startswith("v") else None
    )
    if match is None:
        return None
    element = _ELEMENT_BYTES[match.group("element")]
    packed = match.group("shape") == "p"
    lanes = 1
    if packed:
        lanes = (_register_bytes(instruction.operands) or 16) // element
    each = 2 if match.group("op").startswith(("fm", "fnm")) else 1
    return lanes * each, packed


def _destination(operands: str) -> str:
    """The last operand - AT&T's destination - honoring the commas
    inside a memory operand's parentheses."""
    depth = 0
    for index in range(len(operands) - 1, -1, -1):
        char = operands[index]
        if char == ")":
            depth += 1
        elif char == "(":
            depth -= 1
        elif char == "," and depth == 0:
            return operands[index + 1 :]
    return operands


def classify(body: list[Instruction]) -> dict | None:
    """The counts of one loop body, per iteration of the instruction
    stream - facts of the machine code, blind to cache reuse.

    None when no instruction is recognizably x86-64 AT&T: another ISA
    deserves its own classifier, not this one's guesses.
    """
    if not any(
        i.mnemonic.startswith(("mov", "vmov", "add", "vadd", "ld", "st"))
        or _FP.match(i.mnemonic.lstrip("v"))
        for i in body
    ):
        return None
    flops = 0.0
    vector_fp = 0
    scalar_fp = 0
    width = None
    loaded = 0
    stored = 0
    gathers = 0
    for instruction in body:
        if instruction.mnemonic in _PADDING:
            continue
        if _GATHER.match(instruction.mnemonic):
            gathers += 1
            loaded += _register_bytes(instruction.operands) or 32
            continue
        counted = _flops(instruction)
        if counted is not None:
            each, packed = counted
            flops += each
            if packed:
                vector_fp += 1
                register = _register_bytes(instruction.operands)
                if register is not None:
                    width = max(width or 0, register * 8)
            else:
                scalar_fp += 1
        if "(" not in instruction.operands:
            continue
        moved = _memory_bytes(instruction)
        if "(" in _destination(instruction.operands):
            stored += moved
        else:
            loaded += moved
    return {
        "flops": flops,
        "vector_fp": vector_fp,
        "scalar_fp": scalar_fp,
        "vector_width_bits": width,
        "loaded_bytes": loaded,
        "stored_bytes": stored,
        "gathers": gathers,
    }


def analyze_function(
    disassembly: str, weights: dict[int, float]
) -> tuple[Loop, dict] | None:
    """The hot loop of one disassembled function and its counts, None
    when there is no weighted loop or no classifier for the ISA."""
    instructions = parse(disassembly)
    loop = hot_loop(instructions, weights)
    if loop is None:
        return None
    body = [i for i in instructions if loop.covers(i.offset)]
    counts = classify(body)
    if counts is None:
        return None
    return loop, counts


def _weights_by_hotspot(details: list) -> dict:
    """Per-hotspot address weights, on each Hotspot's best-sampled
    counter - mixing counters would double-count the same addresses."""
    totals: dict = {}
    for detail in details:
        entry = totals.setdefault(detail.hotspot, {})
        entry[detail.counter] = entry.get(detail.counter, 0.0) + detail.value
    chosen = {
        hotspot: max(counters, key=counters.get)
        for hotspot, counters in totals.items()
    }
    weights: dict = {}
    for detail in details:
        if detail.counter == chosen[detail.hotspot]:
            entry = weights.setdefault(detail.hotspot, {})
            entry[detail.offset] = entry.get(detail.offset, 0.0) + detail.value
    return weights


def _mca_path(symbolizer) -> str | None:
    """The llvm-mca sibling of the located LLVM symbolizer, None when
    the symbolizer is the addr2line fallback - binutils has no
    scheduling model to offer."""
    if symbolizer is None or "llvm-symbolizer" not in os.path.basename(
        getattr(symbolizer, "path", "")
    ):
        return None
    directory, base = os.path.split(symbolizer.path)
    return os.path.join(directory, base.replace("llvm-symbolizer", "llvm-mca"))


def _known_cpus(executor: Executor, mca: str) -> set[str]:
    """The scheduling models this llvm-mca can be asked for."""
    invocation = executor.run([mca, "--mcpu=help"])
    text = f"{invocation.stdout or ''}\n{invocation.stderr or ''}"
    names = set()
    for line in text.splitlines():
        match = re.match(r"^\s+(\S+)\s+- Select the", line)
        if match is not None:
            names.add(match.group(1))
    return names


# One llvm-objdump Mach-O arm64 row: `1000004b4: 5400050b\tb.lt
# 0x100000554 <_axpy+0xa4>` - file virtual addresses (the caller rebases
# them), one fixed-width encoding word, immediates spelled `#0x1`, and a
# trailing symbol annotation the operands drop.
_ROW_ARM = re.compile(
    r"^(?P<offset>[0-9a-f]+):\s+[0-9a-f]{8}\s+"
    r"(?P<mnemonic>\S+)(?:\s+(?P<operands>.*?))?\s*$"
)

# aarch64 branches that draw loops. `b` and the conditions loop; `bl`
# and `blr` call, `br` dispatches, `ret` returns - none of them draws.
_ARM_BRANCH = re.compile(r"^(?:b(?:\.\w+)?|cbz|cbnz|tbz|tbnz)$")
_ARM_TARGET = re.compile(r"0x(?P<target>[0-9a-f]+)")

# aarch64 floating-point arithmetic: `f` then the operation; the
# multiply-accumulate family counts two per lane, like x86's FMAs.
# Apple's llvm-objdump prints the arrangement as a mnemonic suffix
# (`fmla.2d v5, v1, v0[0]`); the standard syntax carries it on the
# registers (`fmla v5.2d, ...`) - both are read.
_FP_ARM = re.compile(
    r"^f(?P<op>add|sub|mul|div|sqrt|min|max|nmul|abd|"
    r"mla|mls|madd|msub|nmadd|nmsub)"
    r"(?:\.(?P<lanes>\d+)(?P<element>[bhsd]))?$"
)
_ARM_FMA = {"mla", "mls", "madd", "msub", "nmadd", "nmsub"}

# A NEON arrangement (`v0.2d`) or a scalar FP register, and the memory
# register widths: q loads a full 128-bit vector, x and d eight bytes,
# w and s four.
_ARM_ARRANGEMENT = re.compile(r"\bv\d+\.(?P<lanes>\d+)(?P<element>[bhsd])\b")
_ARM_SCALAR_FP = re.compile(r"^[hsd]\d+$")
_ARM_ELEMENT_BYTES = {"b": 1, "h": 2, "s": 4, "d": 8}
_ARM_REGISTER_BYTES = {"q": 16, "v": 16, "x": 8, "d": 8, "w": 4, "s": 4}

_ARM_PADDING = {"nop"}


def parse_arm64(text: str, base: int) -> list[Instruction]:
    """The instruction rows of one llvm-objdump Mach-O disassembly,
    offsets rebased from file virtual addresses to module-relative ones
    so the sampled weights speak the same units."""
    rows = []
    for line in text.splitlines():
        match = _ROW_ARM.match(line.strip())
        if match is None:
            continue
        operands = (match.group("operands") or "").split("<")[0].strip()
        rows.append(
            Instruction(
                offset=int(match.group("offset"), 16) - base,
                mnemonic=match.group("mnemonic"),
                operands=operands,
            )
        )
    return rows


def loops_arm64(instructions: list[Instruction], base: int) -> list[Loop]:
    """Every loop the aarch64 branches draw: a branch landing at or
    before itself. The target is the operand's hex address - last for
    the compare-and-branch forms, whose first operand is the register."""
    offsets = {i.offset for i in instructions}
    found = []
    for instruction in instructions:
        if _ARM_BRANCH.match(instruction.mnemonic) is None:
            continue
        targets = _ARM_TARGET.findall(instruction.operands)
        if not targets:
            continue
        landing = int(targets[-1], 16) - base
        if landing <= instruction.offset and landing in offsets:
            found.append(Loop(start=landing, end=instruction.offset))
    return found


def _arm_flops(instruction: Instruction) -> tuple[float, bool, int | None] | None:
    """(FLOPs per execution, vector?, lanes) for one aarch64
    instruction, None when it is not floating-point arithmetic."""
    match = _FP_ARM.match(instruction.mnemonic)
    if match is None:
        return None
    each = 2 if match.group("op") in _ARM_FMA else 1
    if match.group("lanes") is not None:
        lanes = int(match.group("lanes"))
        return lanes * each, True, lanes
    arrangement = _ARM_ARRANGEMENT.search(instruction.operands)
    if arrangement is not None:
        lanes = int(arrangement.group("lanes"))
        return lanes * each, True, lanes
    first = instruction.operands.split(",")[0].strip()
    if _ARM_SCALAR_FP.match(first):
        return each, False, None
    return None


def _arm_memory_bytes(instruction: Instruction) -> int:
    """How many bytes one execution of this load or store moves: the
    sum of its register operands' widths, before the address bracket."""
    registers = instruction.operands.split("[")[0]
    moved = 0
    for token in re.findall(r"\b([qvxdws])\d+(?:\.\d*[bhsd])?\b", registers):
        moved += _ARM_REGISTER_BYTES[token]
    return moved


def classify_arm64(body: list[Instruction]) -> dict | None:
    """The counts of one aarch64 loop body, per iteration of the
    instruction stream - the same facts as x86's, NEON's fixed 128-bit
    vectors instead of register widths, and no gathers: NEON has none
    to count.

    None when no instruction is recognizably aarch64: another ISA
    deserves its own classifier, not this one's guesses.
    """
    if not any(
        i.mnemonic.startswith(("ld", "st", "add", "mov")) or _FP_ARM.match(i.mnemonic)
        for i in body
    ):
        return None
    flops = 0.0
    vector_fp = 0
    scalar_fp = 0
    width = None
    loaded = 0
    stored = 0
    for instruction in body:
        if instruction.mnemonic in _ARM_PADDING:
            continue
        counted = _arm_flops(instruction)
        if counted is not None:
            each, vector, _ = counted
            flops += each
            if vector:
                vector_fp += 1
                width = 128
            else:
                scalar_fp += 1
        if instruction.mnemonic.startswith(("ld", "st")):
            moved = _arm_memory_bytes(instruction)
            if instruction.mnemonic.startswith("st"):
                stored += moved
            else:
                loaded += moved
    return {
        "flops": flops,
        "vector_fp": vector_fp,
        "scalar_fp": scalar_fp,
        "vector_width_bits": width,
        "loaded_bytes": loaded,
        "stored_bytes": stored,
        "gathers": 0,
    }


def analyze_function_arm64(
    disassembly: str, weights: dict[int, float], base: int
) -> tuple[Loop, dict] | None:
    """The hot loop of one Mach-O disassembled function and its counts,
    None when there is no weighted loop."""
    instructions = parse_arm64(disassembly, base)
    loop = hot_loop(instructions, weights, loops_arm64(instructions, base))
    if loop is None:
        return None
    body = [i for i in instructions if loop.covers(i.offset)]
    counts = classify_arm64(body)
    if counts is None:
        return None
    return loop, counts


def listing_lines(body: list[Instruction]) -> list[str]:
    """The llvm-mca input lines for one loop body: our parsed
    `mnemonic operands` form, branches and padding stripped. The frozen
    listings of corpus/listings/ are written by this same function - the
    corpus tests exactly what production feeds the tool."""
    return [
        f"{i.mnemonic} {i.operands}".strip()
        for i in body
        if not i.mnemonic.startswith("j") and i.mnemonic not in _PADDING
    ]


def parse_mca(text: str) -> tuple[float, float] | None:
    """(port-bound, steady-state) cycles per iteration from one llvm-mca
    report, None when the report does not carry them."""
    cycles = _MCA_CYCLES.search(text)
    iterations = _MCA_ITERATIONS.search(text)
    ports = _MCA_RTHROUGHPUT.search(text)
    if cycles is None or iterations is None or ports is None:
        return None
    return float(ports.group(1)), int(cycles.group(1)) / int(iterations.group(1))


def _bounds(
    executor: Executor,
    mca: str | None,
    known: set[str] | None,
    mcpu: str | None,
    llvm_major: int | None,
    body: list[Instruction],
    listing: Path,
) -> dict:
    """The cycle bounds of one loop body, or the reason there are none.

    The listing fed to llvm-mca is written next to the Run's raw
    artifacts: the exact input of an estimate is part of explaining it.
    """
    if mca is None:
        return {"bounds_reason": "no usable LLVM: the scheduling model "
                "needs llvm-mca; install LLVM 19 or newer"}
    if mcpu is None:
        return {"bounds_reason": "unknown microarchitecture: no "
                "scheduling model to pick"}
    if known is not None and mcpu not in known:
        return {"bounds_reason": f"LLVM {llvm_major} does not know "
                f"{mcpu}; install LLVM 19 or newer"}
    lines = listing_lines(body)
    listing.parent.mkdir(parents=True, exist_ok=True)
    listing.write_text("\n".join(lines) + "\n")
    invocation = executor.run([mca, f"--mcpu={mcpu}", str(listing)])
    parsed = (
        parse_mca(invocation.stdout)
        if invocation.exit_code == 0 and invocation.stdout
        else None
    )
    if parsed is None:
        return {"bounds_reason": f"llvm-mca could not model this loop "
                f"({(invocation.stderr or '').strip()[:80] or 'no report'})"}
    ports, effective = parsed
    return {
        "cycles_ports": ports,
        "cycles_effective": effective,
        "scheduling_model": mcpu,
    }


def analyze(
    executor: Executor,
    config: Config,
    details: list,
    floor_samples: int,
    symbolizer=None,
    microarchitecture: str | None = None,
    directory: Path | None = None,
) -> tuple[list[LoopAnalysis], list[Degradation]]:
    """The hot-loop analysis of every Hotspot worth it, plus what had
    to be declared.

    Worth it: named with a physical anchor, enough samples to trust the
    address distribution, and a module file present on this machine - a
    replayed command's binary never is, so replays skip the analysis
    whole exactly like the call-stack ladder does. A missing GNU objdump
    while eligible modules exist is the one declared loss; a function
    without a weighted loop, or another ISA, is silently absent - the
    fact is unavailable and not transmitted, never approximated.
    """
    from nunatak.attribution.addr2line import _function_extents
    from nunatak.collect import stacks as prologue

    by_hotspot: dict = {}
    for detail in details:
        by_hotspot.setdefault(detail.hotspot, []).append(detail)
    eligible = []
    for hotspot, rows in by_hotspot.items():
        if hotspot.physical_identity is None:
            continue
        samples = sum(d.sample_count or 0 for d in rows)
        if samples < floor_samples:
            continue
        module = Path(hotspot.logical_identity.module)
        if not module.is_file():
            continue
        eligible.append(hotspot)
    if not eligible:
        return [], []

    if executor.system == "Darwin":
        return _analyze_darwin(
            executor, config, eligible, details, symbolizer,
            microarchitecture, directory,
        )
    objdump, version = prologue.objdump_version(executor, config)
    if version is None:
        return [], [
            Degradation(
                name="loop-analysis-unavailable",
                message=f"no GNU objdump at '{objdump}': the hot loops "
                "cannot be disassembled",
                remedy="install binutils, or set tools.objdump in nunatak.toml",
            )
        ]
    readelf = os.path.join(os.path.dirname(objdump), "readelf") if os.path.dirname(objdump) else "readelf"

    mca = _mca_path(symbolizer)
    known = _known_cpus(executor, mca) if mca is not None else None
    mcpu = _MCPU.get(microarchitecture) if microarchitecture else None

    weights = _weights_by_hotspot(details)
    analyses = []
    extents_by_module: dict = {}
    for hotspot in eligible:
        module = hotspot.logical_identity.module
        if module not in extents_by_module:
            extents_by_module[module] = _function_extents(executor, readelf, module)
        extents = extents_by_module[module] or []
        start = hotspot.physical_identity.offset
        extent = next(
            ((value, size) for value, size in extents if value == start), None
        )
        if extent is None:
            continue
        invocation = executor.run(
            [
                objdump, "--disassemble",
                f"--start-address={extent[0]:#x}",
                f"--stop-address={extent[0] + extent[1]:#x}",
                module,
            ]
        )
        if invocation.exit_code != 0 or not invocation.stdout:
            continue
        outcome = analyze_function(invocation.stdout, weights.get(hotspot, {}))
        if outcome is None:
            continue
        loop, counts = outcome
        body = [i for i in parse(invocation.stdout) if loop.covers(i.offset)]
        listing = (directory or Path(".")) / "loops" / f"{len(analyses)}.s"
        bounds = _bounds(
            executor, mca, known, mcpu,
            getattr(symbolizer, "major", None), body, listing,
        )
        analyses.append(
            LoopAnalysis(
                hotspot=hotspot,
                start_offset=loop.start,
                end_offset=loop.end,
                instructions=sum(
                    1 for i in body if i.mnemonic not in _PADDING
                ),
                flops_per_iteration=counts["flops"],
                vector_fp=counts["vector_fp"],
                scalar_fp=counts["scalar_fp"],
                vector_width_bits=counts["vector_width_bits"],
                loaded_bytes=counts["loaded_bytes"],
                stored_bytes=counts["stored_bytes"],
                gathers=counts["gathers"],
                **bounds,
            )
        )
    return analyses, []


def _darwin_objdump(executor: Executor, config: Config) -> tuple[str, str | None]:
    """Xcode's llvm-objdump, when it answers.

    The Linux refusal of llvm-objdump does not travel here: silently
    substituting a separate debug file's NOBITS sections is an ELF
    mechanism, and Mach-O has neither the sections nor the substitution.
    """
    path = config.tools.get("objdump", "objdump")
    invocation = executor.run([path, "--version"])
    output = f"{invocation.stdout or ''}{invocation.stderr or ''}"
    match = re.search(r"LLVM version (\S+)", output)
    return path, match.group(1) if match else None


def _analyze_darwin(
    executor: Executor,
    config: Config,
    eligible: list,
    details: list,
    symbolizer,
    microarchitecture: str | None,
    directory: Path | None,
) -> tuple[list[LoopAnalysis], list[Degradation]]:
    """The Darwin flavor of the hot-loop analysis: llvm-objdump over
    Mach-O, extents from nm's symbol starts - the format carries no
    sizes, a function runs to the next symbol - and the aarch64
    classifier.
    """
    from nunatak.attribution import atos

    objdump, version = _darwin_objdump(executor, config)
    if version is None:
        return [], [
            Degradation(
                name="loop-analysis-unavailable",
                message=f"no usable objdump at '{objdump}': the hot loops "
                "cannot be disassembled",
                remedy="install Xcode or its command line tools, or set "
                "tools.objdump in nunatak.toml",
            )
        ]

    mca = _mca_path(symbolizer)
    known = _known_cpus(executor, mca) if mca is not None else None
    mcpu = _MCPU.get(microarchitecture) if microarchitecture else None

    weights = _weights_by_hotspot(details)
    analyses: list[LoopAnalysis] = []
    tables: dict = {}
    for hotspot in eligible:
        module = hotspot.logical_identity.module
        if module not in tables:
            tables[module] = atos.symbol_table(executor, module)
        if tables[module] is None:
            continue
        base, starts = tables[module]
        start = hotspot.physical_identity.offset
        if start not in starts:
            continue
        following = [value for value in starts if value > start]
        stop = following[0] if following else start + (1 << 20)
        invocation = executor.run(
            [
                objdump, "--disassemble",
                f"--start-address={base + start:#x}",
                f"--stop-address={base + stop:#x}",
                module,
            ]
        )
        if invocation.exit_code != 0 or not invocation.stdout:
            continue
        outcome = analyze_function_arm64(
            invocation.stdout, weights.get(hotspot, {}), base
        )
        if outcome is None:
            continue
        loop, counts = outcome
        body = [
            i
            for i in parse_arm64(invocation.stdout, base)
            if loop.covers(i.offset)
        ]
        # The listing feeds llvm-mca: branches and padding out, exactly
        # like the x86 flavor's - except the branch spelling is arm's.
        listing_body = [
            i
            for i in body
            if _ARM_BRANCH.match(i.mnemonic) is None
            and i.mnemonic not in _ARM_PADDING
        ]
        listing = (directory or Path(".")) / "loops" / f"{len(analyses)}.s"
        bounds = _bounds(
            executor, mca, known, mcpu,
            getattr(symbolizer, "major", None), listing_body, listing,
        )
        analyses.append(
            LoopAnalysis(
                hotspot=hotspot,
                start_offset=loop.start,
                end_offset=loop.end,
                instructions=sum(
                    1 for i in body if i.mnemonic not in _ARM_PADDING
                ),
                flops_per_iteration=counts["flops"],
                vector_fp=counts["vector_fp"],
                scalar_fp=counts["scalar_fp"],
                vector_width_bits=counts["vector_width_bits"],
                loaded_bytes=counts["loaded_bytes"],
                stored_bytes=counts["stored_bytes"],
                gathers=counts["gathers"],
                **bounds,
            )
        )
    return analyses, []
