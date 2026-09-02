# Calibrate the Machine

The first `run` on an unknown Machine calibrates it before launching the
application, which is the only moment the node is truly yours. There is
nothing to do for that to happen, and nothing to redo afterwards: the
profile is cached and every later Run on the same Machine reuses it.

## Spend the budget in a small job

A calibration takes up to 60 seconds of the allocation it runs in. At the
head of a large job that is a waste, so the verb exists to spend it in a
small one:

```sh
nunatak calibrate
```

```
calibrating Machine 0b160aed1826e329 (60s budget)
dram_bandwidth   1.335e+11 byte/s   measured
flops_dp         1.129e+12 flop/s   measured
flops_sp         2.258e+12 flop/s   measured
```

Three ceilings, in the order that matters: without DRAM bandwidth and the
double-precision peak there is no roofline, and the single-precision peak
is refinement. Run it in a job that asks for the same shape as the real
one - the same cores, the same node count - because that shape is part of
the Machine's identity.

## Reuse, and recalibrate on purpose

A second call says what it found rather than spending the budget again:

```
Machine 0b160aed1826e329 already calibrated (--force to redo)
dram_bandwidth   1.335e+11 byte/s   measured
flops_dp         1.129e+12 flop/s   measured
flops_sp         2.258e+12 flop/s   measured
```

`nunatak calibrate --force` measures again. The reason to reach for it is
that the machine changed underneath the key that identifies it - a BIOS
setting, a firmware update, a DIMM replaced - since hardware plus
allocation shape is all that key holds.

## Skip it

```sh
nunatak run --no-calibrate -- ./solver
```

The Run keeps theoretical ceilings, which are always of quality
`estimated`, and it has no memory-bandwidth ceiling at all: that one only
exists once it has been measured. Hotspots are still attributed,
classified and placed where the remaining roofs allow.

## The network roofs come from elsewhere

`network_bandwidth` and `network_latency` are measured by nunatak's own
MPI probe, not by the calibration kernel, and a run never builds it.
`doctor` does, on a login node, and caches it per MPI stack:

```
ok       network-probe      Open MPI 5.0.7: /home/ubuntu/.cache/nunatak/probes/b1d1c16c8688f9fd/probe-v1
```

Without a cached probe the Run declares `network-ceiling-unavailable` and
names `doctor` as the way forward. [The site's MPI
stack](../../deployment/mpi-stack.md) is where that gets set up, and
[profiling an MPI job](../mpi/profile-an-mpi-job.md) is where the probe
shows up in a run.

## Where the ceilings end up

In the Run, not in the cache: every Run embeds a full snapshot of its
Machine in `manifest.json`, ceilings and their quality included, so the
cache can be deleted without a single Run losing anything. The [Run
directory reference](../../reference/run-directory.md) lists the fields;
the report's roofline is the same numbers, drawn.
