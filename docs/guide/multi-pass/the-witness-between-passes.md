# The witness between passes

Two executions are not one execution. Fusing a quantity measured in the
first with a quantity measured in the second is exact only if the
application did the same work both times, and nothing about a job
guarantees that. The witness is how a Run finds out, and what it finds
out decides whether a fused number is `measured` or `estimated`.

## Rerunning is not the tool's decision

`nunatak run` executes the application once. When a counter group does
not fit alongside the others, the kernel multiplexes and the value comes
back with its coverage, or the group is simply absent - and either way
the allocation is spent once.

`--multi-pass` is the expert opt-in that trades allocation time for exact
counts. Relaunching an application inside a job the user pays for is not
a decision a profiler takes on its own, which is why there is no
heuristic that promotes a run to several passes.

## One measurement concern per pass

The groups are semantic rather than a packing of whatever fits: `flops`
and `memory` on Zen and Neoverse, `flops_dp`, `flops_sp` and `memory` on
Intel. Each is small enough that no counter is ever rotated off its
register.

Packing the events greedily instead would produce passes that mix
concerns, and a value would then be exact or multiplexed depending on
which pass happened to hold it - the sort of variation that makes a
report impossible to reason about.

## Why the witness is not the clock

A witness has to be work-proportional. Time and cycles are not, and both
were measured failing on the corpus machine: the same work took 69% more
cpu-seconds on a first pass, the frequency governor ramping up, and a
memory-bound run cost 4.8e9 then 6.9e9 cycles back to back. Either would
have condemned honest passes as inconsistent.

The witness is therefore a retired count: retired FLOPs on Zen, retired
instructions on Intel - on their dedicated fixed counter, which no group
competes for - and on Neoverse, the one architectural, non-speculative
count those cores offer. On deterministic work it agrees to the unit
rather than to a percentage.

On Zen, an application with no floating point gets a vacuous witness, and
that is the honest amount of evidence available rather than a failure:
the instruction witnesses of Intel and Neoverse have no vacuous case.

## Disagreement downgrades every fused quantity

The witness is summed per pass and its spread compared to the threshold.
Within it, cross-pass quantities are exactly what they claim. Beyond it,
the application did different work in different passes - a convergence
criterion, dynamic scheduling, non-deterministic MPI - and every fused
quantity becomes `estimated` with the reason:

```
fused across passes that disagree: the witness (flops) moved by 12%
between passes, beyond the 5% threshold
```

The run declares `passes-inconsistent` alongside it. Fusing silently
would produce a wrong arithmetic intensity wearing the face of an exact
measurement, which is the worst outcome available to a user who paid for
several executions. A quantity measured entirely within one pass is
untouched by any of this.

## A recompilation mid-run is an invalidity

A module whose build-id changed between passes was rebuilt while the Run
was in progress. That is not an uncertainty to downgrade: the two passes
measured different machine code, and no threshold makes them comparable.

Such Hotspots keep separate physical identities, are presented per pass,
and are never fused and never placed - `module-recompiled-between-passes`
says so. Comparing two versions of a program is two Runs, and
[comparing two Runs](../compare/index.md) is the verb for it.

## It is still one Run

Every Measurement keeps the pass it came from, each pass is its own entry
in the manifest with its own exit code and collectors, and a counter
replicated across passes counts only its reference pass in every
analysis - so the seconds stay one execution's worth rather than two.

One directory, one report, one thing to archive. The passes are visible
inside it for whoever wants to audit them, and invisible to whoever just
wants the roofline.
