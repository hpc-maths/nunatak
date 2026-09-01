# Profile an MPI job

Pass the whole launch line after `--`:

```sh
nunatak run -- mpirun -n 8 ./solver
```

nunatak splits that line at the launcher. `mpirun` and its options run
here, `./solver` runs in every rank, and both collection layers run
inside the ranks. `mpirun`, `mpiexec`, `mpiexec.hydra`, `srun`, `jsrun`,
`aprun`, `prterun`, `orterun` and `flux` are recognised as launchers,
alone or behind `numactl`, `taskset` or an environment assignment.

## Build the site's MPI pieces once

Run `nunatak doctor` on a login node, where the compilers are. It builds
the network probe and mpiP against the site's own MPI and caches both;
a run never builds either.

```
ok       network-probe      Open MPI 5.0.7: ~/.cache/nunatak/probes/b1d1c16c8688f9fd/probe-v1
ok       mpiP-build         /opt/mpiP/lib/libmpiP.so
```

A `missing` row names what the run will lack -
`network-analysis-unavailable` without a usable `mpicc`,
`mpi-analysis-unavailable` without mpiP - and
[the site's MPI stack](../../deployment/mpi-stack.md) is where those two
are provided.

## Profile the launch

The run announces what it is about to do, then hands the launcher back
its own output:

```
call stacks: fp: frame pointers kept in 91% of prologues (206 probed across 28 modules)
launching ranks (each one counting; sampling narrows to rank 0 plus one rank per node beyond 64 ranks): mpirun -n 8 ./solver
probing the network inside this allocation
residual 3.319e-02
```

The last line is the solver's. The application's stdout, stderr and exit
code pass through untouched, so `nunatak run -- mpirun -n 8 ./solver &&
post_process` behaves like the bare launch.

## Read the topology line

The summary opens on the world, right after the headline:

```
summary: 89 Hotspots above the statistical floor hold 99% of the sampled time (87003 samples of task-clock over 87.3 s)
ranks: 8 (8 sampled); busiest rank 3 at 1.00x the mean; MPI holds 37% of the time
```

How many ranks reported and how many carry Hotspots, the busiest rank's
time over the mean of all of them, and mpiP's share of MPI in the whole
run. [The two collection layers](the-two-collection-layers.md) says what
those numbers are made of, and what makes an imbalance visible in one
column rather than another.

## Choose how many ranks sample

Up to 64 ranks, every rank samples; beyond that, sampling narrows to
rank 0 plus the first rank of each node. Move the threshold in
`nunatak.toml` when a job needs Hotspots on more ranks, or on fewer:

```toml
[sampling]
rank_threshold = 128
```

The counting layer covers every rank either way. The
[configuration reference](../../reference/configuration.md) lists the
key with the rest of the file.

## Skip the network probe

```sh
nunatak run --no-calibrate -- mpirun -n 8 ./solver
```

The probe runs through the allocation's own launcher before the
application, which costs a few seconds of the allocation.
`--no-calibrate` skips it together with the machine calibration, and the
Ceilings stay theoretical.

## Check what the run declared

Ranks that measured nothing are named by number rather than passed over:
`counting-unavailable` when a node had no usable `perf`,
`counting-incomplete` when the world size announced a rank that left
nothing behind, `mpi-report-missing` when the application did not reach
`MPI_Finalize`. Each one is an entry in the
[degradation catalogue](../../reference/degradations.md), which says what
was lost and what is still measured.
