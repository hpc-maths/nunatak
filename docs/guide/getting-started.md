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
samples stay unresolved by design.

Without a usable LLVM, **GNU addr2line** (binutils) stands in - executed
on what the machine offers, never redistributed, and declared
second-choice by `doctor`. The fallback keeps the extent rule that the
tool itself does not: GNU addr2line names an address in the gap between
two functions after the preceding symbol, so the symbol table is read
first and only covered addresses resolve. What it cannot offer is
declared too: no staleness fingerprints (extracts are accepted as if
unfingerprinted, like gcc's) and no loop analysis. Without either tool
the run still measures - the names are simply missing, and the
degradation says so.

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

### The call-stack ladder

On Linux, `doctor -- <command>` also settles which call stacks a run of
that binary can afford, in a fixed order:

1. **`lbr`** when the processor offers hardware branch stacks - Intel in
   practice: some thirty frames at near-zero cost, with no requirement
   on how the application was compiled.
2. **`fp`** when the binary and its shared libraries keep frame
   pointers. No header declares that: the only witness is the machine
   code, so doctor reads the prologues of a sample of functions - the
   largest ones of each module, where samples will land - which yields a
   **rate**, never a yes/no. Each module gets one vote, so a large libc
   cannot outvote the one binary being profiled.
3. **No stacks at all**, and that is the named degradation
   `call-stacks-unavailable`: it loses the attachment of library leaves
   to user code (a hot `dgemm` inside OpenBLAS stays a Hotspot without
   caller) and the inclusive time - never the roofline, which only
   depends on the leaf.

The prologues are read by **GNU objdump** (binutils), invoked and never
redistributed. llvm-objdump is deliberately refused for this: on
distributions that ship separate debug files, it silently substitutes
their empty section content for the library's and reads no code at all.

The rate below which the `fp` rung is refused is configuration, recorded
in the Run's provenance:

```toml
[stacks]
fp_threshold = 0.75      # share of probed prologues keeping the frame pointer
```

Every `run` settles the same ladder before launching and announces the
rung it will sample with (`call stacks: fp: ...`). The settled mode rides
`perf record --call-graph`, on the single process and inside every
sampling MPI rank alike - the decision is made once, on the orchestrating
node, never re-probed per rank. perf validates its options before
launching, so a mode the kernel refuses fails fast and the recording
retries without stacks (`call-stacks-rejected`), then time-only: the
application runs exactly once.

`--call-graph dwarf` bypasses the ladder on explicit demand: it works on
any binary, frame pointers or not, by copying stack memory at every
sample - a cost that would break the observer-effect budget at full
rate, so the sampling frequency is lowered to 97 Hz and the cost
announced. There is no silent dwarf: asking is the point.

Recorded stacks are aggregated by call path and persisted in the pivot
(`pivot/stacks.parquet`, frames normalized to `(module, offset)` like
every sampled address): a per-context split of a Hotspot stays addable
years later, on a machine where the binary no longer exists. Stacks
never enter the Hotspot identity.

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
addr2line = "/usr/bin/addr2line"    # fallback when no LLVM answers

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
  pivot/               measurements, events, attribution detail, call paths (Parquet)
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

## Counter groups

On a microarchitecture nunatak knows (AMD Zen 2/3/4 today), sampling
attributes more than time: a **FLOP counter** and the **DRAM demand
fills**, scaled to bytes, ride along with `task-clock`. Each auxiliary
event uses a fixed period - every sample is worth exactly its period,
so the totals match `perf stat` within a fraction of a percent, and the
interrupt rate stays bounded by construction.

Honesty travels with the numbers: DRAM bytes come from demand fills
only (hardware prefetchers bypass them, and sampling prefetch events
inflates what they measure - an observer effect), so those Measurements
are `estimated` with that reason; Zen does not split FLOPs by
precision, so a placement against the double-precision peak says so
too. An unknown microarchitecture samples time alone, and a kernel that
rejects the event names degrades to time-only without ever running the
application twice.

## MPI runs

`nunatak run -- mpirun -n 8 ./solver` starts one launcher here and
eight ranks wherever the scheduler placed them. Collection then has two
layers, with two costs, and both live **inside the ranks** - nunatak
interposes a small shim between the launcher and the application,
without touching either. The **sampling layer** attributes Hotspots:
each sampled rank records itself, counter group included, on its own
node's counters. Below a threshold (64 ranks, `sampling.rank_threshold`
in `nunatak.toml`) every rank samples; beyond it, sampling narrows to
**rank 0 plus the first rank of each node** - Hotspots stay
attributable everywhere the code runs, at a cost that stops growing
with the job. The **counting layer** covers every other rank at
constant cost: one `perf stat` around the whole rank - time, cycles,
instructions - whose per-rank totals are what reveal load imbalance.
They carry no Hotspot, and Hotspot-level Measurements on unsampled
ranks are `unavailable`, **never extrapolated** from the sampled
neighbours.

The summary of an MPI run opens its topology right after the headline:
`ranks: 128 (3 sampled); busiest rank 17 at 1.42x the mean; MPI holds
23% of the time`. The imbalance factor is the busiest rank over the
mean - a number stated, never judged; the per-Hotspot Diagnostic is
where regimes are named. Unsampled ranks are listed among the
admissions under "what this report does not say", by number.

Each rank writes home before it exits, so a Run stays **one
directory** whatever the number of ranks and nodes - the retrieval is
done before the job epilogue, when the allocation still exists. A rank
whose node has no usable `perf` runs bare and is declared by number
(`counting-unavailable`); ranks that the world size announces but that
left nothing behind are declared too (`counting-incomplete`). Silence
about a missing rank would read as "nothing ran there".

The shim propagates the application's exit code and never touches its
stdout or stderr, and a launcher that fails to resolve its application
is left alone: nunatak wraps a launch it understands, it never guesses.

Nothing samples around the launcher: hardware events run on the ranks'
own physical counters - an outer sampler holding the same PMCs
corrupts what the ranks measure, a fact measured on real hardware, not
a precaution. For the same reason a sampled rank does not also count:
its time aggregate is recoverable from its own samples.

The **network probe** is nunatak's own binary and binds to the site's
MPI stack, whose ABIs are mutually incompatible - so it is never
shipped built. `nunatak doctor` builds it with the site's `mpicc`
(`tools.mpicc` to point elsewhere), preferably on a login node where
the compilers are, and caches it per stack under
`$XDG_CACHE_HOME/nunatak/probes`: on a cluster with modules, the MPI
loaded today is rarely the job's. The identified stack - implementation,
version, `mpicc` - is recorded in the Run's Provenance: a network
analysis whose underlying stack is unknown is not interpretable.
Without a usable `mpicc`, doctor announces
`network-analysis-unavailable` and the run proceeds.

An MPI run launches the cached probe **through the allocation's own
launcher, before the application** - the only moment the network is
ours - and its best repetition becomes the Machine's
`network_bandwidth` and `network_latency` Ceilings. The probe counts
its nodes and keeps the measurement honest: a single-node world
measured shared memory, not the interconnect, and both Ceilings say so
as a motivated downgrade. A run never compiles the probe: without a
cached binary, `network-ceiling-unavailable` names `doctor` as the way
forward. `--no-calibrate` skips the probe along with the calibration.

The MPI side of the counting layer comes from **mpiP**, preloaded into
every rank - `LD_PRELOAD`, appended to whatever the site already
preloads, never recompiling the application. Its report lands in the
Run and becomes per-rank Measurements: `mpi_time` and `app_time`
(mpiP's wall-clock view of each rank) and `mpi_sent_bytes`. The library
must be built against the site's MPI stack; nunatak looks for it in
`tools.mpip` (`nunatak.toml`), then in `LD_LIBRARY_PATH` - which is how
an environment module exposes it - then in its own cache. That cache
is filled by **`doctor`**, like the probe's: the pinned mpiP source is
downloaded once (checksum-verified; once fetched, it rebuilds offline
forever) and compiled with the site's own `mpicc` and Fortran wrapper
(`mpifort`, then `mpif77` - mpiP's build requires one) into the
stack's cache entry. No wrapper, no network on a never-fetched login
node, or a failed build: `mpi-analysis-unavailable` says which, with
the modules/spack remedy - and the run always proceeds. An application
that never reaches `MPI_Finalize` leaves no report, and the Run says
that too (`mpi-report-missing`).

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

## The HTML report

Every measuring run also writes `report.html` into the Run directory: a
**self-contained page** - no CDN, no font, no request of any kind -
that opens on a cluster without a server and still reads in ten years
from an archived file. It carries three reading levels, in the same
vocabulary as the terminal summary.

The **synthesis** opens the page: coverage, findings with direct access
to their Hotspot, "what this report does not say". An MPI run adds its
**Ranks** block - the balance sentence, then one row per rank with its
time, its MPI share and the layer that covered it (`sampled` or
`counted`), the busiest first, capped rather than flooding; unsampled
ranks join the admissions by number. Below it, the
**inventory** lists every Hotspot above the statistical floor, sortable
by any numeric column and filterable by regime, estimated Quality or
missing source. Quality and resolution level are separate columns and
never look alike: Quality is color and shape (measured plain, estimated
hatched - a downgraded row shows its reasons on hover), the resolution
level a neutral text label. An empty cell means the quantity is
**unavailable** for that Hotspot, not that it is zero - the table says
so under its last row, and the below-floor aggregate "others" closes
the table as a row of its own.

Under the inventory, the **transverse view** ventilates the sampled time
by innermost inline frame, all Hotspots combined. It shows what no
Hotspot shows alone: the header routine inlined into twelve of them -
invisible in each, dominant across them - wears its count (`in 12
hotspots`). Keyed by `(function, file)` rather than by the compiler's
inlining choices, it is the only view stable across a recompilation. A
run where nothing was inlined has nothing transverse to say: the block
does not appear.

Opening a Hotspot - from a finding or an inventory row - **substitutes**
the inventory with its **detail**; the two never sit side by side, and
the way back is the explicit button or `Escape`. The detail is where
the **roofline** lives: contextualized on one Hotspot, the device is
implicit and the chart is correct by construction - the memory diagonal
stops at the ridge (a unit-tested invariant), the selected Hotspot uses
the same Quality encoding as everywhere (full disc measured, dashed
outline estimated), the other placeable Hotspots stay as pale points
for scale. A Hotspot that cannot be placed says why **in the spot where
the chart was expected**, never a blank. Beside the chart: the metrics
with their absences written `unavailable`, the **source annotated with
samples per line** - line numbers and distribution survive `--no-source`,
only the text is withheld - and the ventilation by inline frame.

```sh
nunatak report              # regenerate the report of the most recent Run
nunatak report <run-dir>    # or of a specific one
nunatak report --no-source  # a shareable variant: no source text at all
```

Regenerating is a real operation: the analysis is never persisted, so
the report is recomputed from the measured pivot - after an upgrade, or
on a machine that only received the Run directory.

`--no-source` writes `report-no-source.html` next to the full report,
never in its place. The payload is stripped **before the page exists**,
so the shared file never contained a line of code - a page-side toggle
would be a trap, hiding text that stays embedded. Line numbers and the
per-line sample distribution remain: one still sees where the time
goes.

The **Provenance** - commit and tree state, collectors with their
versions, observed dependencies, the effective configuration with its
thresholds - is a drawer unfolding from the report's header: never a
dialog, never in the main view.

The page is rendered by a compiled TypeScript mini-app embedded in the
package. Installed wheels carry it already compiled: the packaging hook
builds it where the wheel is built, so Node is needed only there -
never on the machines that install or run nunatak. Building a wheel
from the sdist without npm still succeeds; the result simply lacks the
bundle. On a development checkout it is built once with
`npm install && npm run build` in `report-app/`. Wherever the bundle is
missing, the run continues and announces the named degradation
`report-unavailable` - a missing capability never fails a run.
