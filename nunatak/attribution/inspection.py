"""Module inspection: which symbol and debug sections an object offers.

The symbolizer output alone cannot tell a `.symtab` name from a
`.dynsym`-only one, yet the difference is what separates the `function`
resolution level from `symbol` - and what tells the user whether the way
forward is a debuginfo package or a `-g` recompile. The inventory comes
from the llvm-readelf sitting next to the located llvm-symbolizer: same
install, same version.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from nunatak.collect.execution import Executor

# One GNU-style table row per section: `  [ 4] .dynsym  DYNSYM  ...`.
_SECTION = re.compile(r"^\s*\[\s*\d+\]\s+(\.\S*)")


@dataclass(frozen=True)
class ModuleSections:
    """Presence of the sections that grade attribution."""

    symtab: bool
    dynsym: bool
    debug_info: bool


def readelf_path(symbolizer_path: str) -> str:
    """The llvm-readelf sibling of a located llvm-symbolizer, honoring
    versioned basenames like `llvm-symbolizer-19`."""
    directory, base = os.path.split(symbolizer_path)
    return os.path.join(directory, base.replace("llvm-symbolizer", "llvm-readelf"))


def inspect(executor: Executor, readelf: str, module: str) -> ModuleSections | None:
    """Section inventory of `module`, or None when it cannot be established
    - llvm-readelf missing, module unreadable. The caller then keeps the
    level the symbolizer output already justified rather than guessing."""
    invocation = executor.run([readelf, "-S", module])
    if invocation.exit_code != 0 or not invocation.stdout:
        return None
    names = {
        match.group(1)
        for line in invocation.stdout.splitlines()
        if (match := _SECTION.match(line))
    }
    return ModuleSections(
        symtab=".symtab" in names,
        dynsym=".dynsym" in names,
        debug_info=".debug_info" in names,
    )
