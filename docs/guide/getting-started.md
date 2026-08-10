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

## Hotspot names

Sampled addresses are attributed to their **physical function** - the
thing with a symbol, an extent and an address, that you can recompile,
isolate and compare - with `llvm-symbolizer` (LLVM 17 or newer, an
external dependency that `doctor` locates and invokes). Compile with `-g`
to reach line-level attribution; without it, the symbol table still
names functions.

Every Hotspot declares how far its attribution could go - its
**resolution level**: `line`, `function`, `symbol` or `unresolved`. A
failed attribution never degrades the measurement: that time really was
spent at that address, and the Hotspot is displayed `module+0x3a1c`
rather than being attached to the nearest symbol. Kernel and vdso
samples stay unresolved by design, and without LLVM the run still
measures - the names are simply missing, and the degradation says so.

`function` and `symbol` name the same situation - a name without a
source position - but not the same remedy: `function` comes from the
symbol table of a binary built without `-g`, `symbol` from the dynamic
symbols of a stripped module, where the way forward is a debuginfo
package, not a recompile.

## Source in the Run

For every Hotspot attributed at line level, the run embeds a **source
extract** - never a whole file: the body of the physical function and
its hot inline frames, a few context lines around. The file is searched
in three steps: the path DWARF recorded, then the `--source-map OLD=NEW`
rewriting (repeatable flag, or a `[source_map]` table in
`nunatak.toml`), then a basename search under the repository root. On
multiple ambiguous matches nunatak does not choose: the Hotspot stays
without source, and the extract carries the reason instead of the text.

A resolved file is checked against the **line-table fingerprint** the
compiler recorded (clang emits an MD5 per source file by default): if
you edited the file since the profiled binary was built, its lines have
moved, and the extract is refused with that reason rather than shown
wrong. Without a fingerprint - gcc emits none - the extract is accepted
as-is.

`--no-source` embeds no source text at all, for what must leave a
sensitive site: line numbers and measurements are kept.

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

## Exit codes

The application's code is propagated in the general case. Reserved codes,
in the manner of `timeout`: **127** command not found, **126** found but
not executable, **125** nunatak failure before launch, **121** violation
of `--strict`.

Without `--strict`, a degradation never fails the run. With it, any named
degradation becomes an error - for scripted use and performance CI.

## Configuration

Three TOML layers, by increasing precedence: site (`/etc/nunatak.toml`),
project (`nunatak.toml` at the repository root), command-line flags.

```toml
name = "solver"          # Run naming; --name always wins
runs_dir = "/scratch/me/runs"

[tools]
perf = "/opt/perf/bin/perf"
llvm-symbolizer = "/usr/lib/llvm-19/bin/llvm-symbolizer"

[source_map]
"/build/app" = "/home/me/app"    # where the build tree lives now

[thresholds]
coverage = 0.8           # multiplexing coverage below which a value degrades
```

Every effective value, thresholds included, is recorded in the Run's
provenance: a threshold can be tuned, it cannot be tuned silently.

## The Run directory

```
.nunatak/solver-20260809-142233/
  manifest.json        machine snapshot, provenance, passes, degradations
  pivot/               measurements, events, attribution detail (Parquet)
  collect/             raw collector outputs (perf.data, perf script text)
```

The manifest is plain JSON, readable without nunatak. The pivot holds
measured data only; analyses are recomputed on demand by later commands,
so a Run remains fully exploitable years after being written.

The attribution detail - the inlining chain and the weight of every
sampled address of each named Hotspot - is part of the measured pivot:
it is what lets a later command ventilate a Hotspot by line and by
inline frame on a machine where the binary and the symbolizer no longer
exist. It is detail *inside* a Hotspot, never a unit of analysis.

The machine snapshot records the **allocation shape** alongside the
hardware: the cores this job actually received (affinity mask) and its
cgroup CPU and memory limits. A Machine is that couple, not a node - a
job given 8 cores of a 128-core node is a different Machine than the
whole node, and its ceilings will be measured for those 8 cores.

Until a calibration has measured the Machine, the Run carries
**theoretical FLOP/s ceilings**: the microarchitecture's per-cycle
capability, crossed with the exposed frequency and scaled to the
allocation. They are always of quality `estimated`, with the reason -
and an unknown microarchitecture yields no ceiling at all rather than
an extrapolation. Memory-bandwidth ceilings only exist measured.

**Measured ceilings** come from an embedded microbenchmark kernel -
a STREAM-style triad for memory bandwidth, FMA chains in intrinsics for
the FLOP/s peaks - compiled locally with whatever compiler the machine
offers and run as a separate process, never inside the Python
interpreter. A ceiling is the **maximum of its repetitions**, never
their mean: it is an upper bound. Polluted conditions - dispersed
repetitions, concurrent load, a kernel built without SIMD, a value far
above the theoretical peak - downgrade the ceiling to `estimated` with
the reason, they never discard it.

## Calibrating the Machine

The calibration triggers by itself at the **first `run` on an unknown
Machine**, before the application launches - the only moment the node
is truly yours. The profile is cached (keyed by hardware plus
allocation shape) and reused by every later Run on the same Machine.

```sh
nunatak calibrate            # spend the budget in a dedicated job
nunatak calibrate --force    # recalibrate despite a cached profile
nunatak run --no-calibrate -- ./solver   # skip it: ceilings stay theoretical
```

Ceilings are measured in priority order within a ~60 s budget - memory
bandwidth and the double-precision peak first, because without them
there is no roofline. A partial profile stays exploitable; whatever was
not measured keeps its theoretical, `estimated` value. When nothing can
be measured (no compiler on the machine), nothing is cached: the next
run tries again.

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
