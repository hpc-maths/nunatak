# Example programs

Two small programs, built for two different purposes.

```sh
make
./stencil
./gemm
```

They need a C compiler and nothing else. `-march=native` means they are
built for the machine they run on.

## `stencil`, to learn on

Reaction-diffusion on a 4096 x 4096 grid, sixty explicit time steps,
around four seconds. Three kernels of different character, each in its
own translation unit so the compiler cannot inline them into the driver
and a profiler has something to name:

- `laplacian`, a 5-point stencil, bandwidth-bound;
- `reaction`, a degree-4 polynomial per cell, compute-bound;
- `update`, an axpy over three arrays, bandwidth-bound.

The three come out at roughly a third of the sampled time each.

**It carries a defect on purpose.** `laplacian` and `update` sweep the
grid twice, through a `lap` array that exists only to carry values from
one to the other. Computing the laplacian where it is used removes that
array and one pass over it: the same number of floating-point
operations, half the traffic. Measured on an EPYC 7702, one core: 4.51 s
before, 3.45 s after, a gain of 23.5%.

## `gemm`, to check nunatak against

Tiled `C = A * B`, n = 2048, double precision. It performs exactly
`2n^3` = 17.18e9 floating-point operations, so it prints its own GFLOP/s
from a wall clock:

```
n = 2048, 1.554 s, 11.06 GFLOP/s analytic, 17179869184 flop, checksum ...
```

**nunatak measures the same quantity independently, from the hardware
counters, and the two must agree.** On an EPYC 7702 they do: 4.17
GFLOP/s analytic against 4.25 measured, under 2% apart, on a run under
the profiler.

A disagreement is not a bad profile. It means the counter path is wrong
for that microarchitecture, and that is what this program is for.

The kernel is built at `-O3` rather than the `-O2` the tutorial teaches:
at `-O2` gcc leaves the inner loop scalar and the kernel runs at a
quarter of the speed, which makes it useless as a point of comparison
against a known peak.

## What these are not

They are not fixtures. `corpus/binaries/` freezes binaries so that real
tools can be run against known ground, and `corpus/recordings/` freezes
tool output so parsers can be replayed without the tools. Those are
written to be stable; these are written to be read.
