"""atos fallback: symbolization from what every Mac offers.

The nominal path is llvm-symbolizer; Xcode ships none, so on a typical
Mac the fallback is the platform's own atos. It keeps the contract: one
batched invocation per module (`-offset` takes module-relative
addresses directly), chains innermost first with `-i`, and the
function-grain anchor.

The anchor comes from `nm`: Mach-O symbols carry no size, so a
function's extent runs to the next text symbol - alignment padding
between two functions attributes to the preceding one, which no reader
of the format can tell apart, and which no sampled PC lands in anyway.
atos itself is honest about the void: an address outside every symbol
comes back as bare hex, never named after a neighbour.

What the fallback cannot offer, honestly: no declaration line, and no
line-table fingerprints - staleness cannot be verified, extracts are
accepted as if unfingerprinted, exactly like the addr2line path.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass

from nunatak.attribution.symbolizer import (
    AttributionChain,
    Frame,
    ModuleSymbolization,
)
from nunatak.collect.execution import Executor
from nunatak.config import Config

# One atos output line: `name (in module) (file.c:12)`, or
# `name (in module) + 100` without debug information, or bare
# `0x... (in module)` when no symbol covers the address.
_NAMED = re.compile(
    r"^(?P<function>.+?) \(in [^)]+\)"
    r"(?: \((?P<file>.+):(?P<line>\d+)\)| \+ \d+)?$"
)

# One `nm -n` text-symbol row: `00000001000004b0 T _axpy`.
_TEXT_SYMBOL = re.compile(r"^(?P<value>[0-9a-fA-F]+) (?P<type>[TtSs]) (?P<name>\S+)$")

_HEADERS = ("__mh_execute_header", "__mh_dylib_header", "__mh_bundle_header")


@dataclass(frozen=True)
class Atos:
    """One usable atos: an invoked path and the OS release versioning it."""

    path: str
    version: str

    @property
    def readelf(self) -> None:
        """No section inventory rides with atos: Mach-O is not ELF, and
        pretending a reader exists would grade attribution on faith."""
        return None

    @property
    def dwarfdump(self) -> None:
        """No line-table fingerprints either: staleness cannot be
        verified on this path, extracts are accepted as if
        unfingerprinted - the addr2line posture, kept."""
        return None

    def symbolize(
        self,
        executor: Executor,
        module: str,
        offsets: list[int],
        env: dict[str, str] | None = None,
    ) -> ModuleSymbolization:
        """Resolve `offsets` (module-relative) in `module`.

        The symbol starts are read from `nm` first: they carry the
        start_address that anchors the function-grain physical identity,
        which atos's text output never prints. Without them the module
        is declared unreadable rather than symbolized anchorless.
        """
        starts = _symbol_starts(executor, module)
        if starts is None:
            return ModuleSymbolization(
                error=f"nm cannot read {module}: no symbol starts to anchor on"
            )
        wanted = sorted(set(offsets))
        argv = [self.path, "-o", module, "-i", "-offset"]
        argv += [hex(offset) for offset in wanted]
        invocation = executor.run(argv, env=env)
        if invocation.exit_code != 0 or invocation.stdout is None:
            reason = (invocation.stderr or "").strip()
            return ModuleSymbolization(
                error=reason or f"atos exited with {invocation.exit_code}"
            )
        blocks = _blocks(invocation.stdout)
        if len(blocks) != len(wanted):
            return ModuleSymbolization(
                error=f"atos answered {len(blocks)} blocks for "
                f"{len(wanted)} addresses"
            )
        chains: dict[int, AttributionChain] = {}
        for offset, frames in zip(wanted, blocks):
            start = _preceding(starts, offset)
            if not frames or start is None:
                chains[offset] = AttributionChain()
                continue
            frames[-1] = Frame(
                function=frames[-1].function,
                file=frames[-1].file,
                line=frames[-1].line,
                start_address=start,
            )
            chains[offset] = AttributionChain(frames=tuple(frames))
        return ModuleSymbolization(chains=chains)


def symbol_table(executor: Executor, module: str) -> tuple[int, list[int]] | None:
    """`module`'s Mach-O base and the module-relative starts of its text
    symbols, sorted; None when nm cannot read the module.

    nm prints file virtual addresses: the Mach-O header symbol names the
    module's base, subtracted so executables (based at 4 GiB) and
    dylibs (based at zero) anchor alike. The base itself rides along for
    the readers that must speak to tools in file addresses - the
    disassembler's ranges, for one.
    """
    invocation = executor.run(["nm", "-n", module])
    if invocation.exit_code != 0 or not invocation.stdout:
        return None
    values: list[int] = []
    base = 0
    for line in invocation.stdout.splitlines():
        match = _TEXT_SYMBOL.match(line.strip())
        if match is None:
            continue
        value = int(match.group("value"), 16)
        if match.group("name") in _HEADERS:
            base = value
            continue
        values.append(value)
    if not values:
        return None
    return base, sorted(value - base for value in values)


def _symbol_starts(executor: Executor, module: str) -> list[int] | None:
    """The module-relative text-symbol starts alone, for the anchor."""
    table = symbol_table(executor, module)
    return table[1] if table is not None else None


def _preceding(starts: list[int], offset: int) -> int | None:
    """The start of the last symbol at or before `offset`, None when the
    address precedes every symbol - there is nothing to anchor on."""
    anchor = None
    for value in starts:
        if value <= offset:
            anchor = value
        else:
            break
    return anchor


def _blocks(stdout: str) -> list[list[Frame]]:
    """Split `-i` output into per-address frame lists, in input order.

    Blocks are separated by blank lines; inside one, frames are printed
    innermost first. A bare-hex answer is atos's empty record: the
    address has no covering symbol, and the block stays frameless.
    """
    blocks: list[list[Frame]] = []
    current: list[Frame] = []
    open_block = False
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            if open_block:
                blocks.append(current)
                current, open_block = [], False
            continue
        open_block = True
        match = _NAMED.match(line)
        if match is None or match.group("function").startswith("0x"):
            continue
        line_number = match.group("line")
        current.append(
            Frame(
                function=match.group("function"),
                file=match.group("file"),
                line=int(line_number) if line_number else None,
            )
        )
    if open_block:
        blocks.append(current)
    return blocks


def locate(executor: Executor, config: Config) -> Atos | None:
    """The platform's atos, when it answers.

    atos carries no version of its own - it follows the operating
    system, like sample - so the usage banner proves it runs and
    `sw_vers` names the release that versions it.
    """
    candidates = []
    if "atos" in config.tools:
        candidates.append(config.tools["atos"])
    on_path = shutil.which("atos")
    if on_path:
        candidates.append(on_path)
    # The platform path, unconditionally: the tool ships with macOS at a
    # fixed place, and a replay on another system has no PATH to find it
    # on - the probe must reach the executor, where the recording is.
    if "/usr/bin/atos" not in candidates:
        candidates.append("/usr/bin/atos")
    for candidate in candidates:
        invocation = executor.run([candidate])
        banner = f"{invocation.stdout or ''}{invocation.stderr or ''}"
        if "no processes or executables specified" not in banner:
            continue
        version = executor.run(["sw_vers", "-productVersion"])
        if version.exit_code != 0 or not version.stdout:
            continue
        return Atos(path=candidate, version=f"macOS {version.stdout.strip()}")
    return None
