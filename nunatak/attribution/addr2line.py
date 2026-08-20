"""addr2line fallback: symbolization from what the machine offers.

The nominal path is llvm-symbolizer; when no usable LLVM exists, GNU
addr2line (binutils) is executed instead - executable but never
redistributable, being GPL-3. The fallback keeps the same contract: one
batched invocation per module, chains innermost first, and the extent
rule.

The extent rule does not come with this tool: GNU addr2line names an
address in the gap between two functions after the preceding symbol
(measured: two bytes past `main`'s extent still answer `main`), and that
output is indistinguishable from a legitimate hit in a binary compiled
without debug information - both print the name with `??:?`. The symbol
table is the only witness, so the sibling GNU readelf is read first and
every address outside `[st_value, st_value + st_size)` of a function
stays unresolved. The same table provides `st_value`, the start address
that anchors the function-grain physical identity.

What the fallback cannot offer, honestly: no declaration line (DWARF
knows it, the tool does not print it), and no line-table fingerprints -
staleness cannot be verified, extracts are accepted as if unfingerprinted.
macOS `atos` waits for a macOS collector to exist: there is no Darwin
collection path yet, so it would be dead code.
"""

from __future__ import annotations

import os
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

# One GNU readelf symbol row: `    32: 00000000000010c0   312 FUNC ...`.
_SYMBOL = re.compile(
    r"^\s*\d+:\s+(?P<value>[0-9a-fA-F]+)\s+(?P<size>0x[0-9a-fA-F]+|\d+)\s+FUNC\s+"
    r"\S+\s+\S+\s+(?P<ndx>\S+)"
)

# `0x...` lines separate the per-address blocks that `-a` requests.
_ADDRESS = re.compile(r"^0x(?P<address>[0-9a-fA-F]+)$")

# A position line: `/path/file.c:12`, `/path/file.c:12 (discriminator 1)`,
# `??:0` or `??:?` when unknown.
_POSITION = re.compile(r"^(?P<file>.*):(?P<line>\d+|\?)(?: \(discriminator \d+\))?$")


@dataclass(frozen=True)
class Addr2Line:
    """One usable GNU addr2line: an invoked path and its version."""

    path: str
    version: str

    @property
    def readelf(self) -> str:
        """The GNU readelf sitting next to this addr2line: same binutils,
        same install."""
        directory = os.path.dirname(self.path)
        return os.path.join(directory, "readelf") if directory else "readelf"

    @property
    def dwarfdump(self) -> None:
        """binutils reads no DWARF 5 line-table fingerprints: staleness
        cannot be verified on this path, and pretending otherwise would
        invoke addr2line with another tool's arguments."""
        return None

    def symbolize(
        self,
        executor: Executor,
        module: str,
        offsets: list[int],
        env: dict[str, str] | None = None,
    ) -> ModuleSymbolization:
        """Resolve `offsets` (module-relative virtual addresses) in `module`.

        The function extents are read first; without them the extent rule
        cannot be enforced and the module is declared unreadable rather
        than symbolized on trust. `env` carries the debuginfod controls
        (this is where addr2line may fetch a distribution library's
        debug file); the extent rule stays local either way.
        """
        extents = _function_extents(executor, self.readelf, module)
        if extents is None:
            return ModuleSymbolization(
                error=f"{self.readelf} cannot read {module}: the extent rule "
                "cannot be enforced without the symbol table"
            )
        wanted = sorted(set(offsets))
        argv = [self.path, "-e", module, "-a", "-f", "-C", "-i"]
        argv += [hex(offset) for offset in wanted]
        invocation = executor.run(argv, env=env)
        if invocation.exit_code != 0 or not invocation.stdout:
            reason = (invocation.stderr or "").strip()
            return ModuleSymbolization(
                error=reason or f"addr2line exited with {invocation.exit_code}"
            )
        chains = _parse(invocation.stdout)
        kept: dict[int, AttributionChain] = {}
        for offset in wanted:
            chain = chains.get(offset)
            start = _covering(extents, offset)
            if chain is None or start is None:
                continue
            frames = list(chain.frames)
            frames[-1] = Frame(
                function=frames[-1].function,
                file=frames[-1].file,
                line=frames[-1].line,
                start_address=start,
            )
            kept[offset] = AttributionChain(frames=tuple(frames))
        return ModuleSymbolization(chains=kept)


def _function_extents(
    executor: Executor, readelf: str, module: str
) -> list[tuple[int, int]] | None:
    """The `(st_value, st_size)` of `module`'s defined functions, None
    when the table cannot be read. `.symtab` and `.dynsym` rows both
    count; aliases of one address keep the widest extent."""
    invocation = executor.run([readelf, "--wide", "--symbols", module])
    if invocation.exit_code != 0 or not invocation.stdout:
        return None
    extents: dict[int, int] = {}
    for line in invocation.stdout.splitlines():
        match = _SYMBOL.match(line)
        if match is None or match.group("ndx") in ("UND", "ABS"):
            continue
        size = int(match.group("size"), 0)
        if size <= 0:
            continue
        value = int(match.group("value"), 16)
        extents[value] = max(extents.get(value, 0), size)
    return sorted(extents.items())


def _covering(extents: list[tuple[int, int]], offset: int) -> int | None:
    """The start of the function whose extent covers `offset`, None when
    the address falls in a gap - refusing to name the gap after its
    neighbour."""
    for value, size in extents:
        if value <= offset < value + size:
            return value
    return None


def _parse(stdout: str) -> dict[int, AttributionChain]:
    """Parse `-a -f -C -i` output into per-offset chains.

    Each block is an `0x...` line followed by (function, position) line
    pairs, innermost first. A `??` function is the tool's empty record.
    """
    chains: dict[int, AttributionChain] = {}
    offset: int | None = None
    frames: list[Frame] = []

    def close():
        if offset is not None:
            chains[offset] = AttributionChain(frames=tuple(frames))

    lines = stdout.splitlines()
    index = 0
    while index < len(lines):
        address = _ADDRESS.match(lines[index].strip())
        if address is not None:
            close()
            offset, frames = int(address.group("address"), 16), []
            index += 1
            continue
        function = lines[index].strip()
        position = _POSITION.match(lines[index + 1].strip()) if index + 1 < len(lines) else None
        if function and function != "??" and position is not None:
            file = position.group("file")
            line = position.group("line")
            frames.append(
                Frame(
                    function=function,
                    file=file if file != "??" else None,
                    line=int(line) if line not in ("?", "0") else None,
                )
            )
        index += 2
    close()
    return chains


def locate(executor: Executor, config: Config) -> Addr2Line | None:
    """The first GNU addr2line that actually runs.

    Only the GNU tool is accepted: the parser and the extent workaround
    are vetted against its verbatim output, and anything else claiming
    the name would be trusted on faith.
    """
    candidates = []
    if "addr2line" in config.tools:
        candidates.append(config.tools["addr2line"])
    on_path = shutil.which("addr2line")
    if on_path:
        candidates.append(on_path)
    for candidate in candidates:
        invocation = executor.run([candidate, "--version"])
        if invocation.exit_code != 0 or not invocation.stdout:
            continue
        match = re.search(r"GNU addr2line.*?(\d+(?:\.\d+)+)", invocation.stdout)
        if match is not None:
            return Addr2Line(path=candidate, version=match.group(1))
    return None
