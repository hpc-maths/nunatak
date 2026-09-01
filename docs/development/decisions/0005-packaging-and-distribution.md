# 0005. Packaging: conda-forge and spack deliver a complete product, PyPI delivers the core

*Recorded 2026-08-09.*

## Context and decision

Three earlier decisions loaded this subject without settling it. One made
the pure-Python-package assumption fall by requiring a binary calibration
kernel per ISA. Another made Node.js and pi prerequisites. A third added
a symbolizer and the LLVM pieces of the static loop analysis. The
question was therefore no longer "how do we publish a package" but "what
does the artifact contain, and who provides the rest".

**The organising principle**: the **conda-forge and spack** channels
deliver a complete product, pulling LLVM, Node, pi and py-spy as declared
dependencies; the **PyPI** channel delivers the core and declares what is
missing, with `doctor` giving the exact command to complete it. One
behaviour, two levels of completeness, no divergence of code between
channels.

**LLVM is an external dependency, never vendored.** That reverses an
earlier decision to embed the symbolizer so that behaviour would not vary
from one site to another. Two facts overturned it. First the
measurement: `llvmlite`, the closest precedent for a Python wheel
embedding LLVM, weighs **40 MB on macOS arm64 and 58 to 60 MB on
manylinux**, against the order of ten megabytes claimed without
verification. Then the reality of the field: spack is present on nearly
every HPC machine and conda-forge on most development machines, and
**both channels refuse vendoring as a matter of culture**, shipping LLVM
22 today.

The earlier argument is not abandoned, it is **redirected**: what
mattered was that a Hotspot's identity should not vary silently. The
variation is now accepted because it is **recorded in the Provenance** -
the exact LLVM version and the `-mcpu` actually chosen. A variation
written into the Run is no longer a hidden variation.

## Options considered

- **Vendoring LLVM everywhere, conda-forge and spack included**:
  consistent with the earlier decision, dropped because a package that
  embeds its own LLVM is turned away in conda-forge review, and because
  50 MB per platform for a feature half the users will never look at is a
  bad trade.
- **Vendoring only in the PyPI wheel**, conda and spack linking against
  the system: dropped, it is the worst of both worlds, two behaviours for
  one product depending on the install channel.
- **Abandoning PyPI** since spack and conda-forge carry the
  distribution: dropped, `pip install` into a venv remains everyone's
  first reflex and often the only thing possible without admin rights.
- **An LLVM floor at 17**, the version in RHEL 8: dropped after
  measurement. Zen 5, Apple M4 and Neoverse V3 only arrive in **LLVM
  19**, and Diamond Rapids in 20: a low floor degrades the tool precisely
  on new hardware, the hardware nobody is used to and whose traps are
  unknown.
- **Refusing an LLVM outside the tested window**: dropped, it would
  condemn a user of an up-to-date conda-forge to wait for our release,
  for a risk that is usually nonexistent.
- **Tying nunatak's release cadence to LLVM's**: dropped, our own
  cadence, LLVM staying a dependency like any other.
- **A hard prerequisite for Node and pi**: relaxed, see below.
- **A calibration kernel as a Python extension module**: dropped in
  favour of standalone executables, see below.
- **Building the network probe at install time**: dropped, on a cluster
  with modules the MPI at install time is almost never the job's.
- **A guided install downloading the proprietary collectors**: dropped,
  NVIDIA's EULA forbids it for `nsys` and `ncu`, and downloading tools
  onto a shared machine is not our role in any case.

## Consequences

### Channels and dependencies

- **conda-forge and spack** are the reference channels. They declare
  LLVM, Node.js, pi and py-spy as dependencies, so the user gets a
  complete product with no further step. conda-forge covers `linux-64`,
  `linux-aarch64`, `linux-ppc64le` and `osx-arm64` for LLVM (22.1.8) as
  for Node (26.6.0).
- **PyPI** is kept as the "bring your own LLVM" channel: the wheel
  contains the core and the standalone binaries, the external
  prerequisites are declared, and `doctor` explains how to get them. A
  pip user without LLVM gets a **partially functional tool from the first
  install**, which is only acceptable because `doctor` says so plainly,
  before the run, with the exact command.
- A reserve to document in the spack recipe: without an external LLVM
  declared in `packages.yaml`, `spack install nunatak` **will build LLVM
  from source**, which takes hours. `doctor` must be able to say "your
  system LLVM would do, declare it as external".

### The LLVM version, and microarchitecture coverage

- Declared dependency: **`llvm@19:`**. Measured by querying each
  branch's microarchitecture tables: LLVM 17 brings znver4,
  sapphirerapids, graniterapids, apple-m1/m2 and
  neoverse-n1/n2/v1/v2; **18** adds apple-m3; **19** adds **znver5,
  apple-m4, neoverse-v3 and neoverse-n3**; **20** adds diamondrapids.
- **LLVM 17 and 18 are tolerated, not refused**: symbolization is
  complete there, `llvm-symbolizer` being mature and the release notes
  from 18 to 22 carrying only minor fixes. Only the loop analysis is
  restricted to the microarchitectures that version knows.
- Below 17, or with no LLVM at all: **fall back on the system
  subprocess** already decided (`addr2line` on Linux, `atos` on macOS),
  and no loop analysis. Using too old an LLVM "just in case" would be
  worse, since it would yield silently degraded results where the
  fallback is at least declared.
- **The safety rule is mechanical** and rests on LLVM being able to list
  the `-mcpu` values it knows: a microarchitecture absent from the
  installed version's list leaves the cycle bounds unavailable, with
  "install LLVM 19 or newer" as the reason; a present one yields
  estimated bounds. On a Zen 5 node with LLVM 18, no false result is
  produced, only a declared absence. That rule is what makes tolerating
  old versions safe.

### Two families of result in the static loop analysis

- Depending **only on the disassembler**: vectorization rate and width,
  memory access pattern, **L1 arithmetic intensity**. These are counts
  over the instruction stream.
- Depending **on the scheduling model**: the cycle bounds, on the
  execution-port side and on the dependency-chain side.
- A consequence that corrects ADR 0004: **the L1 arithmetic intensity
  survives everywhere LLVM can disassemble**, Apple cores included,
  whose scheduling model is approximate. The rescue of the roofline on
  Apple Silicon therefore does not depend on the model's quality.
  Conversely, the disassembler itself ages: a binary compiled with the
  newest extensions (AMX, the latest AVX) is not decodable by an old
  LLVM.
- **The static analysis never produces the Quality measured**, whatever
  the LLVM version. It is a model, not a measurement of the machine.

### The version watch

LLVM publishes a major **every six months on a predictable date**:
18.1.0 in March 2024, 19.1.0 in September 2024, 20.1.0 in March 2025,
21.1.0 in August 2025, 22.1.0 in February 2026. The watch can therefore
be planned rather than suffered, and it has to be **tooled and not
declarative**, or it will not survive its second year.

- A **CI job triggered on every rc and every major** which, on one hand,
  **diffs the `-mcpu` list** against the previous version and opens a
  ticket listing the newly known microarchitectures - that signal
  triggers their addition to the test bench and the update of the
  theoretical fallback table - and on the other hand **replays the
  parser corpus** against the new version's `llvm-mca` and
  `llvm-symbolizer` output.
- A **corpus of frozen binaries**, without which none of the above is
  worth anything: with DWARF, without, stripped, heavily inlined,
  AVX-512 and SVE vectorized, together with the expected outputs. It is
  the most durable asset of this decision.
- **An open upper bound, with the tested window declared.** Beyond it,
  `doctor` **warns without refusing**: "LLVM 24 detected, not validated
  with this version of nunatak". If a parser really breaks, it breaks
  loudly, not silently.
- The same watch covers **every orchestrated tool** (perf, `nsys`,
  `ncu`, rocprofv3, mpiP, py-spy). The principle of parsers versioned by
  detected tool version had been set without saying what triggers their
  update: this is the missing piece.
- **Our own release cadence**, not aligned on LLVM's.

### Node.js and pi

They had been made hard prerequisites. They are **aligned on the common
pattern** of named functional degradation that now governs everything
else - call stacks, LLVM, source, collectors. The architecture demands
it: the deterministic Diagnostic, recomputed, is separate from the
Explanation, persisted apart and labelled advice, and the tool's factual
output does not depend on the model in any way. A hard prerequisite would
refuse installation to a user on a network-isolated cluster, who will
never be able to call a remote provider anyway, while the whole
deterministic core would be useful to them.

Concretely: declared as dependencies on conda-forge and spack, therefore
present by default on the nominal path; absent elsewhere, they produce
"Explanation unavailable: Node.js or pi not found", announced by
`doctor`, and the run proceeds.

### What the wheel contains, and in what form

- The calibration kernel and the network probe are **standalone
  executables invoked as subprocesses**, not Python extension modules.
  Three reasons, one of which is not convenience: it is "exec and parse,
  never link" applied to our own binaries; the wheel becomes
  `py3-none-<platform>`, therefore **one artifact per platform instead of
  one per (platform, Python version) pair**, exactly as py-spy's wheels
  are `py2.py3-none-*`; and a **Calibration measured in a clean process**
  gives a truer upper bound than the same measurement taken with the
  resident Python interpreter, its allocator and its GIL.
- **Python versions: CPython's upstream support**, with no house policy -
  today 3.11 to 3.14, each version dropped the day CPython drops it.
  Supporting 3.10, which dies on 31 October 2026, would mean being born
  with an already dead version.
- To write down plainly in the documentation, the confusion being
  guaranteed: **the version of Python that runs nunatak has nothing to do
  with the profiled application's**. The 3.12 threshold bears on the
  application's interpreter, the perf trampolines, not on ours.
- **NVIDIA: PTX only**, for a low floor. The driver compiles PTX on the
  fly for the architecture actually present, which covers GPUs released
  after the wheel for free. Cubins for the most common architectures can
  be added later if the first-launch compilation delay proves annoying.
- **AMD: `gfx90a` (MI200, so Frontier and LUMI), `gfx942` (MI300, so El
  Capitan and the fleet being deployed), `gfx908` (MI100).** There is no
  PTX equivalent: an unlisted target does not run at all. The rest,
  notably workstation RDNA, goes through local recompilation. The
  **generic per-family targets** recently introduced by ROCm are to be
  evaluated at implementation time; they would shorten this enumeration.
  This NVIDIA/AMD asymmetry must be documented as a choice, not suffered
  as an oversight, exactly like per-line attribution being unavailable on
  AMD.
- **CPU: run-time ISA dispatch** (`CPUID` on x86, `AT_HWCAP` on ARM).
  This is necessary and not cosmetic: the Calibration is looking for an
  upper bound, and measuring the peak with narrower instructions than the
  machine can issue would produce a false ceiling wearing the measured
  label, which is worse than an estimated one.
- An uncovered ISA: **local recompilation** from the embedded sources,
  then the **theoretical microarchitecture table** as a last resort.

### The network probe

- It links against the site's MPI stack, whose ABIs - OpenMPI, MPICH,
  Intel MPI, Cray MPICH - are mutually incompatible. **MPI 5.0, approved
  on 5 June 2025, standardises an ABI**, which will one day make
  precompilation possible: worth watching, not worth betting on, the
  implementations and then the centres taking years to follow.
- It is built **at first use, never at install time**: on a cluster with
  modules the MPI loaded at install time is almost never the job's, and
  the error would only show at run time, as missing symbols or, worse, as
  false measurements.
- The binary is **cached by the key `(implementation, version, mpicc)`**:
  a user alternating between three MPI modules gets three probes, each
  correct.
- The build happens preferably during `doctor`, therefore typically on a
  login node, some compute nodes having no compiler. The **Provenance
  records which MPI stack the probe was built against**: a network
  analysis whose underlying stack is unknown is not interpretable.
- No usable `mpicc`: **MPI analysis unavailable**, a named degradation,
  announced before the run. The rest of the profiling does not depend on
  it.
- **The mechanism also covers mpiP**: `LD_PRELOAD` avoids recompiling the
  application, not compiling mpiP, a constraint that had not been made
  explicit. We build mpiP locally, or use the site's if it exists.

### External tools, in three categories

1. **Delivered by our channels as declared dependencies**: py-spy,
   Node.js, pi, LLVM.
2. **Built locally from embedded sources**: the network probe and mpiP.
3. **Never deliverable, provided by the site**: `nsys` and `ncu`
   (NVIDIA's EULA forbids redistribution), `perf` (tied to the kernel
   version), rocprofv3 (comes with ROCm), LIKWID (GPL-3, and an optional
   refinement).

For the third category the only tenable policy is **detect, name the
capability lost, say how the site provides it** ("`module load cuda`,
then run again"). No guided install that downloads anything.

### `doctor`, the seam between installation and use

- It inventories the three categories with their versions, checks the
  permissions (perf's `paranoid` level, `ERR_NVGPUCTRPERM`) and inspects
  the target binary (`-g`, frame pointers, `-lineinfo`, `.dSYM`).
- Two methodological rules, drawn from facts verified on a machine:
  **never trust `xcrun --find`** - on a machine where `xcode-select`
  points at an uninstalled Xcode, it declares `dsymutil`, `nm` and `atos`
  absent although they are in `/usr/bin` - and **never trust `PATH`
  alone**, the Homebrew `llvm` formula being `keg_only` and therefore
  never linked. `doctor` probes the paths and **invokes** the tools.
- A **cheap subset runs automatically at the start of `run`**: no build,
  no benchmark, a few tens of milliseconds. It announces what will be
  degraded **and then continues**. That is the whole point: warn before
  burning an allocation, not after. The full `doctor` stays an explicit
  command.
- **`--strict`** turns every announced degradation into an error, and
  `doctor` can emit **JSON**. In a performance CI or a reproducible
  measurement campaign, silently getting an estimated roofline where
  measured was expected is precisely what one does not want.
