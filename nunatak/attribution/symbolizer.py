"""llvm-symbolizer driver: module-relative addresses to attribution chains.

The nominal symbolization path is LLVM, declared as an external dependency
and never bundled. Probing must invoke the candidates, because finding a
file proves nothing: Homebrew's llvm formula is keg-only, hence never on
PATH, and Linux distributions install versioned, unlinked binaries.

Symbolization only ever runs on the set of distinct addresses left by the
aggregation - a few thousand in practice - so its cost is one short
invocation per module. The extent rule comes with the tool: llvm-symbolizer
names an address only when it falls inside `[st_value, st_value + st_size)`
of a symbol, and an address in a gap between symbols comes back empty
rather than attached to its neighbour.
"""

from __future__ import annotations

import glob
import json
import re
import shutil
from dataclasses import dataclass, field

from nunatak.collect.execution import Executor
from nunatak.config import Config
from nunatak.pivot import ResolutionLevel

MINIMUM_LLVM = 17
RECOMMENDED_LLVM = 19


@dataclass(frozen=True)
class Frame:
    """One step of an attribution chain: a demangled name, a source position.

    `line` is where the address falls, `declaration_line` where the function
    starts; both are None when the module has no debug information, and the
    file with them. `start_address` is the symbol's `st_value` - the
    module-relative start of the physical function, carried only by the
    outermost frame - which keys the function-grain physical identity.
    """

    function: str
    file: str | None = None
    line: int | None = None
    declaration_line: int | None = None
    start_address: int | None = None


@dataclass(frozen=True)
class AttributionChain:
    """What symbolization established for one module-relative address.

    Frames are ordered innermost first: the last one is the physical
    function - the thing with a symbol, an extent and an address - and the
    frames before it were inlined into it. An empty chain states that no
    symbol covers the address.
    """

    frames: tuple[Frame, ...] = ()

    @property
    def physical(self) -> Frame | None:
        """The physical function the address belongs to, None when no
        symbol covers it."""
        return self.frames[-1] if self.frames else None

    @property
    def resolution_level(self) -> ResolutionLevel:
        """How far this chain goes: LINE with a source position, FUNCTION
        with a bare name, UNRESOLVED when no symbol covers the address.

        The symbolizer output cannot tell `.symtab` from a `.dynsym`-only
        module, so the SYMBOL level never originates here: refining
        FUNCTION into SYMBOL requires inspecting the module's sections.
        """
        if self.physical is None:
            return ResolutionLevel.UNRESOLVED
        if self.physical.file is not None:
            return ResolutionLevel.LINE
        return ResolutionLevel.FUNCTION


@dataclass(frozen=True)
class ModuleSymbolization:
    """The outcome for one module: chains keyed by offset, and the reason
    when the module could not be read at all."""

    chains: dict[int, AttributionChain] = field(default_factory=dict)
    error: str | None = None


@dataclass(frozen=True)
class Symbolizer:
    """One usable llvm-symbolizer: an invoked path and its major version."""

    path: str
    major: int

    @property
    def readelf(self) -> str:
        """The llvm-readelf sibling of this symbolizer: same install,
        same version."""
        from nunatak.attribution import inspection

        return inspection.readelf_path(self.path)

    @property
    def dwarfdump(self) -> str:
        """The llvm-dwarfdump sibling, reader of the DWARF 5 line-table
        fingerprints the staleness guard compares."""
        from nunatak.attribution import staleness

        return staleness.dwarfdump_path(self.path)

    def symbolize(
        self, executor: Executor, module: str, offsets: list[int]
    ) -> ModuleSymbolization:
        """Resolve `offsets` (module-relative virtual addresses) in `module`.

        One batched invocation: llvm-symbolizer takes every address on the
        command line and answers with one JSON entry per address, so the
        chains come back keyed by the offset each entry names.
        """
        argv = [self.path, "--output-style=JSON", f"--obj={module}"]
        argv += [hex(offset) for offset in sorted(set(offsets))]
        invocation = executor.run(argv)
        if not invocation.stdout:
            reason = (invocation.stderr or "").strip()
            return ModuleSymbolization(
                error=reason or f"llvm-symbolizer exited with {invocation.exit_code}"
            )
        return _parse(invocation.stdout)


def _frame(entry: dict) -> Frame | None:
    """Build a Frame from one symbolizer JSON record, None for the empty
    record llvm-symbolizer emits when no symbol covers the address.

    An empty file name and a line of 0 both mean "unknown" in the tool's
    output and become None: 0 is not a line number.
    """
    function = entry.get("FunctionName") or ""
    if not function:
        return None
    start = entry.get("StartAddress") or None
    return Frame(
        function=function,
        file=entry.get("FileName") or None,
        line=entry.get("Line") or None,
        declaration_line=entry.get("StartLine") or None,
        start_address=int(start, 16) if start else None,
    )


def _parse(stdout: str) -> ModuleSymbolization:
    """Parse llvm-symbolizer JSON output into per-offset chains.

    A successful invocation prints one array with one entry per requested
    address; an unreadable module prints a single bare object carrying an
    `Error` member instead.
    """
    chains: dict[int, AttributionChain] = {}
    error = None
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            return ModuleSymbolization(
                error=f"unrecognized llvm-symbolizer output: {line[:80]!r}"
            )
        for entry in payload if isinstance(payload, list) else [payload]:
            if "Error" in entry:
                error = entry["Error"].get("Message") or "symbolization failed"
                continue
            frames = (_frame(record) for record in entry.get("Symbol", []))
            chains[int(entry["Address"], 16)] = AttributionChain(
                frames=tuple(frame for frame in frames if frame is not None)
            )
    return ModuleSymbolization(chains=chains, error=error)


def candidate_paths(config: Config) -> list[str]:
    """Paths worth probing for llvm-symbolizer.

    PATH alone cannot be trusted: Homebrew's llvm formula is keg-only, and
    Linux distributions install versioned, unlinked binaries.
    """
    candidates = []
    if "llvm-symbolizer" in config.tools:
        candidates.append(config.tools["llvm-symbolizer"])
    on_path = shutil.which("llvm-symbolizer")
    if on_path:
        candidates.append(on_path)
    candidates += [
        "/opt/homebrew/opt/llvm/bin/llvm-symbolizer",
        "/usr/local/opt/llvm/bin/llvm-symbolizer",
        *sorted(glob.glob("/usr/lib/llvm-*/bin/llvm-symbolizer"), reverse=True),
        *sorted(glob.glob("/usr/bin/llvm-symbolizer-*"), reverse=True),
    ]
    return candidates


def locate(executor: Executor, config: Config) -> Symbolizer | None:
    """The first candidate that actually runs, with its major version.

    An old LLVM is still returned: the caller decides what its age implies,
    doctor turning it into a warning or a degradation.
    """
    for candidate in candidate_paths(config):
        invocation = executor.run([candidate, "--version"])
        if invocation.exit_code != 0:
            continue
        output = f"{invocation.stdout or ''}\n{invocation.stderr or ''}"
        match = re.search(r"LLVM version (\d+)\.", output)
        if match is None:
            continue
        return Symbolizer(path=candidate, major=int(match.group(1)))
    return None
