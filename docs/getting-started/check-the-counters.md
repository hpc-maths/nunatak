# Check the counters against a rate you already know

`examples/gemm` performs exactly `2n^3` floating-point operations and
prints its own rate from a wall clock. nunatak measures that same
quantity from the hardware counters, independently. The two have to
agree. Finding out whether they do on your machine tells you how much to
believe every other FLOP figure the tool reports there.

This runs on Linux, with `perf` and a FLOP counter. macOS exposes no
per-Hotspot counter, so the check does not apply there -
[macOS](../guide/macos/index.md) says what a time profile can still say.
Every transcript below comes from one session on one machine, an AMD
EPYC 7702 with one core busy, and that session's report is published
with this page.

## 1. Run it without a profiler

```sh
make -C examples
./examples/gemm
```

```
n = 2048, 1.621 s, 10.60 GFLOP/s analytic, 17179869184 flop, checksum 404.978022
```

The flop count is not a measurement: `2 x 2048^3` is 17179869184, exactly,
on every machine. That is what makes this program a control - the
quantity is known before anything is profiled, so a disagreement can only
come from the profiler.

## 2. Run it under nunatak

```sh
nunatak run --name gemm -- ./examples/gemm
```

The program prints its own line again, and it is slower:

```
n = 2048, 4.054 s, 4.24 GFLOP/s analytic, 17179869184 flop, checksum 404.978022
```

Compare the counters against the analytic rate of this run, not of the
first one. The 1.621 s above belongs to an execution nobody measured;
the counters describe the execution that paid for them. Both lines end
on the same checksum, which is the cheap way to see that the profiler
changed the timing and nothing else.

That slowdown is one event's price. The FLOP counter takes a sample every
4999999 retired floating-point operations, and on a kernel this dense
that came to 4.054 s against 1.621 s, two and a half times the bare run,
far past the 10% of wall clock the collection budget aims at. The check below is
unaffected, both of its numbers coming from the same slowed execution,
and the figure to keep is that a FLOP-dense kernel pays more than the
budget promises.

## 3. Compare the two rates

The run closes on one finding, and it carries the rate the counters
imply:

```
summary: 1 Hotspot above the statistical floor holds 100% of the sampled time (3981 samples of task-clock over 3.99 s)
  gemm (line) - 100% of the sampled time - latency-bound
    achieved 4.3 GFLOP/s of 1.13 TFLOP/s attainable: 0.4% of the envelope
    DRAM intensity 535 flop/byte
    downgraded to estimated: demand fills only: hardware-prefetched traffic is not counted; FLOPs not split by precision on this microarchitecture; compared against the double-precision peak
```

4.3 GFLOP/s from the counters against 4.24 GFLOP/s from the program's
own clock: under 2% apart. The counter path is right on this
microarchitecture, and every FLOP figure nunatak reports on it - the
roofline placement, the arithmetic intensity, the classification that
follows - stands on the path this check exercised.

Repeat it on each machine you profile on. It costs one run, and it is the
only statement about the counters that does not come from the tool
itself.

Now read the verdict beside the name. `latency-bound`, on a kernel that
vectorizes two thirds of its floating-point work, is not credible, and
the line under it says why: 535 flop/byte, labelled estimated, because
these counters see demand fills only. The rate is right to under 2% and
the regime is wrong, about the same Hotspot, in the same three lines.
The report says which of the two carries the uncertainty, and that habit
is what this page is really teaching.

## 4. Open the report and look at the roofline

```sh
xdg-open .nunatak/gemm-*/report.html
```

The page is one file, with no server behind it, and its third level is
one Hotspot at a time. Click `gemm` in the inventory: its detail carries
the chart the rest of this page has been arguing about.

The roofline holds four things:

- this Hotspot's point, at its measured rate and its estimated
  arithmetic intensity;
- the machine's double-precision peak, as a horizontal roof - the
  1.13 TFLOP/s the summary named, measured by a calibration rather than
  read off a datasheet;
- the memory bandwidth, as a diagonal that stops at the ridge point
  rather than crossing the roof;
- the other placeable Hotspots, as pale points, for scale.

Read the vertical distance between the point and the roof above it. That
distance is the statement: what this kernel achieved, against what this
machine allows at that intensity.

The horizontal position asks for more care. It is the DRAM intensity, and
on this microarchitecture that value is `estimated`: the counters see
demand fills only, so whatever the hardware prefetched is invisible to
them. Fewer bytes counted than the kernel moved means an intensity larger
than the real one, so the point sits further right than it belongs. Its
height is untouched, and that height is the rate you just checked against
`2n^3`.

You can see it before running anything: the report of the very Run quoted
above is published with this page - <a
href="../_static/example-gemm-report.html">open it</a> - and the chart in
`gemm`'s detail is the one described here.
[Reading a report](../guide/report/index.md) is the subject that owns the
three levels.

## 5. What a disagreement means

The program's flop count is exact, so a disagreement is a statement about
the counters rather than about the profile. Two shapes, and the
[quality reference](../reference/quality.md) names both as proxies:

- counters well above the analytic rate: the event counts work the
  processor started and did not retire, or counts an operation as several
  flops. A speculative FLOP event is the usual case.
- counters well below: the event misses part of the work, FLOPs not split
  by precision or a vector operation counted once.

A Run carries the machine, the events and their scaling in its
provenance, so the Run directory is itself the report: the disagreement,
the microarchitecture it happened on, and the events that produced it
travel together.

## 6. Two figures not to read here

`0.4% of the envelope` compares one core against the whole node. The
1.13 TFLOP/s is this machine's double-precision peak across its 32
cores, and `gemm` is single-threaded. Pinning the application does not
narrow the envelope either: the Machine is snapshotted from nunatak's own
process, which stays unpinned, so the affinity mask that reaches the
application never reaches the Machine. On a serial program, read the
rate and the intensity, never the fraction.

The two arithmetic intensities answer two questions. The loop's own
demand is 42 flops per 904 bytes touched, 0.0465 flop/byte, against the
535 flop/byte the counters report. Two things widen that gap, and this
microarchitecture cannot separate them: a tiled `gemm` really does serve
most of its bytes from cache, and these counters really do miss what the
prefetcher brought in. That is why the DRAM value is labelled estimated,
and why [static loop analysis](../guide/static-loop-analysis.md) keeps
the two apart instead of averaging them into one number.

## 7. What the code says about the same kernel

The loop analysis reads `gemm`'s inner loop from the machine code and
counts, per iteration: 164 instructions, 42 FLOPs, 67% of the
floating-point instructions vectorized at 256 bits, 656 bytes loaded and
248 stored, and cycle bounds of 38.8 port-bound against 39.19 in steady
state on `znver2`.

A loop that vectorizes two thirds of its floating-point work is the one
you would expect to approach the compute roof, and that is why this
program is the control while `laplacian` - 0% vectorized, in the same
table - is the patient. The counters and the instruction stream agree
about which of the two is which, and that agreement is the second half of
this check.

## Where to go next

- [Profile a program end to end](tutorial.md), which finds a defect and
  measures its repair, on the other example program;
- [The example programs](the-example-programs.md), for what each one is
  built to prove;
- [How to read what nunatak tells you](../guide/reading-what-nunatak-tells-you.md),
  which generalises what this page did once: read what a number is worth
  before acting on it.
