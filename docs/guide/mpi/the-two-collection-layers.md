# The two collection layers

An MPI launch starts one launcher, where nunatak runs, and its ranks
wherever the scheduler placed them. Both collection layers live inside
those ranks, and they have two different costs.

## Attribution costs per rank, aggregates do not

| Layer | What it gives | Cost | Scope |
|---|---|---|---|
| **Counting** | per-rank aggregates: time, cycles, instructions, and mpiP's MPI time and volumes | constant, a few dozen bytes per rank | **every** rank |
| **Sampling** | Counters attributed to Hotspots | proportional to the ranks that do it | all of them below the threshold, a subset beyond |

The counting layer has nothing to attribute and produces no Hotspot.
It is what reveals load imbalance and the MPI share, and it is why a
large part of a run's time can carry no Hotspot without anything being
missing.

The MPI half of the counting layer comes from **mpiP**, preloaded
into every rank with `LD_PRELOAD` - appended to whatever the site
already preloads, and the application is never recompiled. Its report
becomes three per-rank Measurements: `mpi_time` and `app_time`, mpiP's
wall-clock view of each rank, and `mpi_sent_bytes`.

## Beyond the threshold, sampling narrows to one rank per node

Up to `sampling.rank_threshold` ranks - 64 by default - every rank
samples. Beyond it, or when the runtime publishes no world size,
sampling narrows to rank 0 plus the first rank of each node: Hotspots
stay attributable everywhere the code runs, at a cost that stops growing
with the job.

What the other ranks lose is stated rather than filled in. Their
Hotspot-level Measurements are `unavailable`, **never extrapolated** from
a sampled neighbour, and the summary names them. Eight ranks on one node,
with the threshold lowered to four, leave one sampled rank and seven
declarations:

```
ranks: 8 (1 sampled); busiest rank 1 at 1.01x the mean; MPI holds 38% of the time
  - 7 ranks not sampled (1, 2, 3, 4, 5, 6, 7): their Hotspot measurements are unavailable, never extrapolated
```

## Nothing samples around the launcher

A `perf record` wrapped around `mpirun` would hold the same physical
counters as the ranks and corrupt what they measure - a fact measured on
Zen 2, not a precaution. The launcher therefore runs bare, and each rank
collects itself.

For the same reason a sampled rank does not also count: a second `perf`
around it would compete for the same counters, and its time aggregate is
recoverable from its own samples.

## The shim runs inside the rank, between the launcher and the application

`mpirun -n 8 ./solver` becomes `mpirun -n 8 <shim> ./solver`. Neither the
launcher nor the application is modified, and the shim is transparent in
the three ways that decide whether an MPI application still runs: it
propagates the exit code, it leaves stdout and stderr alone, and it hands
the application every descriptor the launcher opened. MPICH and Intel MPI
pass each rank its PMI channel as an inherited descriptor, and a shim
that closed it would fail `MPI_Init` before the application started.

A launcher whose application cannot be resolved is left alone: nunatak
wraps a launch it understands rather than guessing which token is the
binary.

## Each rank writes home before it exits

Artifacts land under `collect/rank-<n>/` in the Run directory, which is
on the shared filesystem, so the retrieval happens while the allocation
still exists rather than after the job epilogue has reclaimed the nodes.
A Run stays [one directory](../../reference/run-directory.md) whatever
the number of ranks and nodes.

A rank that measured nothing is declared by number:
`counting-unavailable` for a node with no usable `perf`,
`counting-incomplete` for a rank the world size announced and that left
nothing behind. Silence about a missing rank would read as "nothing ran
there".

## A waiting rank is not an idle processor

The imbalance factor is the busiest rank's time over the mean of all of
them. It is stated, never judged: the per-Hotspot Diagnostic is where a
regime is named.

Where the MPI runtime waits by spinning, which is Open MPI's default, a
rank that arrives early spends processor time inside the wait and the
per-rank times stay flat. On a Jacobi solver whose grid rows split
unevenly over eight ranks, all eight spent 10.9 s and the factor read
1.00x, while mpiP's MPI time per rank ranged from 0.25 s to 6.6 s. The
imbalance was real and the column that carried it was the MPI time,
which is why the report's rank table holds both.
