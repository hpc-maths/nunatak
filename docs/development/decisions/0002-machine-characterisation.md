# 0002. Machine characterisation: ceilings measured by an embedded microbenchmark, the profile travelling with the Run

*Recorded 2026-08-09.*

## Context and decision

A roofline means nothing unless its ceiling is reachable in practice. A
theoretical peak (`cores x frequency x SIMD width x 2`) is systematically
out of reach - AVX-512 throttling, variable turbo, cgroup limits - and a
Hotspot at 60% of the real ceiling would show at 35% of the theoretical
one: the memory-bound / core-bound classification flips on that error. A
**Machine**'s ceilings are therefore **measured empirically on the
target**, as ERT, likwid-bench, Intel Advisor and rocprofiler-compute all
do; the theoretical calculation is a fallback only, and the ceiling is
then of Quality estimated.

The measurement is done by an **embedded microbenchmark kernel of our
own** - a STREAM-style triad for bandwidths, FMA chains in per-ISA
intrinsics for the FLOP/s peaks - shipped as **precompiled wheels with
run-time ISA dispatch**, with local recompilation as the escape hatch
when the detected ISA is covered by no embedded variant. `likwid-bench`
is orchestrated as an **optional refinement** when LIKWID is present, to
sharpen the L1/L2/L3 hierarchy. On the GPU side, calibration kernels are
embedded as **PTX** compiled by the driver at run time for NVIDIA - no
toolkit required, every generation covered - and as code objects for the
common `gfx` targets on AMD. One exception to that delivery model: the
**network probe**, which cannot be precompiled and has to be built with
the site's `mpicc`.

The result is a **Machine profile** cached in
`$XDG_CACHE_HOME/profiler/machines/`, keyed by the canonical fingerprint
of the hardware **combined with the shape of the allocation** - the cores
actually visible, the affinity mask, the cgroup limits. A profile is
reused across identical nodes of a cluster, but a job that receives 8
cores of a 128-core node does not recycle the ceilings of the whole node.
The Run's manifest **embeds a full snapshot** of that profile, so the
roofline placement stays computable on another machine or years later,
and the cache is only an optimisation.

## Options considered

- **Theoretical ceilings as the nominal path** (cpuid, `nvidia-smi`,
  vendor specifications): no run-time cost, but a roofline biased by
  default, therefore a diagnosis biased by default.
- **A database of vendor specifications per model**: immediate coverage
  of common hardware, dropped for its endless maintenance - thousands of
  entries, stale at every generation - and its silence on anything
  unlisted.
- **`likwid-bench` as the nominal path**: better microarchitecture
  coverage, dropped because the nominal path would then depend on an
  external GPL package absent from macOS and rarely installed.
- **Vendoring ERT or STREAM**: proven, citable code, but ERT pulls in a
  Python driver and MPI, and a FLOP peak written in portable C stays at
  the mercy of the compiler's choices around FMA emission and unrolling.
- **A shared site cache, pre-filled by the centre's administrator**:
  pools calibration across users, dropped for v1 in favour of a single
  cache mechanism to specify, test and debug.
- **A full scaling curve** (ceilings at 1, 2, 4, 8... cores): the most
  rigorous way to detect memory saturation, dropped for its cost in
  calibration time.

## Consequences

- Calibration triggers **automatically at the first Run on an unknown
  Machine**, before the application launches: it is the only moment the
  user really owns the compute node, exclusively. `profiler machine
  calibrate` forces it, `--no-calibrate` avoids it at the price of
  estimated ceilings.
- The **budget is bounded at 60 s by default** and ceilings are measured
  **in priority order**: DRAM bandwidth and the double-precision FLOP
  peak first, since without them there is no roofline, then single
  precision, then the cache levels, then the GPU. A partial profile stays
  usable, and whatever was not reached keeps its estimated value.
- A ceiling is the **maximum of its repetitions**, never their mean: it
  is an upper bound. Signs of pollution - external load, a non-exclusive
  allocation, dispersion between repetitions, an abnormal gap from the
  theoretical value - **downgrade the ceiling to estimated** with a
  textual reason, without introducing a fourth Quality level: the
  vocabulary of ADR 0001 stays intact.
- Ceilings are measured **at the scope of the allocation**, plus a
  **single-threaded point** for scalability diagnosis. The roofline
  placement **aggregates the Measurements of every Locus of the
  allocation** before comparing: the same scope on both sides, or one
  compares one rank's performance against a whole node's ceiling.
- The theoretical fallback rests on a **table per microarchitecture**
  (FLOP per cycle per precision, SIMD width, FMA units - a few dozen
  entries that move slowly) crossed with what the system exposes at run
  time. **An unknown microarchitecture yields an unavailable ceiling**,
  never an extrapolation.
- The **network** ceiling is measured by a ping-pong probe launched with
  the user's own MPI launcher, before the application, when the Run spans
  more than one node; otherwise it is estimated from the detected
  interconnect.
- **The network probe is the only component that escapes precompiled
  delivery.** It has to be linked against the site's MPI implementation -
  a probe built against another MPI would not launch, or worse, would
  measure a different communication path than the application's. It is
  therefore **compiled locally with the site's `mpicc`** at the first
  network calibration, and the resulting binary is cached beside the
  Machine profile. The MPI compiler is discovered from the launcher seen
  in the user's command line (`mpirun`, `srun`, `mpiexec`), so that it is
  built against the same stack as the profiled application rather than
  against an arbitrary MPI on `PATH`. When no usable `mpicc` is found, or
  the build fails, the network ceiling falls back to the estimate from
  the detected interconnect and the reason is recorded - never a blocking
  failure of the Run. The cached probe binary is invalidated like the
  profile itself, plus one further criterion: a change in the detected
  MPI stack, implementation and version.
- A cached profile is invalidated by a **change of microbenchmark kernel
  version**, different kernels making ceilings incomparable. The
  frequency governor and turbo are recorded as metadata: if they changed,
  the report warns but does not recalibrate on its own. There is no
  expiry in time; `profiler machine calibrate --force` takes over.
- **macOS is not a degraded mode for calibration**: the kernel measures
  real ceilings there, in NEON. The macOS degradation established
  earlier bears on the roofline's numerator - no FLOP counter - not on
  its denominator.
- The library **stops being a pure Python package**: it ships binary
  wheels per platform, PTX, and `gfx` code objects. A direct consequence
  for packaging and for the CI build matrix.
