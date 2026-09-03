# 0001. The pivot data model: columnar Parquet, the measured pivot kept apart from the analysis

*Recorded 2026-07-23.*

## Context and decision

Every heterogeneous collector - perf, nsys/ncu, rocprofv3, mpiP, the perf
trampolines - converges on a single pivot. That pivot holds measured data
only: Hotspots (the atomic unit: a CPU function, a GPU kernel, a Python
frame), observed at Loci (node > MPI rank > thread, or node > device >
stream), carrying aggregated Measurements and a stream of timestamped
Events, plus a reference to the Machine that holds the roofline ceilings.
The roofline placement and the deterministic Diagnostic are recomputed on
demand from that pivot; the LLM's Explanation is persisted separately and
labelled advice. The pivot is persisted as Parquet - Measurements and
Events, columnar - plus a JSON manifest describing the Run and embedding
a full snapshot of the Machine. Joins happen on the fly through DuckDB,
with no server.

> Amendment (ADR 0002): the manifest originally *pointed at* the Machine.
> Since the roofline placement is recomputed on demand, a Run deprived of
> its Ceilings stops being analysable, so the manifest embeds the full
> Machine profile and the calibration cache becomes an optimisation and
> nothing more.

## Options considered

- SQLite: natural relational joins and one portable file, but weaker on
  large Event volumes and on the massive columnar reads of distributed
  runs.
- Parquet with an SQLite index: the fastest at scale, dropped for v1
  because it means keeping two formats consistent.

## Consequences

Every Measurement carries a Quality - measured, estimated, unavailable -
which propagates automatically along the lineage of derived metrics.
macOS forces that constraint, having no FLOP counter, and so do the
microarchitectures with unreliable counters: Haswell, Sandy Bridge,
E-cores, Zen 2 and Zen 3.

The analysis engine can be improved and re-applied to an existing Run
without profiling again. The boundary between deterministic facts and
generated advice is material, all the way down to the disk. And
aggregation across Loci - sum, mean, imbalance - is always computed on
demand, never stored.
