# Testing

nunatak runs tools it did not write, on hardware most contributors do not
have. That would make it untestable, except for one consequence of
"exec and parse": everything nunatak consumes from a collector is text or
a file. A `perf.data`, the text of `perf script`, an mpiP report, an
`xctrace` bundle, a py-spy stream.

> Record once on real hardware, replay for ever without it.

That is the whole strategy, and it is why the architecture requires
adapters to be substitutable by a source of recordings.

## Two corpora

They are the project's two durable assets, and they are worth more than
any test written against them.

| Corpus | What it freezes | What it serves |
|---|---|---|
| `corpus/recordings/` | the collectors' real output | every parser, the ingestion, the whole downstream |
| `corpus/binaries/` | the tools' real input: binaries with DWARF, without, stripped, heavily inlined, AVX-512 and SVE, without frame pointers | attribution, symbolization, loop analysis, and every future LLVM |

Entries are captured, never written by hand. A hand-written entry tests
our idea of a tool's output, which is exactly the mistake that leaves a
green suite over a broken parser. Every entry was produced by nunatak
itself, through `--record`.

The two are complementary in a way worth stating: recordings free the
parsers from the tools, and binaries free the tools from the machine that
built them. A new LLVM can be run against known ground precisely because
the inputs are frozen.

## The frontier

What is testable without special hardware blocks a pull request. That is
the overwhelming majority of the code, and notably all of what could lie
to a user:

- every parser, versioned by tool version;
- the whole attribution chain: symbolization, the extent rule, inlining,
  interpreter frame folding, address normalisation;
- the analysis engine: the roofline envelope, classification, quality
  propagation along a lineage, the statistical floor, the "others"
  aggregate, the refusal to fuse across passes;
- the report and its TypeScript application, fed from a frozen pivot;
- the command line: exit codes, propagation, `--strict` and its 121, the
  JSON outputs, the configuration cascade.

What needs real hardware cannot block, and that is calibration, the real
overhead against its budget, whether collection commands genuinely run
with their permissions, and MPI at scale.

## Three tiers

Tier 1 runs on hosted runners and blocks. Six combinations -
`ubuntu-latest`, `ubuntu-24.04-arm` and `macos-15`, each with CPython
3.10 and 3.14, the ends of upstream's support window. It replays both
corpora, builds the wheel, builds the report application, runs the
explanation layer against a real pi, and builds this documentation with
warnings as errors.

A reserve worth writing down: these are virtual machines, and they rarely
expose a PMU. Tier 1 checks that commands launch, that permissions are
diagnosed correctly and that outputs parse. It does not check that a
counter returns a true value.

One test launches the platform's real collector, and the rest run without
one. Wrapping a profiler around a process that exits immediately proves
nothing the corpus does not prove, costs twelve seconds a test on macOS,
and hangs often enough there to freeze a job. So the command-line tests
take the documented no-collector path, and the real launch is covered
once, by the recording test.

Tier 2 is a self-hosted machine with real PMUs, nightly and
non-blocking. It runs the hermetic suite on real Linux, then what only
hardware can verify:

```sh
pytest -m hardware      # needs real PMUs and a compiler
pytest -m llvm          # needs a real LLVM against the frozen binaries
```

Tier 3 is a campaign on a cluster, a few times a year, for NVIDIA, for
AMD, and for MPI at a scale nothing else reaches.

> A hardware campaign does not deliver a green check. It delivers a
> refreshed recording corpus.

That is what turns rare access into a durable asset: one campaign makes
the following six months of CI meaningful.

## The three hard cases

Calibration is tested by properties, never by numbers. A ceiling never
exceeds the theoretical peak of its table; it is the maximum of its
repetitions and not their mean; two consecutive calibrations stay within
a tolerance; the theoretical fallback fires; polluted conditions
downgrade.

The prompt is a pure function of the pivot, so it is captured by
snapshot. Every change to what the model sees becomes a diff read in
review, which is the only executable guarantee against the most dangerous
class of bug here: source sent under `--no-source`, a Hotspot below the
floor, assembler leaking. The quality of the advice blocks nothing.

What a snapshot cannot see is whether pi still answers the way the parser
expects. A tier-1 lane therefore runs the real pi against a stub model:
the tests start an endpoint on loopback that speaks the OpenAI protocol,
and a placeholder key is enough because the server ignores it. No API
key, no network, no model download, and what runs live is everything
except the model - the process, the hardening flags, the event stream,
the four parallel calls, the provider-error path, and the rule that a
loopback provider is local and needs no agreement. The lane opts in with
`-m pi`, and a missing pi fails it rather than skipping: a lane that
silently skips is a lane that rots.

The report is snapshot-tested on HTML produced from a frozen pivot, with
a few browser paths for what is interactive, and one unit test on the
roofline's geometry. That test was motivated by a real bug in the
prototype, where the memory diagonals crossed the compute ceiling instead
of stopping at the ridge. It was invisible to anyone reading the code.

## What we accept we cannot test

Written down rather than passed over: the absolute accuracy of counters
on microarchitectures we do not own, the real overhead at scale, MPI
beyond what campaigns reach, the quality of the advice, and the ISAs and
`gfx` targets outside the wheel.

These are not holes. They are the areas the product covers by honesty
rather than by tests. `doctor` announces what it cannot do, the
provenance records the conditions a number was produced under, and a
motivated downgrade says why a value is uncertain. A tool that cannot
test everything has to declare what it does not know, and the test
strategy is the last link of that.
