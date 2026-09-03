# Glossary

The domain model of nunatak, and the words this project uses. It is
binding: these terms appear as they stand in the code, in the
interface, in the report and in this documentation, and the terms each
entry lists under _Avoid_ appear nowhere.

It fixes the vocabulary, never the implementation.

## How the entities relate

```
Run ─┬─ Machine (shared, cached between Runs)
     │     └─ Ceiling*         (carries a Quality)
     ├─ Provenance             (code, dependencies, effective configuration)
     ├─ Pass*
     ├─ Hotspot* ─┬─ physical identity   (native only)
     │            ├─ logical identity
     │            ├─ resolution level
     │            └─ internal detail: lines, inlining chain
     ├─ Locus*     (node > rank > thread, or node > device > stream)
     ├─ Measurement*  (Hotspot x Locus, carries a Quality, its samples, its Pass)
     │     └─ raw counter | derived metric (with its lineage)
     └─ Event*
```

Recomputed on demand and never persisted: the Diagnostic, the static loop
analysis, every aggregate across Loci. Persisted apart from the pivot and
regenerable without profiling again: the Explanation.

## Language

**Hotspot**:
The atomic unit of analysis - the thing placed on the roofline, diagnosed,
and given to the LLM. A function on CPU (DWARF symbol), a kernel grouped by
name on GPU, a frame on Python. Discoverable without instrumentation by
every collector. It carries two identities of different scopes: a
physical identity `(module build-id or LC_UUID, offset)`, which
aggregates samples inside a Run and only exists for native code; and a
logical identity `(module, demangled name, source file)`, which is
displayed, feeds the LLM, allows comparison between Runs, and transposes to
GPU and Python alike. Lines and the inlining chain are internal details of
the Hotspot, never a unit of analysis.
_Avoid_: kernel (ambiguous: reserved for the GPU sense), region, function (too CPU-specific), symbol

**Locus**:
A point in the execution topology where a Hotspot is observed, structured
in levels: node > MPI rank > thread for CPU, node > GPU device > stream for
GPU. The "where" axis of profiling.
_Avoid_: rank (a level of the Locus, not the Locus), place, worker

**Measurement**:
A value attached to a (Hotspot, Locus) couple: the DRAM traffic of function
`foo` on rank 3 thread 2. The elementary grain of the data. Aggregation
across loci (sum, mean, min/max, imbalance) is computed on demand, never
stored. A Measurement also carries what is needed to judge its own
solidity: its sample count and the relative error that follows from it, its
coverage ratio when counters were multiplexed, and its Pass of origin.
A Measurement without a Hotspot is Locus-level: a whole-Locus aggregate
from the counting layer - one rank's time, cycles, instructions, MPI
volumes - which has nothing to attribute. It is still one value at one
Locus, never an aggregation across Loci.
_Avoid_: value, data point, sample (a sample is a source of measurements, not the measurement)

**Raw counter**:
What a collector reports directly, without transformation:
`FP_ARITH_INST_RETIRED.SCALAR_DOUBLE`, `CAS_COUNT`, `dram__bytes.sum`. A
Measurement of a raw counter is always of quality "measured" (or
"unavailable" when the counter does not exist on the microarchitecture).
_Avoid_: event, hardware counter, raw metric

**Derived metric**:
A quantity computed from raw counters through a formula: arithmetic
intensity, GFLOP/s, L2 hit rate, bandwidth. It remembers its source
counters and its formula (its lineage).
_Avoid_: metric alone (always say raw or derived), KPI, indicator

**Arithmetic intensity**:
The horizontal axis of the roofline, in FLOP per byte. There are two,
never interchangeable, and confusing them is a fault. The DRAM
intensity relates FLOPs to the traffic actually exchanged with main
memory: it is measured from raw counters, it depends on cache reuse, and it
is the one of the classic roofline. The L1 intensity relates FLOPs to
the bytes requested by the instruction stream: it is derived from static
loop analysis, it says nothing about cache reuse, and it exists even where
no counter is available - which is what makes a roofline possible on Apple
Silicon. Every mention must say which one.
_Avoid_: arithmetic intensity unqualified (always DRAM or L1), AI, operational intensity

**Static loop analysis**:
The examination of the disassembled binary of a hot inner loop, without
executing it: vectorization rate and width, memory access pattern, cycle
bounds on the execution-port side and on the dependency-chain side, L1
arithmetic intensity. It produces facts, not Measurements: they have no
Locus, no sample count, and come from no collector. It carries a Quality,
which depends on how fine the scheduling model of the target
microarchitecture is.
_Avoid_: code analysis, CQA, MAQAO (the tool was set aside, its use cases were kept), dynamic analysis

**Quality**:
The confidence label of a Measurement or a Ceiling: "measured", "estimated"
or "unavailable". For a derived metric, Quality propagates automatically
along the lineage: it is the worst of its inputs (estimated FLOPs make an
estimated arithmetic intensity). Makes explicit why a number is uncertain -
imposed by macOS (no FLOP counter) and by microarchitectures with
unreliable counters.
_Avoid_: confidence, reliability, precision

**Motivated downgrade**:
The mechanism by which a nominally measured value falls back to the
"estimated" Quality, accompanied by a readable reason. It is how the system
stays honest without multiplying Quality levels: the three states never
move, only the reason varies. Situations that trigger it today: Calibration
performed under polluted conditions, counters multiplexed below the
coverage threshold, Hotspot below the statistical floor, inconsistent
passes in multi-pass mode, per-line distribution from a line table blurred
by optimization, static-loop-analysis bounds on a microarchitecture with an
approximate scheduling model. Any new approximation must attach to it
rather than invent its own vocabulary. It does not cover the two
neighbouring cases: attribution failure, which belongs to the resolution
level, and invalidity, which is refused instead of downgraded.
_Avoid_: degradation (reserved for the functional degradation when a collector is missing), warning

**Resolution level**:
How far the attribution of a Hotspot could go: "line", "function", "symbol"
or "unresolved". An attribute of the Hotspot, distinct from Quality:
when attribution fails, the Measurement stays exact - that time really was
spent at that address - and it is the identity that degrades, not the
value. It conditions what the user sees and what goes to the LLM: without
source, no Explanation.
_Avoid_: symbolization quality, attribution precision, confidence

**Pass**:
One execution of the application within a single Run. The nominal mode has
exactly one; the multi-pass mode chains several, with disjoint counter
groups, to avoid multiplexing. A Run remains one invocation of
`nunatak run` whatever the number of Passes, and every Measurement knows
which Pass it came from.
_Avoid_: run (reserved for the container), execution, iteration, replay (the replay is ncu's kernel replay, inside a Pass)

**Event**:
A timestamped fact with a duration: a GPU kernel launch, an MPI call with
its wait time and its volume. The Event stream feeds the report timeline
and the network analysis; it is distinct from the aggregated Measurements
(which feed the roofline and the diagnostic). A collector fills
Measurements, Events, or both.
_Avoid_: span, trace, sample, record

**Run**:
A profiling session - one invocation of `nunatak run -- ...`. The persisted
container of the measured pivot: its Hotspots, Loci, Measurements and
Events, plus a reference to the Machine and its Provenance. Contains no
analysis output (recomputed) and no Explanation (persisted apart).
_Avoid_: session, profile, trace, experiment

**Provenance**:
What allows a Run to be explained without replaying it: the identity of the
code (commit, clean or dirty tree, patch of uncommitted changes), the
runtime dependencies (libraries actually loaded, with their build-id), and
the build-time ones (environment modules, compilation options read from the
binary). Lives in the Run manifest, never in the measured pivot. It is
best-effort and never blocks a Run, and it is descriptive, not
certifying: it records what it observes and does not guarantee that the
binary derives from the commit.
_Avoid_: metadata, environment, reproducibility (it does not guarantee it), context

**Machine**:
The hardware a Run executes on, carrier of the roofline Ceilings. An entity
distinct from the Run, shared and cached between Runs. Its identity is not
a node but a couple hardware + allocation shape: two jobs receiving
different shares of the same node are two Machines, and a thousand
identical nodes of a cluster are one. Every Run embeds a complete snapshot
of its Machine.
_Avoid_: node (the node is a Locus level), target, host

**Ceiling**:
An upper performance bound of the Machine, reachable in practice: FLOP/s
peak per precision, bandwidth per level of the memory hierarchy, network
bandwidth. The roof of the roofline. Like a Measurement, a Ceiling carries
a Quality ("measured" when it comes from a successful Calibration,
"estimated" when computed theoretically or measured under suspicious
conditions). It holds for a given scope - the allocation's - and therefore
compares to Measurements aggregated over that same scope.
_Avoid_: peak, roofline (the roofline is the model, not the value), limit

**Calibration**:
The operation that produces the Ceilings of a Machine by running
microbenchmarks on the target. Triggered once per Machine, cached, never
replayed without a reason. A Ceiling is the maximum of its repetitions,
never their mean: we are looking for an upper bound.
_Avoid_: benchmark (the benchmark is the tool, the Calibration is the operation), measurement (reserved for the measured pivot), machine profiling

**Diagnostic**:
The deterministic, reproducible verdict produced by the analysis engine for
a Hotspot: its roofline placement (arithmetic intensity, achieved
performance vs ceilings) and its classification (memory-bound,
compute-bound, latency-bound, imbalance). Recomputed on demand from the
measured pivot + the Machine, never persisted. It constitutes the "facts" given to the
LLM.
_Avoid_: verdict, analysis, result, bottleneck (the bottleneck is a conclusion of the Diagnostic)

**Explanation**:
The advice generated by the LLM from the Diagnostic + the Hotspot's source.
Non-reproducible, persisted separately from the measured pivot and always
labeled "advice" - never mixed with the deterministic facts. Can be
regenerated without reprofiling.
_Avoid_: advice as a term (it is the display label), recommendation, opinion, LLM output
