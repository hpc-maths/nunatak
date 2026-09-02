# Counter groups

Time alone answers "where does it go". A roofline needs two more
quantities - floating-point operations and bytes moved from DRAM - and
those come from hardware counters that differ per microarchitecture, are
finite in number, and lie in specific, documented ways. What a Run can
say about a Hotspot beyond its seconds is decided by that hardware, and
nunatak's job is to say which of the two it got.

## Every auxiliary event rides on a fixed period

On a microarchitecture nunatak knows, FLOP counters and a DRAM traffic
event are sampled alongside `task-clock`, each with a fixed period rather
than a target frequency: one sample every 4,999,999 retired FLOPs, one
every 100,003 demand fills.

A period makes each sample worth exactly that period, so summing the
samples counts the events - measured at 99.9% of what `perf stat` reports
on the corpus machine - and it bounds the interrupt rate by construction,
which is the only overhead lever sampling has. The periods are prime, so
no harmonic of a loop can hide from the sampler.

Hardware-prefetch fill events are deliberately not in the set. Sampling
them inflates what they measure - the interrupt handler's own memory
traffic triggers prefetches, an observer effect measured at 20x on Zen 2
- and it doubles the run time. DRAM traffic is therefore demand fills
only, and every Measurement built from it says so.

## The set is bounded by the counters one thread actually gets

Four general counters on Skylake-generation cores with SMT, eight from
Ice Lake on, always enough on Zen. A fixed-period event that the kernel
rotates off its counter undercounts silently, which is worse than not
counting at all, so the single execution's set never exceeds that
budget.

Where the budget cannot hold a whole semantic group, the group is absent
from the single execution and arrives with `--multi-pass`: single
precision everywhere on Intel, memory too on Skylake-SP. Absence with a
remedy, never a truncated group wearing `measured`.

## Absences are choices, not oversights

| Microarchitecture | What is attributed | What is not, and why |
|---|---|---|
| AMD Zen 1 | FLOPs, all precisions | no fill-source breakdown exists in its kernel table, so no per-core DRAM traffic |
| AMD Zen 2 to Zen 5 | FLOPs, all precisions, and demand DRAM fills | no precision split: Zen 5's selectors overlap in ways no machine has settled |
| Intel Skylake to Granite Rapids | FLOPs per precision, retired L3-miss loads as the DRAM proxy | the uncore memory controllers count per socket and cannot be attributed to a Hotspot |
| Intel Haswell, Broadwell | memory traffic only | those cores retired their FLOP counters; they returned with Skylake |
| Intel Alder Lake, Raptor Lake | nothing beyond time | the E-cores expose no FLOP event, and a set counting on half the cores would undercount under `measured` |
| Arm Neoverse V1, N2, V2 | the SVE/fixed FLOP pair, last-level read misses as the DRAM proxy | write traffic exists only on the interconnect's per-socket PMU; the events are speculative, not retired |
| Arm Neoverse N1 | memory traffic only | no FLOP event of any kind, and guessing lanes from NEON instruction counts is not a measurement |
| anything else | time | an unknown microarchitecture gets no group, and the placement stays `unavailable` with its reason |

The Zen 2 set is validated against real PMUs on the nightly machine. The
Intel and Neoverse event names come from the kernel's own tables and have
not met real hardware yet; a kernel that does not know them degrades the
run to time-only rather than guessing.

## Honesty travels with the numbers

Three of those rows produce a quantity that is true about something
narrower than what a reader would assume, and each says so in the
Measurement's own downgrade reason: demand fills on Zen count no
prefetched traffic, retired L3-miss loads on Intel count no stores and no
prefetches, and Neoverse's FLOP events count speculatively executed
operations rather than retired ones.

Where FLOPs are not split by precision, a placement against the
double-precision peak carries that as its reason too. None of this is
hidden in a footnote: the reason rides the number into the terminal, the
report and the model's prompt, so a conclusion built on it inherits the
caveat.

## Multiplexing is measured, then judged

When more events are enabled than the PMU has counters, the kernel
rotates them and reports each counter's coverage - the share of the run
during which it was actually counting. A multiplexed value stays
`measured` while its coverage clears 80%, because the kernel's
extrapolation over most of a run is still the quantity, and is downgraded
below it with the numbers in the reason:

```
counters multiplexed: coverage 63% below the 80% threshold
```

Downgrading everything multiplexed would paint a report uniformly grey
and strip the label of its power to discriminate. The coverage itself
rides every Measurement into the Run whichever side of the threshold it
falls on, so a reader who distrusts 81% can see it.
