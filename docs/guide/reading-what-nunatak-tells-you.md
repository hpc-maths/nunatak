# How to read what nunatak tells you

A profiler that is wrong without saying so is worse than no profiler at
all: it sends its user to optimise the wrong loop for three weeks.
Everything on this page follows from that, and every other page in this
guide assumes it.

## Four registers, never confused

Four different things can go wrong, and they get four different
treatments. Mixing them is a design error, not a presentation detail.

| Register | What is at stake | The mechanism | An example |
|---|---|---|---|
| **Quality** | a value's **uncertainty** | `measured`, `estimated`, `unavailable`, with a motivated downgrade | counters multiplexed below the coverage threshold |
| **Resolution level** | a Hotspot's **identity** | `line`, `function`, `symbol`, `unresolved` | a stripped binary, an address in a gap between symbols |
| **Degradation** | a **capability** that is absent | named, announced before the run, with the way forward | no frame pointers, therefore no inclusive time |
| **Invalidity** | an operation that **means nothing** | refusal, never a downgrade | fusing passes whose binary changed |

The boundaries matter in both directions. When attribution fails, the
Measurement stays exact: that time really was spent at that address, and
downgrading its Quality would spend a label built to speak about numeric
uncertainty on a situation where no number is in doubt. Symmetrically,
fusing one pass's FLOPs with another's memory traffic after the code
changed does not produce an imprecise arithmetic intensity; it produces
one that describes nothing. That is an invalidity, and an invalidity is
refused.

## An estimate always carries its reason

A nominally measured value falls back to `estimated` **with a readable
reason**. The three Quality levels never move; only the reason varies, so
every new approximation attaches to them rather than inventing its own
vocabulary.

What triggers a downgrade today: a calibration run in polluted
conditions, counters multiplexed below the coverage threshold, a Hotspot
below the statistical floor, passes the witness group found inconsistent,
a per-line distribution from a line table the optimiser made noisy, and
cycle bounds on a microarchitecture whose scheduling model is
approximate.

**The label without the reason is useless.** Wherever an estimated value
appears, its reason is within reach.

## Nothing fills a hole with an invention

Three applications, each binding.

**The extent rule.** An address is attributed to a symbol only if it
falls inside `[address, address + size)`. An address in the gap between
two symbols becomes an unresolved Hotspot, displayed `libfoo.so+0x3a1c`,
and is never attached to the preceding symbol. The widespread practice is
the opposite, and it is the one thing this system could do that would let
it lie with confidence.

**No extrapolation across Loci.** The Hotspots of unsampled ranks are
`unavailable`, never inferred from their neighbours.

**`unavailable` is not zero.** An absent quantity is written that way,
never as an empty cell with no explanation and never as a nil value.

## Degrade, never refuse

**Every absent external prerequisite produces a named degradation,
announced before the run, never a refusal.** That holds for call stacks,
LLVM, source, Node and pi, the collectors, `mpicc`. The Run carries
fewer measurements; it still exists, and it still says what it lost.

Two exceptions, and two only. `--strict` deliberately turns every
degradation into an error, for scripted use and performance CI. And an
invalidity, which is not a degradation.

## The engine measures, the model explains

The Diagnostic is deterministic and reproducible. The Explanation is
generated, not reproducible, persisted apart, and always labelled advice.

Three operational consequences. The model never receives raw assembler -
giving it any would be asking it to diagnose, and it is the class of
input where its error is least detectable by you. It never receives a
Hotspot below the statistical floor. And with no source there is no
Explanation: deprived of the code, the pipeline produces generalities.

## What varies is recorded

Two sites will not obtain identical results: the LLVM version, the MPI
stack, the compilation options and the configured thresholds differ. The
answer is not to freeze those variables but to write them into the Run's
provenance.

**A recorded variation is no longer a hidden variation.** The thresholds
that govern Quality are configurable, and their effective values are
written into the Run and shown in the report. A threshold can be tuned;
it cannot be tuned silently.

nunatak also never links what it orchestrates: every collector runs as a
subprocess and its output is parsed. That is a licence constraint and an
architectural one, and it is what makes the whole test strategy possible.

## Warn before, not after

You pay for your compute time. Everything that will be missing is
announced **before** the allocation is spent: a light subset of `doctor`
runs at the start of every `run`, names the degradations and the way
forward, and then continues.

That is the point of the whole page. The product cannot promise to
measure everything on every machine. It can promise that you will never
learn afterwards that it did not.
