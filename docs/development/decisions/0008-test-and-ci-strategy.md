# 0008. Test strategy: record once on hardware, replay everywhere

*Recorded 2026-08-09.*

## Context and decision

The product has to work on varied x86 and ARM CPUs, on GPUs from both
vendors, on a multi-node MPI cluster and on a Mac. No continuous
integration service provides all of that, and part of the measurements
only mean something on real hardware. The question was therefore not "how
do we test everything" but **where the frontier runs, and what we do on
each side of it**.

**The founding principle "exec and parse, never link" has a consequence
nobody had exploited**: everything nunatak consumes from the collectors
is text or files - a `perf.data`, an sqlite export from `nsys`, a CSV
from `ncu`, an mpiP report, an `xctrace` `.trace`, a Mach-O debug map. So
one can **record once on real hardware, then replay indefinitely without
it**. That is the pivot of the whole strategy.

**The recording corpus is captured, not written.** A hand-written corpus
only tests the idea one has of a tool's output, never its real output:
that is precisely the mistake that would leave a green CI over a broken
parser. It is therefore produced by a recording mode of nunatak itself,
during campaigns on real hardware.

**And a hardware campaign does not deliver a green check, it delivers the
corpus.** That is what turns rare hardware access into a durable asset:
one campaign makes the following six months of CI meaningful.

## Options considered

- **Writing the corpus by hand** from the tools' documentation: dropped,
  it would validate our reading of the formats and not the real formats.
- **No hardware CI at all**, relying on community reports: dropped,
  nothing would ever verify that the collection commands actually run.
- **Renting cloud GPU runners for every merge**: dropped for its cost,
  out of proportion with the value added over replaying the corpus.
- **Making hardware campaigns a mere regression test**: dropped in favour
  of a campaign whose output is the corpus, the only way to make rare
  access pay.
- **Asserting absolute Calibration values in CI**: dropped, the value
  *is* the machine. We assert invariants.
- **Judging the quality of the LLM's advice with a judge model**:
  dropped, it would add something non-deterministic to validate something
  non-deterministic, in a project that has made the Diagnostic's
  reproducibility its bottom line.
- **Letting the quality of a piece of advice block a merge**: dropped, it
  is reviewed by a human on a frozen set of cases at each version.

## Consequences

### The frontier

**Testable with no special hardware, therefore blocking a merge.** That
is the overwhelming majority of the code, and notably **all of what can
lie to the user**:

- every **parser** of collector output, against frozen recordings,
  versioned by detected tool version;
- the whole **attribution chain**: symbolization, the extent rule,
  inlining chains, the folding of Python interpreter frames,
  normalisation to module offsets. That is DWARF and frozen ELF or
  Mach-O, not hardware;
- the whole **deterministic analysis engine**: roofline placement,
  classification, Quality propagation along the lineage, the statistical
  floor, the "others" aggregate, the refusal to fuse across passes;
- the **report generation** and its TypeScript application, fed from a
  frozen pivot;
- the **CLI**: exit codes, propagation of the application's, `--strict`
  and its 121, the JSON outputs, the configuration cascade, medium
  detection.

**Requires real hardware, therefore cannot block a merge**: the
Calibration, whose value is the machine; the real overhead against the
10% budget; the fact that the collection commands truly run on each
platform, permissions included; multi-node MPI at scale.

### Three tiers of execution

**Tier 1 - hosted runners, blocking.** GitHub provides
`ubuntu-24.04-arm` and `ubuntu-26.04-arm` (arm64) as well as `macos-14`
and `macos-15` (Apple Silicon), and standard runner usage is free and
unlimited on public repositories: the project being BSD-3/MIT, all of
that is open to it. This tier covers far more than replaying the corpus:
**the entire wheel build matrix**, and **the whole macOS path end to
end** - the `/usr/bin/xctrace` shim without Xcode, the fallback to
`/usr/bin/sample`, `dsymutil`, the debug map pointing at the `.o` files,
`atos`.

A reserve to write into the specification: these runners are virtual
machines, where **PMUs are generally not exposed**. One verifies there
that the commands launch, that permissions are correctly diagnosed and
that outputs parse, but **not** that hardware counters return true
values. That is not a gap in the CI, it is the frontier above
reappearing.

**Tier 2 - a self-hosted runner**, a Linux workstation with real PMUs
and possibly a GPU. The only tier that verifies a counter really returns
something. Non-blocking, run at night.

**Tier 3 - periodic campaigns on a cluster**, a GENCI centre for NVIDIA
and MPI at scale, LUMI or equivalent for AMD. A few times a year, manual
or scheduled, and **their deliverable is the refreshed recording
corpus**.

### The three hard cases

- **Calibration: we test properties, never numbers.** A measured Ceiling
  never exceeds the theoretical peak of the microarchitecture table; a
  Ceiling is the **maximum** of its repetitions and never their mean; two
  successive Calibrations on the same Machine stay within a tolerance;
  the theoretical fallback fires when the kernel cannot run; the
  downgrade to estimated triggers in polluted conditions.
- **The LLM pipeline: the prompt is a pure function of the pivot**,
  therefore an artifact under snapshot test. Every change to what the
  model sees becomes a diff read in review. It is deterministic, nearly
  free, and it holds the most dangerous class of bug: sending source
  under `--no-source`, sending a Hotspot below the statistical floor,
  letting assembler through. Those three rules were guaranteed by nothing
  executable. To them are added the mandatory detection of provider
  errors and the labelling as advice. **The quality of the advice blocks
  no merge**: it is reviewed by a human on a frozen set of cases at each
  version.
- **The report**: fed from a frozen pivot, it produces deterministic
  HTML, therefore snapshots on the output, plus a few browser paths on
  the interactive parts - view substitution, `--no-source` mode, the "off
  the roofline" case - which runs on a free hosted runner. And a unit
  test on the roofline's geometry, `min(peak, bandwidth x intensity)`:
  exactly the bug introduced in the prototype, invisible when reading the
  code and obvious at render time.

### What we accept we cannot test

Written down plainly rather than passed over: the absolute accuracy of
counters on microarchitectures we do not own, the real overhead at scale,
MPI beyond what campaigns reach, the quality of the advice, and the ISAs
and `gfx` targets outside the wheel.

**These are not holes, they are the areas the product covers by honesty
rather than by tests.** `doctor` announces what it cannot do, the
Provenance records the conditions under which a number was produced, and
a motivated downgrade says why a value is uncertain. A tool that cannot
test everything has to **declare what it does not know** - and the test
strategy is the last link of that.

### Articulation with the version watch

The CI job triggered on every LLVM rc and major **is tier 1 applied to a
new tool version**: it diffs the `-mcpu` list and replays the corpus. The
same mechanism covers every orchestrated tool. The frozen-binaries corpus
and the recording corpus are therefore the project's two durable assets,
and they serve both regression testing and the watch.
