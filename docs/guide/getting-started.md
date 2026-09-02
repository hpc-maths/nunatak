# Getting started

nunatak profiles an application without modifying it:

```sh
nunatak run -- ./my_binary
nunatak run -- mpirun -n 8 ./solver --input case.nml
```

The application runs once, its stdout/stderr untouched, and its exit code
is propagated - `nunatak run -- ./solver && post_process` behaves exactly
like the bare command. The measurements land in a **Run**: a single
self-sufficient directory under `.nunatak/`, named
`<project>-<date>-<time>`, that survives `scp`, archiving, and being
attached to a ticket. Its path is printed at the end of the run.

On Linux, sampling is collected with `perf`. On other platforms, or when
`perf` is missing, the run still executes: the missing capability is
announced **before** launch as a named degradation with the way forward,
and the Run simply carries fewer measurements.

## Checking the environment

```sh
nunatak doctor                  # tool inventory, permissions
nunatak doctor -- ./my_binary   # + target binary inspection
nunatak doctor --json
```

`doctor` invokes the tools instead of trusting their presence on `PATH`.
A cheap subset of it runs automatically at the start of every `run`.

Given a command, `doctor` also inspects the target binary and announces
how far attribution will go - line level with debug information,
function level with a bare symbol table, symbol level on a stripped
binary - **before** any compute time is spent, with the remedy when one
exists (`-g`, or keeping the symbol table).

## Static loop analysis

Every measuring run also reads the machine code of its Hotspots: the
sampled address distribution names the **innermost hot loop**, a
disassembler reads the physical function, and the instruction stream
is counted per iteration - vector versus scalar floating point, the
width used, the bytes each iteration loads and stores, the gathers.
Two flavors exist. On Linux the disassembler is GNU objdump over
x86-64 AT&T (the same tool, and the same measured reason, as the
frame-pointer probing). On macOS it is Xcode's llvm-objdump over
Mach-O aarch64 - the Linux refusal of llvm-objdump names an ELF
mechanism with no Mach-O counterpart - with function extents from
`nm`'s symbol starts and a NEON classifier (no gathers to count: NEON
has none). These counts cover the CQA/MAQAO use cases without MAQAO,
survive everywhere a disassembler can read, and are **facts of the
code, blind to cache reuse**: nothing derived from them is ever
`measured` - a static analysis cannot be (invariant I6).

The analysis needs the binary readable where the run executes; a Run
replayed elsewhere simply carries none. A function whose samples fall
outside every loop has nothing to analyze, and another ISA than the
classifier's yields no counts rather than guesses - the fact is
unavailable and not transmitted. Only a missing GNU objdump is declared
(`loop-analysis-unavailable`).

On top of the counts, **cycle bounds** come from llvm-mca's scheduling
model: what the execution ports allow per iteration, and what the
simulated steady state reaches - dependency chains are the gap between
the two (a gather loop shows 1.8 cycles on the ports and 103 in steady
state: the latency chain speaking). Their availability rule is
mechanical, because LLVM can list the `-mcpu` models it knows: a
microarchitecture absent from the installed LLVM's list leaves the
bounds `unavailable` with « install LLVM 19 or newer » as the reason -
the counts survive - and a present one yields bounds `estimated`,
naming the model used. The exact listing fed to llvm-mca is persisted
next to the Run's raw artifacts: the input of an estimate is part of
explaining it.

The report's Hotspot detail states these facts in a « Hot loop » block:
the vectorization ratio and width, the bytes each iteration moves, the
gathers, the L1 intensity and the cycle bounds - every derived quantity
`estimated` with its reason, absent bounds saying why. The L1 intensity
is what the code demands; the DRAM intensity beside it is what memory
actually served - the gap between the two is cache reuse speaking.

## What the analysis says

The analysis engine is a **pure function of (pivot, Machine)**: nothing
it produces is persisted, everything is recomputed on demand, so a Run
stays analyzable years later. For every Hotspot above the statistical
floor it states a **Diagnostic**: the share of the run, the roofline
placement - DRAM arithmetic intensity, achieved FLOP/s against the
envelope `min(compute peak, bandwidth x intensity)` - the imbalance
across Loci, and a **classification**: `imbalance`, `latency-bound`,
`memory-bound` or `compute-bound`. A classification states a regime,
never a cause.

Every derived quantity carries its **lineage** and its Quality,
propagated as the worst of its inputs: a number displayed `measured` is
measured end to end. Where a source counter does not exist - no FLOP
counter collected, no clock in seconds - the fact is `unavailable` with
the reason, never approximated.

## The summary at the end of the run

The log closes on three moments: the **summary**, the degradations
again - their announcements scrolled past long ago in a job log - and
the paths. The summary is the report's first reading level: the
sampling coverage first, then the findings ordered by decreasing share
of the sampled time, each with its quantified evidence:

```
summary: 1 Hotspot above the statistical floor holds 100% of the sampled time (2051 samples of task-clock over 2.06 s)
  main (line) - 100% of the sampled time - latency-bound
    achieved 1.22 GFLOP/s of 125 GFLOP/s attainable: 1.0% of the envelope
    DRAM intensity 1.21 flop/byte
    downgraded to estimated: demand fills only: hardware-prefetched traffic is not counted; ...
Run: .nunatak/workload-20260811-142233
Report: .nunatak/workload-20260811-142233/report.html
```

Reading only the log teaches fewer details than the report, never less
about how solid the numbers are: a downgraded value states its reason, a
Hotspot that cannot be placed says why where the placement was expected,
and what is missing is gathered under **"what this report does not
say"** - the time below the statistical floor aggregated as "others",
the time attributed to no name, the envelope ceilings that are only
estimated - instead of being scattered across footnotes or, worse,
omitted.
