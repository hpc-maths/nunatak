# Compare two Runs

Profile once before the change and once after, then diff the two
directories:

```sh
nunatak run --name stencil-before -- ./stencil
# edit, rebuild
nunatak run --name stencil-fixed -- ./stencil
nunatak compare .nunatak/stencil-before-* .nunatak/stencil-fixed-*
```

`--name` is what makes the pair legible three weeks later: the Run
directory is `<name>-<date>-<time>`, and `before` and `after` in a
terminal beat two timestamps.

## Read the total first, then the rows

```
compare: stencil-before-20260901-132849 -> stencil-fixed-20260901-132928
total: 8.53 s -> 6.17 s: -27.7% (significant, sampling error ±1.4%)
  update (kernels.c) 2.98 s -> 3.27 s: +9.8% (significant, sampling error ±2.7%)
  reaction (kernels.c) 3.11 s -> 2.86 s: -8.0% (significant, sampling error ±2.5%)
  laplacian (kernels.c) vanished (was 2.42 s)
Report: .nunatak/stencil-fixed-20260901-132928/compare.html
```

That is `examples/stencil` before and after the fix its own report points
at: the laplacian is computed where it is used, so one array and one pass
over the grid disappear. `laplacian` has no second side because the
function is gone; `update` grew because it absorbed that work; the run
still lost 27.7% of its time.

Ten rows are printed, heaviest side first, and a last line counts what
was left out. The whole diff is in `compare.html` and in `--json`.

## Measure the noise floor once per machine

Profile the same unchanged binary twice and compare the two Runs. What
comes back is the resolution of every comparison made on that machine
with that workload:

```
compare: stencil-a-20260902-072203 -> stencil-b-20260902-072213
total: 8.37 s -> 8.39 s: +0.3% (within the sampling error of ±1.5%: not a difference)
  reaction (kernels.c) 3.06 s -> 3.06 s: -0.1% (within the sampling error of ±2.6%: not a difference)
  update (kernels.c) 2.95 s -> 2.99 s: +1.3% (within the sampling error of ±2.6%: not a difference)
  laplacian (kernels.c) 2.33 s -> 2.32 s: -0.3% (within the sampling error of ±2.9%: not a difference)
Report: .nunatak/stencil-b-20260902-072213/compare.html
```

Nothing changed between those two Runs, and the diff says so of all four
rows. Each kernel knows its time to ±2.6% here, and the two Runs land
1.3% apart on `update`: a 1% win claimed on this workload is the sampler
being read as code. A longer Run lowers the floor, since the error falls
as 1/sqrt(n) in the number of samples.

## When the two Runs are not comparable

```
warning: not directly comparable [different-commands]: the commands differ (./stencil vs ./stencil 2048): the workloads may not be the same
compare: stencil-a-20260902-072203 -> stencil-small-20260902-072222
total: 8.37 s -> 1.73 s: -79.3% (significant, sampling error ±1.2%)
  reaction (kernels.c) 3.06 s -> 0.682 s: -77.7% (significant, sampling error ±2.0%)
  update (kernels.c) 2.95 s -> 0.476 s: -83.9% (significant, sampling error ±2.0%)
  laplacian (kernels.c) 2.33 s -> 0.56 s: -76.0% (significant, sampling error ±2.3%)
Report: .nunatak/stencil-small-20260902-072222/compare.html
```

Every row is significant and every row is meaningless: the second Run
solved a grid four times smaller. The four checks that produce such a
warning are the Machine, the command, the rank topology and the time
base; the diff is printed anyway and the exit code stays 0.

Keep a pair comparable by changing one thing: same command line, same
node, same rank count. When the change *is* the command line - a
different grid, a different rank count - the comparison to make is of
rates rather than of times, and nunatak does not make it for you.

## What a machine reads

```sh
nunatak compare before after --json
```

The payload carries every delta with its two sample counts, its combined
error and a `significant` boolean. A pipeline reads that boolean and
never the percentage; the [machine-readable
reference](../../reference/machine-readable.md) lists the fields.

## The page

Each comparison writes `compare.html` into the second Run's directory -
this Run, against that reference - and embeds exactly the JSON `--json`
prints. It reads like a report, and [the three reading
levels](../report/the-three-reading-levels.md) apply to it unchanged.
