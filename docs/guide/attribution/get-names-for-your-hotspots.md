# Get names for your Hotspots

Compile with `-g`. The rest of this page is what to do when names are
missing anyway.

## Ask before you profile

`nunatak doctor -- ./stencil` inspects the binary you are about to
profile and answers with one of four rows, each carrying what to do
about it:

```
ok       target-attribution debug information present: line-level attribution
warning  target-attribution no debug information: attribution capped at function level
                            -> compile with -g to get line numbers, inlining and source extracts
warning  target-attribution stripped binary: attribution capped at symbol level
                            -> keep the symbol table, or compile with -g
warning  target-attribution no symbol table at all: Hotspots will stay unresolved
                            -> compile with -g, or at least keep the symbol table
```

The last two differ by what is left: a stripped shared library still
exports its dynamic symbols, a fully stripped executable exports
nothing.

The symbolizer has a row of its own, and it is the one to check on a
machine you have just arrived on:

```
ok       llvm               LLVM 20 (/usr/lib/llvm-20/bin/llvm-symbolizer)
```

## What each build actually gives

The same program - `examples/stencil` from this repository - profiled
three ways on the same machine. Built with `-O2 -g`:

```
summary: 5 Hotspots above the statistical floor hold 100% of the sampled time (7113 samples of task-clock over 7.13 s)
  reaction (line) - 38% of the sampled time - latency-bound
  update (line) - 32% of the sampled time - latency-bound
  laplacian (line) - 29% of the sampled time - latency-bound
```

Built at `-O2` without `-g`, so the symbol table alone remains - the
same three functions, the same shares, no source position:

```
  reaction (function) - 38% of the sampled time - latency-bound
  update (function) - 32% of the sampled time - latency-bound
  laplacian (function) - 29% of the sampled time - latency-bound
```

Stripped:

```
summary: 21 Hotspots above the statistical floor hold 99% of the sampled time (8723 samples of task-clock over 8.75 s)
  stencil+0x16a5 (unresolved) - 18% of the sampled time - latency-bound
  stencil+0x1624 (unresolved) - 11% of the sampled time - latency-bound
  stencil+0x1605 (unresolved) - 8% of the sampled time - latency-bound
```

The time is the same time. What the strip removed is the function that
would have gathered those addresses under one name, so they arrive as
what they are: addresses. Nothing is attached to the symbol that
precedes them, and [how attribution works](how-attribution-works.md)
says why that would be worse.

## When the unnamed module is not yours

A distribution library is stripped the same way, and it shows up the
same way in a Run of your own code:

```
  libmpi.so.40.40.7+0x26fa18 (unresolved) - 7% of the sampled time - imbalance
```

Install the library's debuginfo package - `libopenmpi-dev`, `glibc-debuginfo`
and their kin - or point the machine at a
[debuginfod server](../../deployment/debuginfod.md), which both
symbolizers consult on their own. Neither ever helps with your own code,
which is what `-g` is for.

## When no symbolizer answers

Without a usable `llvm-symbolizer`, the run declares `llvm-missing` and
falls back to the platform's own tool - GNU `addr2line` on Linux, `atos`
on macOS. Names keep coming; source staleness fingerprints and static
loop analysis do not. Install LLVM 19 or newer to get them back, and the
[degradation catalogue](../../reference/degradations.md) has the whole
entry.

## What stays unresolved, and should

```
  [unknown] (unresolved) - no placement: no dram_bytes raw counter in this Run
```

Kernel and vdso addresses have no user-space symbol to be attributed to.
They stay unresolved by design, and a Run that shows a small unresolved
share is a Run behaving correctly.
