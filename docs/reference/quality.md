# Quality

Every Measurement and every Ceiling carries one of three labels. They say
how much a number can be trusted, and nothing else.

| Value | Meaning |
|---|---|
| `measured` | it comes from a raw counter, or from a successful calibration |
| `estimated` | a motivated downgrade, or a theoretical model |
| `unavailable` | the quantity does not exist here, and that is not zero |

A derived quantity's Quality is the worst of its inputs, propagated
along the lineage and never set by hand. A number displayed `measured` is
measured end to end.

`estimated` always carries its reason, and the reason is reachable
wherever the value appears. The label alone is useless: it says a number
is uncertain without saying what to do about it.

What downgrades a value today:

| Situation | |
|---|---|
| multiplexed counters | coverage below `thresholds.coverage` |
| a polluted calibration | dispersed repetitions, concurrent load, a kernel built without SIMD, a value above the theoretical peak |
| a Hotspot below the statistical floor | too few samples for the relative error to mean anything |
| inconsistent passes | the witness group disagreed across a multi-pass run |
| a theoretical ceiling | no calibration has measured this Machine yet |
| static loop analysis | a model of the machine code, never a measurement of the machine |
| a proxy counter | DRAM traffic counted from demand fills, speculative FLOP events, FLOPs not split by precision |

`unavailable` is written, never left as an empty cell and never rendered
as zero. A quantity that was not collected and a quantity that is zero
are different statements, and only one of them is a measurement.

Quality is not the [resolution level](resolution-levels.md): one is about
a number's uncertainty, the other about a Hotspot's identity. When
attribution fails the Measurement stays exact, and its Quality stays
`measured`.
