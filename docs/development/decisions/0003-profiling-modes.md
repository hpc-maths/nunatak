# 0003. Profiling modes: one execution by default, an overhead budget held by construction

*Recorded 2026-08-09.*

## Context and decision

LIKWID's region-counting mode requires markers in the source, which rules
it out for a zero-instrumentation tool. Attributing raw counters to a
Hotspot without touching the code leaves one road, event-triggered
sampling: one sample every N events, attributed to the current address.
Everything below sits inside that frame.

`nunatak run` executes the application once by default. Event groups that
do not fit in the core PMU's counters are multiplexed by the kernel,
which extrapolates. An explicit multi-pass mode reruns the application
with disjoint groups for whoever wants exact counters: relaunching an
application inside an allocation the user pays for is not a decision the
tool should take alone.

The overhead budget targets 10% of wall clock and is held by
construction, never verified afterwards. Measuring it would require an
unprofiled reference run, which would double the cost and contradict the
previous decision. The only levers are therefore the sampling frequency,
the number of instrumented GPU launches, and the buffer sizes. The
frequency is adaptive: a fixed frequency yields too few samples on a
three-second application and tens of millions of useless ones on a
six-hour application.

Every approximation this frame introduces is made visible by a motivated
Quality downgrade, never passed over in silence.

## Options considered

- Multi-pass by default: exact counters from the first use, dropped
  because it multiplies the user's compute time without being asked.
- Never relaunch, under any circumstance: the most legible contract,
  dropped because it permanently closes the door on exact counters for
  users who want them and can pay for them.
- Two automatic passes as soon as a GPU is detected (the NERSC method:
  `nsys` then a targeted `ncu`): the most representative GPU coverage,
  dropped for the same reason as multi-pass by default.
- A budget measured by a reference run: the only way to know the real
  overhead, dropped for its systematic cost.
- Sampling every rank at a reduced frequency: uniform coverage, dropped
  because each rank then falls below the statistical floor precisely when
  the run is at its largest.
- `--focus memory|compute|mpi` from v1, to steer collection priorities:
  it assumes the user already knows where their problem is, which is what
  they came to find out. A possible later refinement, not a default
  mechanism.

## Consequences

A Measurement from multiplexed counters keeps its coverage ratio
(`time_running / time_enabled`). Above the threshold - around 80%,
configurable - it stays measured; below it, it is downgraded to
estimated. Labelling everything multiplexed as estimated would paint the
report uniformly grey and strip the label of its discriminating power.

The GPU is covered in a single execution: `nsys` takes the whole timeline
at low overhead, `ncu` instruments only a few launches per kernel name,
the first launch being excluded as unrepresentative warm-up. Kernel
replay, which costs 10x to 100x, therefore applies to a handful of
launches only. The GPU roofline is available by default, computed on a
sample of launches whose coverage is announced in the report.

Every Measurement carries its sample count and its relative error,
decreasing as `1/sqrt(n)`. Below a floor the Measurement becomes
estimated; far below it, the Hotspot joins an "others" aggregate that
preserves the totals without polluting the views. The LLM never receives
a Hotspot below the floor: explaining noise costs the same generation
time as explaining a real bottleneck.

In multi-pass mode a witness group - cycles and retired instructions - is
replicated in every pass and compared at the end. A gap beyond the
threshold marks a non-reproducible application, such as a convergence
criterion, dynamic scheduling or non-deterministic MPI, and the fused
Measurements are downgraded to estimated with the reason. Fusing silently
would produce a false arithmetic intensity wearing the face of an exact
measurement, the worst possible outcome for a user who paid for several
executions. One invocation of `nunatak run` stays a single Run whatever
the number of passes, and every Measurement keeps its pass of origin.

Collection at scale happens on two levels. Spotting an imbalance needs
only per-rank aggregates - time, cycles, instructions, MPI volumes -
which is counting: a few dozen bytes per rank, constant cost.
Attributing counters to Hotspots needs sampling, and that is what is
expensive. The counting layer therefore covers every rank, the sampling
layer a subset - one rank per node plus rank 0 - beyond a threshold of
around 64 ranks, below which everything is sampled. Hotspot-level
Measurements on unsampled Loci are unavailable, never extrapolated.

macOS offers no event-triggered sampling, kperf having been dropped from
the nominal path earlier. The nominal mode there is temporal sampling -
`xctrace` and its Time Profiler when Xcode is present, the base system's
`/usr/bin/sample` otherwise - completed by `powermetrics` for per-process
aggregates. Raw counters per Hotspot are unavailable and the roofline
stays estimated. kperf remains an expert backend, opt-in, never
automatic.

The order of sacrifice is fixed and documented, for when budget,
available counters and duration conflict: time per Hotspot and per-rank
aggregates first, then memory traffic which settles memory-bound, then
FLOPs per precision which completes the roofline, and last the cache
levels, the per-kernel GPU detail and the assembler. Without that order,
the collector's configuration would silently decide what the user loses.
