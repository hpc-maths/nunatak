"""Regenerate the llvm-mca input listings from the frozen binaries.

The listings are what `run` feeds llvm-mca in production: the hot
loop's body in nunatak's own parsed form, one `mnemonic operands` line
per instruction, branches and padding stripped. Deriving them here with
the same parser keeps the corpus honest - a hand-written listing would
only test our idea of a loop body.

Run on Linux x86_64 with GNU objdump, from a checkout of nunatak:

    python corpus/listings/extract.py

The products are committed next to this script; rerunning it is a
corpus refresh that only makes sense after `corpus/binaries/capture.sh`
refreshed the binaries it reads.
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from nunatak.attribution.loops import classify, listing_lines, loops, parse

BINARIES = Path(__file__).resolve().parents[1] / "binaries"
LISTINGS = Path(__file__).resolve().parent

# (listing name, frozen binary, function, count that identifies the loop)
TARGETS = [
    ("axpy-avx512.s", "symbols-avx512", "axpy", "vector_fp"),
    ("gather-avx2.s", "gather-avx2", "gather_sum", "gathers"),
]


def hot_body(binary: str, function: str, count: str) -> list:
    """The body of the innermost loop of `function` whose classified
    `count` is nonzero - the loop the samples of a real run would name."""
    disassembly = subprocess.run(
        ["objdump", f"--disassemble={function}", "-d", str(BINARIES / binary)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    instructions = parse(disassembly)
    candidates = []
    for loop in loops(instructions):
        body = [i for i in instructions if loop.covers(i.offset)]
        counts = classify(body)
        if counts is not None and counts.get(count, 0) > 0:
            candidates.append((loop.end - loop.start, body))
    if not candidates:
        raise SystemExit(f"no loop of {binary}:{function} has {count} > 0")
    return min(candidates, key=lambda entry: entry[0])[1]


def main() -> None:
    """Write each target's listing exactly as production would."""
    for name, binary, function, count in TARGETS:
        lines = listing_lines(hot_body(binary, function, count))
        (LISTINGS / name).write_text("\n".join(lines) + "\n")
        print(f"{name}: {len(lines)} instructions from {binary}:{function}")


if __name__ == "__main__":
    main()
