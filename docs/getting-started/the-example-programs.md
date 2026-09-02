# The example programs

Two C programs live in `examples/`, built for two different purposes.
They need a compiler and nothing else, and `-march=native` builds them
for the machine they run on:

```sh
make -C examples
./examples/stencil
./examples/gemm
```

## `stencil`, to learn on

Reaction-diffusion on a 4096 x 4096 grid, 60 explicit time steps,
around four seconds of work. Three kernels of different character, each
in its own translation unit so the compiler cannot inline them into the
driver and a profiler has something to name:

- `laplacian`, a 5-point stencil, bandwidth-bound;
- `reaction`, a degree-4 polynomial per cell, compute-bound;
- `update`, an axpy over three arrays, bandwidth-bound.

The three come out at roughly a third of the sampled time each.

**It carries a defect on purpose.** `laplacian` and `update` sweep the
grid twice, through a `lap` array that exists only to carry values from
one to the other. Computing the laplacian where it is used removes that
array and one pass over the grid: the same number of floating-point
operations, half the traffic. Measured on one core of an EPYC 7702,
4.51 s before and 3.45 s after, a gain of 23.5% - large enough to clear
the sampling error of a four-second Run, which is what makes it worth
measuring rather than asserting.

## `gemm`, to check nunatak against

Tiled `C = A * B`, n = 2048, double precision, `restrict` on the three
pointers. It performs exactly `2n^3` = 17.18e9 floating-point
operations, so it prints its own rate from a wall clock:

```
n = 2048, 1.554 s, 11.06 GFLOP/s analytic, 17179869184 flop, checksum ...
```

**nunatak measures that same quantity from the hardware counters, and
the two have to agree.** On an EPYC 7702 they do: 4.17 GFLOP/s from the
program's clock against 4.25 GFLOP/s from the counters, under 2% apart,
on a run under the profiler.

A disagreement is not a bad profile: it means the counter path is wrong
for that microarchitecture, and catching that is what this program is
for.

Its kernel is built at `-O3` rather than the `-O2` used elsewhere. At
`-O2` gcc leaves the inner loop scalar and the kernel runs at a quarter
of the speed, which makes it useless as a comparison against a known
peak.

## What they are not

They are not fixtures. `corpus/binaries/` freezes binaries so that real
tools run against known ground, and `corpus/recordings/` freezes tool
output so that parsers are replayed without the tools; both are written
to stay stable. These two are written to be read, and to be changed by
whoever is learning on them.
