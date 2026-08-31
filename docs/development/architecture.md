# Architecture

nunatak is an orchestrator of processes. It runs tools it did not write,
parses what they print, and turns that into one durable artifact. Every
boundary below follows from that.

`cli` is the entry point and nothing else: it parses the six verbs and
calls into the components described here. No decision lives there that a
second front end would have to reimplement.

## The one boundary that matters

**The measured pivot.** Everything upstream of it writes into it and
never reads an analysis back; everything downstream reads it and never
modifies it.

```
   collect  ->  ingestion  ->  attribution  ->  [ PIVOT ]  ->  analysis
                                                    |          explain
                                                    |          report
                                                    +--> compare
```

The rule is not decoration. It is what lets an analysis be replayed on a
six-month-old Run, a report be regenerated after an upgrade, an
explanation be regenerated without profiling again, and the whole of the
downstream be tested without hardware or a single collector installed.

The pivot holds measurements only. No classification, no roofline
placement, no advice ever enters it: they are recomputed on demand, which
is what keeps a Run analysable years later.

## Upstream of the pivot

| Module | What it does |
|---|---|
| `launch` | sees through the launcher: what `mpirun -n 8 ./solver` really runs, which is what names the Run and what `doctor` inspects |
| `rank` | the shim interposed between launcher and application, so that each rank records itself and writes home before the job's epilogue |
| `collect` | decides which collectors run, with which parameters, on which ranks, in how many passes; composes the launch environment; retrieves artifacts from every node |
| `ingestion` | one parser per tool and version. **Address normalisation happens here**: no absolute address crosses this boundary, only `(module identity, offset)` |
| `attribution` | symbolization, inlining chains, the extent rule, source resolution and its staleness check. The densest component |
| `probe`, `calibration` | our own binaries, built locally and run as separate processes |

An **adapter** knows one tool: how to detect it and its version, how to
build its command line, and what it produces. It knows nothing about the
pivot. Four exist today - `perf`, `xctrace`, `sample`, `pyspy` - and
adding one touches an adapter and a parser, nothing else.

## The pivot

`pivot.model` holds the domain classes and `pivot.persistence` writes and
reads the directory. The vocabulary of both is bound to the glossary, and
the invariants that make a Run addable - normalised addresses, no stored
aggregate, quality as the worst of its inputs - are properties of these
two modules.

## Downstream of the pivot

| Module | What it does |
|---|---|
| `analysis` | a pure function of the pivot and the Machine: roofline placement, classification, quality propagation, the statistical floor, imbalance. Persists nothing |
| `explain` | assembles a prompt that is a pure function of the pivot, drives pi as a subprocess, receives advice |
| `summary`, `report` | two renderings of one synthesis, sharing a vocabulary and a first reading level |
| `compare` | two Runs, by logical function |

`machine`, `provenance`, `config`, `console`, `corpus` and `exit_codes`
serve both sides.

## Nothing is linked

Every crossing into another ecosystem is a subprocess, and its output is
parsed.

| Crossing | Why |
|---|---|
| third-party collectors | licence, and ABI decoupling. Linking GPL code would make the combined work GPL, which the BSD-3 licence forbids |
| LLVM tooling | an external, versioned dependency, never vendored |
| our own binaries | the same principle applied to ourselves, and measurement accuracy: calibrating from inside a resident Python process would pollute the bound being looked for |
| the language model | isolation of an entire ecosystem, reached through pi |

The consequence is accepted rather than regretted: nunatak does not work
without the ability to launch processes and read what they print. It is
also what makes the recording corpus possible, and with it a test suite
that replays real tool output on any machine.

Python carries the core because nothing in it sits on a critical path:
it orchestrates, parses, and computes over aggregates. It never counts
events inside a hot loop.

## What the architecture has to keep possible

Judge any change to the shape against these:

1. **Adding a collector** touches an adapter and a parser.
2. **A new version of a tool** adds a parser without modifying the old
   ones.
3. **Replaying the downstream on recorded output** needs no hardware and
   no collector, which is why adapters must be substitutable by a source
   of recordings.
4. **Regenerating a report or an explanation** needs the Run alone,
   neither the application nor the machine that produced it.
5. **Degrading per component**: a missing collector removes
   measurements, never the run.

## What is deliberately left open

The Parquet library, the exact protocol with pi, the internal module
split, the CLI framework, and how multi-node artifacts are retrieved -
as long as the result is a single directory and the Python trampoline
maps come home before the job's epilogue.
