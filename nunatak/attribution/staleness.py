"""Staleness guard: DWARF 5 line-table checksums against the files on disk.

A developer who edited a file since the profiled binary was built would
otherwise read a report pointing at lines that moved. The line table can
carry an MD5 fingerprint of each source file as the compiler read it
(clang emits one by default, gcc emits none): when the fingerprint is
present and disagrees with the resolved file, the source is neither
shown nor sent, and the extract says why. Absent fingerprint, no
verdict - the refusal requires a present and discordant fingerprint,
never a guess.

The fingerprints come from the llvm-dwarfdump sitting next to the
located llvm-symbolizer: same install, same version.
"""

from __future__ import annotations

import os
import re

from nunatak.collect.execution import Executor
from nunatak.pivot import AddressDetail

_DIRECTORY = re.compile(r'^include_directories\[\s*(\d+)\] = "(.*)"$')
_NAME = re.compile(r'^\s+name: "(.*)"$')
_DIR_INDEX = re.compile(r"^\s+dir_index: (\d+)$")
_MD5 = re.compile(r"^\s+md5_checksum: ([0-9a-f]{32})$")


def dwarfdump_path(symbolizer_path: str) -> str:
    """The llvm-dwarfdump sibling of a located llvm-symbolizer, honoring
    versioned basenames like `llvm-symbolizer-19`."""
    directory, base = os.path.split(symbolizer_path)
    return os.path.join(directory, base.replace("llvm-symbolizer", "llvm-dwarfdump"))


def line_table_checksums(
    executor: Executor, dwarfdump: str, module: str
) -> dict[str, str]:
    """The `{source path: MD5}` fingerprints of `module`'s line tables.

    Empty when the tool cannot run, the module has no line table, or the
    compiler emitted no checksums: an empty verdict verifies nothing and
    forbids nothing.
    """
    invocation = executor.run([dwarfdump, "--debug-line", module])
    if invocation.exit_code != 0 or not invocation.stdout:
        return {}

    checksums: dict[str, str] = {}
    directories: dict[int, str] = {}
    name: str | None = None
    dir_index = 0
    for line in invocation.stdout.splitlines():
        # Each compile unit opens its own prologue with its own
        # directory numbering.
        if line.startswith("debug_line["):
            directories = {}
            name = None
            continue
        match = _DIRECTORY.match(line)
        if match:
            directories[int(match.group(1))] = match.group(2)
            continue
        match = _NAME.match(line)
        if match:
            name = match.group(1)
            dir_index = 0
            continue
        match = _DIR_INDEX.match(line)
        if match:
            dir_index = int(match.group(1))
            continue
        match = _MD5.match(line)
        if match and name is not None:
            path = (
                name
                if os.path.isabs(name)
                else os.path.join(directories.get(dir_index, ""), name)
            )
            checksums[path] = match.group(1)
            name = None
    return checksums


def checksums_for(
    executor: Executor, dwarfdump: str, details: list[AddressDetail]
) -> dict[str, str]:
    """The line-table fingerprints of every module whose Hotspots carry
    source positions - the only ones an extract will be read for."""
    modules = sorted(
        {
            detail.hotspot.logical_identity.module
            for detail in details
            if any(frame.file for frame in detail.frames)
        }
    )
    checksums: dict[str, str] = {}
    for module in modules:
        checksums.update(line_table_checksums(executor, dwarfdump, module))
    return checksums
