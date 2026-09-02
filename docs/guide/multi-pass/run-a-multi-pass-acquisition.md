# Run a multi-pass acquisition

Reach for it when [counter groups](../counter-groups.md) left a group out
of the single execution - single precision on Intel, memory too on
Skylake-SP - or when a multiplexed value came back `estimated` and the
number matters more than the extra run time.

```sh
nunatak run --multi-pass -- ./stencil 2048 20
```

```
collecting with perf 6.14.11 [pass 0: flops]: ./stencil 2048 20
grid 2048 x 2048, 20 steps, 0.64 s (131.8 Mcell/s), checksum 0.568601
[ perf record: Captured and wrote 0.042 MB .nunatak/stencil-mp-20260902-085345/collect/pass-0/perf.data (898 samples) ]
collecting with perf 6.14.11 [pass 1: memory]: ./stencil 2048 20
grid 2048 x 2048, 20 steps, 0.66 s (126.3 Mcell/s), checksum 0.568601
[ perf record: Captured and wrote 0.047 MB .nunatak/stencil-mp-20260902-085345/collect/pass-1/perf.data (946 samples) ]
```

Each pass announces which group it carries and each writes its own
recording under `collect/pass-N/`. The application's output passes
through on every pass, as it does on a single one.

## What the extra execution buys

Exact counts. Each group is small enough that no counter is multiplexed,
so no value carries a coverage caveat and the roofline is built from
numbers the hardware counted rather than extrapolated.

On the run above, the witness - the retired-FLOP count, replicated in
both passes - came back identical to the unit: 1,514,999,697 in pass 0
and 1,514,999,697 in pass 1, a spread of 0.00% against a 5% threshold.
That is what licenses fusing one pass's FLOPs with the other's DRAM
bytes into a single arithmetic intensity.

## Move the threshold

```toml
[passes]
witness = 0.05
```

The value that judged a Run travels inside it, so a later analysis uses
the threshold that was in force rather than today's. The
[configuration reference](../../reference/configuration.md) lists the key
with the rest of the file.

## When there is nothing to split

Three cases, each named rather than silent, all in the
[degradation catalogue](../../reference/degradations.md):

| Situation | What happens |
|---|---|
| the microarchitecture has no counter group | one time-only pass runs, `multi-pass-unavailable` |
| the launch is an MPI job | the same fallback: multi-pass does not cover MPI runs yet |
| the application exits non-zero on the first pass | the remaining passes are skipped, `passes-skipped` |

The last one is a rule about money: relaunching a failure spends the
allocation on reproducing it.
