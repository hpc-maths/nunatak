# Classifications

A classification is the regime a Hotspot is in, stated by the analysis
engine and printed beside its name:

```
  reaction (line) - 38% of the sampled time - latency-bound
```

**A classification states a regime, never a cause.** Every entry below
says the same four things: what the verdict means, the evidence it stands
on, what it does not say, and where to look next. Each name is an anchor,
so `classifications.html#memory-bound` is where a verdict leads.

The order below is the order the engine tries them in, and the first one
that holds wins.

## imbalance

The most-loaded Locus of this Hotspot carries at least **2.0x** the time
of the least-loaded one. It is stated before any roofline placement: a
lopsided Hotspot has to be rebalanced before its position on the roofline
means anything, because that position is an average over Loci that did
not do the same amount of work.

The evidence is the ratio of the maximum over the minimum of the Hotspot's
time, per Locus, printed under the finding:
`most-loaded Locus carries 2.4x the least-loaded`.

It does not say which Locus is late, nor why, nor that the work is
divisible differently.

Look next at the per-rank table in the report and at the run's topology
line, which say whether the time is lopsided everywhere or only here.

## latency-bound

The achieved rate is below **half** of what the roofline attains at this
Hotspot's arithmetic intensity. Neither the compute peak nor the
bandwidth diagonal explains where the time went.

The evidence is the achieved rate, the attainable rate at that intensity,
and their ratio - the envelope fraction - all three printed under the
finding.

It does not name the stall. Dependency chains, cache misses, branch
mispredictions and page faults all land here. One case deserves its own
sentence: where the hardware prefetcher serves the traffic, the DRAM
counter sees demand fills only, the intensity comes out too high, and a
kernel that is in fact bandwidth-limited reads as latency-bound.

Look next at the loop facts - the cycle bounds say what the ports allow
against what the steady state reaches, and their gap is dependency - and
at the L1 intensity beside the DRAM one: a large distance between the two
is cache reuse, a small one is traffic that really did reach memory.

## memory-bound

At least half the envelope is achieved, and the arithmetic intensity is
below the machine's ridge point - the intensity where the bandwidth
diagonal meets the compute peak, `flops_dp / dram_bandwidth`. The
bandwidth is what limits this Hotspot.

The evidence is the DRAM intensity in FLOP per byte exchanged with main
memory, the achieved rate, and the two Ceilings the envelope was built
from.

It does not say which access pattern costs the traffic, nor that reuse is
available. A stencil that reads its neighbours three times and a stream
that reads each byte once produce the same verdict.

Look next at the hot loop's bytes per iteration and at the L1 intensity,
which together say whether the traffic is inherent to the algorithm or a
missed reuse.

## compute-bound

At least half the envelope is achieved and the intensity is above the
ridge point: the compute peak is what limits this Hotspot.

The evidence is the same three quantities, read on the other side of the
ridge.

It does not say the code is optimal. The peak is the machine's, reached
with the widest fused instructions in double precision; a scalar kernel
can be compute-bound at a small fraction of it. Where the
microarchitecture does not split its FLOP counter by precision, the
comparison is against the double-precision peak and the placement carries
that as its downgrade reason.

Look next at the loop facts: the vectorization ratio, the vector width,
and whether the precision the kernel uses is the precision it needs.

## When no regime is stated

A placement needs an intensity and an envelope. Where either is missing,
no classification is invented; the finding says what was missing instead:

```
  main (line) - 0.4% of the sampled time - no placement: no dram_bytes raw counter in this Run
```

The measurements are unaffected, and the Hotspot keeps its share, its
time and whatever counters the Run does carry.
