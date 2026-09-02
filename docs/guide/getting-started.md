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

The report consumes them twice. Each Hotspot's detail names its
**immediate callers** with their shares - what attaches a hot `dgemm`
inside OpenBLAS to the solver code that called it, instead of leaving a
Hotspot without source. And the metrics gain an **inclusive** share:
how much of the sampled time this function was anywhere on the path,
callers included, a recursive function counting once per path. Callers
are named by the same attribution pass as the leaves, extent rule
included: a return address in a gap keeps its honest `module+0x...`.
Without recorded paths both say so - unknown is not zero.

## Multi-pass runs

`nunatak run` executes the application **once**; event groups that do
not fit the PMU are multiplexed by the kernel. `--multi-pass` is the
explicit expert opt-in that reruns the application once per counter
group instead - relaunching an application inside an allocation the
user pays for is never a decision the tool takes alone:

```sh
nunatak run --multi-pass -- ./solver
```

The groups are semantic - one measurement concern per pass (`flops`
and `memory` on Zen and Neoverse; `flops_dp`, `flops_sp` and `memory`
on Intel) -
and each is small enough that no counter is ever multiplexed: exact
counts, which is what the extra executions buy. A **witness** -
work-proportional where cycles count time-at-frequency: the
retired-FLOP count on Zen, retired instructions on Intel (on their
dedicated fixed counter) and on Neoverse (the one architectural,
non-speculative count those cores offer) - is replicated in each pass
and compared at the end: within the threshold, cross-pass quantities - the DRAM intensity
fusing one pass's FLOPs with another's bytes - stay exactly what they
claim; beyond it, the application did different work in different
passes (a convergence criterion, dynamic scheduling, non-deterministic
MPI) and every fused quantity is downgraded to **estimated** with the
reason, while the run declares `passes-inconsistent`. Fusing silently
would produce a wrong arithmetic intensity wearing the face of an
exact measurement - the worst outcome for a user who paid for several
executions. Neither the time base nor cycles qualifies as witness, measured on
the corpus machine: the same work took 69% more cpu-seconds on a first
pass - the frequency governor ramping up - and a memory-bound run cost
4.8e9 then 6.9e9 cycles back to back, while the retired-FLOP count came
back identical to the unit. On Zen, an application without floating
point gets a vacuous witness - the honest amount of evidence available;
the instruction witnesses of Intel and Neoverse have no vacuous case.

The threshold is configuration, recorded in the Run and used by every
later analysis of it:

```toml
[passes]
witness = 0.05    # witness spread beyond which fusion is estimated
```

A module whose build-id changed between passes was **recompiled
mid-run**: an invalidity, not an uncertainty. Its Hotspots keep
separate physical identities, are presented per pass, never fused,
never placed (`module-recompiled-between-passes`) - and comparing two
versions is two Runs, never two passes. The whole invocation stays **one Run**: every
Measurement keeps its pass of origin, each pass is its own entry in the
manifest, and replicated counters only count their reference pass in
every analysis - the seconds stay one execution's worth.

If the application exits non-zero on the first pass, the remaining
passes are skipped (`passes-skipped`): relaunching a failure spends the
allocation on reproducing it. On an unknown microarchitecture there is
nothing to split and a single time-only pass runs
(`multi-pass-unavailable`); MPI runs are not covered yet and fall back
the same way.

## Counter groups

On a microarchitecture nunatak knows, sampling attributes more than
time: **FLOP counters** and a **DRAM traffic** event, scaled to bytes,
ride along with `task-clock`. Each auxiliary event uses a fixed period
- every sample is worth exactly its period, so the totals match `perf
stat` within a fraction of a percent, and the interrupt rate stays
bounded by construction.

- **AMD Zen 1 through Zen 5**: one all-precision retired-FLOP event
  and the demand DRAM fills. The Zen 2 set is validated on real PMUs;
  Zen 1 exposes no fill-source breakdown at all and counts FLOPs only.
- **Intel Skylake through Granite Rapids**: the per-width retired-FLOP
  events, folded onto precision-split counters (`flops_dp`, `flops_sp` -
  the hardware already counts an FMA twice), and retired loads that
  missed L3 as the DRAM proxy - the uncore memory controllers count per
  socket and cannot be attributed to a Hotspot.
- **Arm Neoverse V1/N2/V2** (Graviton 3/4, NVIDIA Grace, Azure Cobalt
  100): the SVE/fixed FLOP pair - SVE element operations are counted
  per 128 bits of vector, so the SVE event is scaled by the core's
  hardware vector length (256-bit on V1) - and last-level read misses
  as the DRAM proxy, write traffic existing only on the interconnect's
  per-socket PMU. These events are speculative, not retired: the FLOP
  Measurements are `estimated` with that reason, and no precision
  split exists.

The Intel and Neoverse names come from the kernel's tables and are not
yet validated on real PMUs; a kernel that does not know them degrades
to time-only.

The single execution's set is bounded by the general counters one SMT
thread actually gets, because an event the kernel rotates off its
counter undercounts silently. Where the budget cannot hold everything -
Skylake-SP offers four counters, exactly the double-precision group -
the missing groups are not truncated but **absent, and arrive with
`--multi-pass`**: single precision everywhere on Intel, memory too on
Skylake-SP.

Absences are choices, not oversights: Haswell/Broadwell retired their
FLOP counters and Neoverse N1 (Graviton 2) never had any, so those
cores attribute memory traffic only; hybrid client parts (Alder/Raptor
Lake) get no set at all, their E-cores exposing no FLOP event - a set
counting on half the cores would undercount under `measured`.

Honesty travels with the numbers: DRAM bytes come from demand fills
(Zen), retired L3-miss loads (Intel) or last-level read misses
(Neoverse) - hardware prefetchers bypass the first two, and sampling
prefetch events inflates what they measure, an observer effect - so
those Measurements are `estimated` with their reason; Zen and Neoverse
do not split FLOPs by precision, so a placement against the
double-precision peak says so too. An unknown microarchitecture
samples time alone, and a kernel that rejects the event names degrades
to time-only without ever running the application twice.

When more events are counted than the PMU has counters, the kernel
rotates them and reports each counter's **coverage**
(`time_running / time_enabled`). A multiplexed value stays `measured`
while its coverage clears `thresholds.coverage` (80% by default) - the
kernel's extrapolation over most of the run is still the quantity -
and is downgraded to `estimated` below it, with the numbers in the
reason: "counters multiplexed: coverage 63% below the 80% threshold".
Downgrading everything multiplexed would paint the report uniformly
grey and strip the label of its discriminating power. The coverage
itself rides every Measurement into the Run, whichever side of the
threshold it falls on.

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
