# The contract with the model

A language model in a profiler is where measured facts turn into
plausible sentences that nobody can check. nunatak's answer is a contract
narrow enough to state on one page: the model is given the facts the
analysis established and the source they point at, it is asked to explain
and to suggest, and everything else about the product works without it.

## The engine measures, the model explains

The role is given in full on every call, and it is the same text every
time:

```
You are the explanation layer of an HPC profiler. You receive facts a
deterministic analysis already established - a roofline placement and
quantities each labeled with its quality (measured, or estimated with
the reason) - and the source code of one hot function. Your role:
1. Explain in plain language why this function performs the way the
   facts say, for a reader without performance expertise.
2. Suggest 2 to 4 concrete optimizations, ordered by expected gain,
   each with a rough estimate of that gain and a short code sketch.
3. Never contradict the facts. When a fact limits an optimization, say
   so. Treat the reason of an estimated quantity as a caveat on any
   conclusion you draw from it.
You explain and suggest from these facts only: you never diagnose,
measure or classify. Answer in compact markdown, no top-level heading,
at most about 400 words.
```

The classification, the roofline placement and every number arrive
already established. A model asked to diagnose would be asked for exactly
the judgement the deterministic analysis exists to produce, and its
mistakes there are the least detectable by a reader.

## What the model receives, in full

One Hotspot per call, and the whole context of that call is the text
below - pi is invoked with no session, no tools, no extensions, no
skills and no context files, so nothing reaches the model that this
prompt does not carry. This is the real prompt for `laplacian` in
`examples/stencil`:

````
## Machine
- AMD EPYC 7702 64-Core Processor, 32 of 32 logical cores allocated
- ceiling dram_bandwidth: 101 Gbyte/s
- ceiling flops_dp: 1.17 TFLOP/s
- ceiling flops_sp: 2.34 TFLOP/s

## Diagnostic for `laplacian` (line level)
- share of the sampled time: 28%
- classification: latency-bound
- achieved 2.13 GFLOP/s of 1.17 TFLOP/s attainable: 0% of the envelope (estimated: FLOPs not split by precision on this microarchitecture; compared against the double-precision peak; demand fills only: hardware-prefetched traffic is not counted)
- DRAM arithmetic intensity: 96.9 flop/byte (estimated: demand fills only: hardware-prefetched traffic is not counted; FLOPs not split by precision on this microarchitecture; compared against the double-precision peak)

## Hot inner loop (static analysis of the instruction stream, insensitive to cache reuse)
- 10 instructions per iteration, 5 FLOPs
- vectorized: 0% of the FP instructions
- 40 bytes loaded, 8 stored per iteration; 0 gathers
- cycle bounds (model znver2): 2.3 port-bound, 2.5 steady state

## Samples by source line
- line 12: 0%
- line 13: 28%
- line 14: 26%
- line 15: 36%
- line 16: 10%

## Source (`/tmp/nunatak-src/examples/kernels.c`, lines 7-19)
```
 */
#include "kernels.h"

void laplacian(const double *u, double *lap, int n)
{
    for (int j = 1; j < n - 1; j++)
        for (int i = 1; i < n - 1; i++)
            lap[j * n + i] = u[(j - 1) * n + i] + u[(j + 1) * n + i]
                           + u[j * n + i - 1] + u[j * n + i + 1]
                           - 4.0 * u[j * n + i];
}

void reaction(const double *u, double *f, int n)
```

Explain this behavior and suggest optimizations.
````

Every estimated quantity carries the reason it was downgraded, in the
same parenthesis the report shows it in, because the system prompt makes
that reason a caveat on any conclusion built on the number. The answer
this prompt produced obeys it: *"The 96.9 flop/B DRAM intensity is only
demand fills (prefetch traffic is excluded), so treat it as an estimate;
it still places the loop far from the bandwidth wall."*

The prompt is a pure function of the measured pivot, so it is held under
snapshot test: any change to what the model sees is a diff read in
review.

## What it never receives

| Never sent | Why |
|---|---|
| raw assembler - x86, PTX, SASS | reading it is diagnosing, and nobody re-reads 400 lines of SASS to check a claim |
| a Hotspot below the statistical floor | it holds too little time for its samples to say anything |
| a quantity the analysis declared unavailable | an absence is the report's to state, not the model's to narrate around |
| the source of a Hotspot the Run does not carry | deprived of source, the model produces generality |

**No source, no explanation.** The Hotspot is withheld by name before
anything is sent, and the report shows its Diagnostic entire with the
reason in place of the advice: `--no-source` was active, the file was not
found, the extract was refused as stale, the Hotspot is unresolved. Vague
advice would discredit the accurate advice next to it, which is a worse
trade than a stated absence.

## The answer is advice, and is stored as such

An Explanation is not reproducible. Ask twice and the words differ, which
is the opposite of a Measurement and the reason the advice is the only
thing in a Run that is persisted rather than recomputed: it lives in its
own file, labeled advice, keyed by the Hotspot's logical identity, and
carrying the model and provider that wrote it. Advice whose author is
unknown cannot be weighed.

In the report it sits in an accent block that names that model, never in
a cell where a measurement could sit. It is rendered as the markdown it
was asked for, and escaped before any markup is produced, so nothing the
model emits becomes markup of the page.

## Two risks, two controls

Source code leaving the machine and source code sitting in a shared
report are different risks, and each has its own switch. `--no-source`
keeps the text out of the report. Consent governs what is sent to a
model, is asked once per project and provider, and is never assumed in
either direction: a provider proven local asks nothing, and a batch job
with no memorised agreement withholds the advice rather than guessing.

The one thing that cannot be split is the pair: a report built with
`--no-source` withholds the advice too, because the model saw the code
and quotes it back.
