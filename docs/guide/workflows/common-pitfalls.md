# Common pitfalls

Six mistakes nunatak cannot make for you, and cannot stop you from
making. What it refuses on your behalf - naming an address after the
symbol before it, fusing counters across a recompilation, accepting a
source extract that no longer matches the binary - belongs to the subject
that owns the mechanism, and is not repeated here.

## An empty cell is not a zero

**Wrong.** The DRAM traffic column is blank for `reaction`, so it moved
no memory.

**Right.** The quantity is unavailable for that Hotspot, and the
inventory says exactly that under its last row. A zero is a measurement;
a blank is the absence of one. Where a value could not be measured, the
report names the reason rather than filling the hole.

## Two Runs from different machines are not a comparison

**Wrong.** The laptop Run says 8.4 s and the cluster Run says 2.1 s, so
the change gained 75%.

**Right.** `compare` prints that pair with a `different-machines` finding
and exits 0, because a human can still read the two sides. The number it
prints is not attributable to the code. Compare Runs from one machine,
one command line and one rank count, and change one thing at a time.

## A delta smaller than its error is not a delta

**Wrong.** 1.3% faster is 1.3% faster.

**Right.** Each side of a comparison knows its own time to a sampling
error, and `compare` writes `within the sampling error of ±2.6%: not a
difference` when the change does not clear the two combined. Profile the
same unchanged binary twice to see the floor of your own workload: on
`examples/stencil` two identical Runs land 1.3% apart.

## A function-level Hotspot says nothing about a line

**Wrong.** The Hotspot is `dgemm`, so the cost is on the line the report
happens to show first.

**Right.** The resolution level printed beside the name says how far
attribution reached: `line` has a source position, `function` and
`symbol` do not, and `unresolved` has no name at all. A conclusion about
a line needs a Hotspot resolved at `line`, which means a binary built
with `-g` - the remedy sits in the same row that states the shortfall.

## A multiplexed counter is not a full count

**Wrong.** The FLOP count is what the application executed.

**Right.** When the event groups do not fit the PMU, the kernel rotates
them and each counter carries the share of the run during which it was
actually counting. Below 80% coverage the value is downgraded to
`estimated` with that share as the reason; above it, the kernel's
extrapolation over most of the run is the quantity. Exact counts are what
`--multi-pass` buys, at one extra execution per counter group.

## The Python that runs nunatak is not the Python being profiled

**Wrong.** Python frames are missing, so nunatak's own environment needs
a newer interpreter.

**Right.** They are two processes. What decides whether Python functions
appear is the version of the interpreter named in the command being
profiled: CPython 3.12 and newer publish their frames to perf, and below
that py-spy stands in and samples temporally, without hardware counters.
nunatak itself runs on 3.10 or newer and its own version changes nothing
about the measurement.
