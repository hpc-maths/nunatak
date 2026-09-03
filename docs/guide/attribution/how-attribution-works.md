# How attribution works

Sampling records addresses. Attribution turns them into names, and the
name it chooses decides what the whole report is about.

## The unit is the physical function

An address is attributed to its physical function: the thing with a
symbol, an extent and an address, which you can recompile, isolate and
compare. Lines and the full inlining chain are recorded too, as detail
inside the Hotspot rather than as units of their own - a line moves when
you edit the file above it, and a Hotspot has to survive that.

The two extremes fail symmetrically. At the grain of the physical
function alone, a report of templated C++ announces
`operator()<Mesh, Field, 2>: 80%` and teaches nothing. At the grain of
the innermost inline frame, it announces `operator[]: 40%`, which is
noise wearing the clothes of a diagnosis.

What the inline chain buys is a second view: time by inline frame,
across all Hotspots. It catches the header routine inlined in twelve
places, invisible otherwise, and it is the only view that survives a
recompilation unchanged, since it does not depend on what the compiler
chose to inline.

## An address is named only by the symbol that contains it

nunatak attributes an address to a symbol when it falls inside
`[address, address + size)`, and not otherwise. An address in the gap
between two symbols stays unresolved and is displayed
`libfoo.so+0x3a1c`.

The common practice is the opposite: name the address after the symbol
that precedes it. On a stripped module the gaps are wide and the
preceding symbol is usually unrelated to the code that ran, so the
practice produces a plausible name for the wrong function. It is the one
thing attribution could do that would let nunatak lie with confidence,
and it is refused. A stripped binary therefore profiles as a list of
addresses - which is what was measured - rather than as a list of
neighbours.

The [resolution level](../../reference/resolution-levels.md) each
Hotspot carries is the statement of how far this went: `line`,
`function`, `symbol` or `unresolved`, displayed as plain text beside the
name.

## A failed attribution does not weaken the measurement

The time really was spent at that address. What failed is the name, and
naming is a separate register from numeric uncertainty: an unresolved
Hotspot carries measurements as solid as any other, and its Quality
stays `measured`.

Downgrading it would be convenient and wrong. It would spend a label
built to say "this number is uncertain" on a situation where no number
is in doubt, and a reader who saw `estimated` there would look for a
counter problem that does not exist.

## What resolves the addresses

`llvm-symbolizer` is the nominal path, from LLVM 17 on. It reads DWARF,
returns the inlining chain, and gives line-level attribution when the
binary was built with `-g`. nunatak executes it and parses its output;
it links nothing, which is what lets the whole path be replayed from a
recording.

Where no usable LLVM answers, the platform's own tool stands in: GNU
`addr2line` from binutils on Linux, `atos` on macOS. Both are executed,
never redistributed, and `doctor` labels them second choice. The
fallback path keeps the extent rule that the tools themselves do not:
GNU `addr2line` names an address in a gap after the preceding symbol, so
nunatak reads the symbol table first and submits only the addresses a
symbol covers.

Two capabilities do not survive the fallback, and each says so where it
is missing. Source extracts arrive without a staleness fingerprint and
are accepted as unfingerprinted, the same treatment gcc's output gets;
static loop analysis needs a disassembler the fallback does not provide,
so the loop facts are absent with that reason. With neither tool
installed the run still measures: the names are missing, and
`llvm-missing` says so before the application launches.

## Why the tested window has no upper bound

LLVM publishes a major version every six months, and distributions pick
it up before our releases do. The versions our test suites exercised are
declared - 17 to 20 today, with 19 the floor for the loop analysis - and
a newer major earns a warning from `doctor` rather than a refusal.

Refusing would trade a small and loud risk - a parser that a new LLVM
genuinely breaks fails on output it cannot read, not on quiet nonsense -
for a certainty: a user whose distribution moved before our release did
would be locked out of their own machine.
