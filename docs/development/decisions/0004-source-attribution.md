# 0004. Attribution to source: the Hotspot's two identities, a declared resolution, the Run's Provenance

*Recorded 2026-08-09.*

## Context and decision

Attribution is the product's foundation and not a presentation detail:
without it there is no source to show, therefore no Explanation, no
comparison between Runs, and a roofline whose points designate nothing.
Everything below sits in the frame set by ADR 0003: two natures of
sample, event-triggered with a call stack on Linux and purely temporal on
macOS, and a counting layer which by construction has nothing to
attribute, since it produces per-rank aggregates only.

A Hotspot carries two identities. The physical one - `(build-id on Linux
or LC_UUID on macOS, offset in the module)` - aggregates samples inside a
Run and validates fusions. The logical one - `(module, demangled name,
source file)` - displays, feeds the LLM, and brings two Runs together. No
absolute address is ever persisted: normalising to a module offset at
ingestion makes ASLR and function reordering fall away by construction,
and incidentally makes ranks that loaded the same library at different
addresses converge on one Hotspot. The declaration line is an informative
attribute, never a key component: putting it in the key would flip every
function onto a new identity as soon as three lines are added at the top
of a file. The logical identity transposes unchanged to the GPU,
`(module, demangled kernel name)`, and to Python, `(.py file, function
name)`; only native code has a physical identity.

The Hotspot stays the physical function, meaning the thing with a symbol,
an extent and an address: something the user can recompile, isolate and
compare. Lines and the complete inlining chain are kept as internal
detail, never as units of analysis. An inline frame is nothing but a line
from another file.

The resolution level is an attribute of the Hotspot, distinct from
Quality. When attribution fails the Measurement is not degraded: that
time really was spent at that address, which is an exact fact. What
degrades is the identity. Confusing the two would be an error of meaning
and would dilute a label built to speak about numerical uncertainty.

The LLM never receives raw assembler, neither x86, nor PTX, nor SASS. The
transverse framing is unambiguous: the analysis engine is deterministic,
the LLM explains and suggests but does not diagnose. Sending it SASS is
exactly asking it to diagnose, and it is the class of input where its
error is least detectable by the user.

A static loop analysis of our own is added to the product, built on the
LLVM that the symbolization decision already embeds. It covers the
CQA/MAQAO use cases without depending on MAQAO.

## Options considered

- A Hotspot at line grain: dropped, a line has no stable existence under
  `-O3` and cannot be recompiled.
- A Hotspot at the innermost inline frame: appears to give the
  developer's view, dropped because it produces "`operator[]`: 40% of
  your time", which is noise wearing the face of a diagnosis.
- A Hotspot at the physical function alone, with no internal detail:
  dropped symmetrically, it announces "`operator()<Mesh, Field, 2>`: 80%"
  and teaches nothing about templated code.
- The logical identity alone: legible and stable, dropped for its
  collisions - twelve `static void helper()` fused into one.
- The physical identity alone: exact, dropped because a recompilation
  invalidates everything and forbids any comparison.
- Attributing an address to the exported symbol that precedes it, the
  widespread practice on stripped binaries: dropped, it is the one way
  this system could lie with confidence all of the time, all the time
  spent in a translation unit's `static` functions ending up glued to the
  last exported symbol before them.
- A subprocess symbolizer alone (`llvm-symbolizer` or `addr2line`
  depending on what the site installed): consistent with "exec and
  parse", dropped because a Hotspot's identity would then depend on the
  packages present on the node, and `addr2line` comes from binutils,
  therefore GPL-3, executable but never redistributable.
- `--call-graph dwarf` by default: works on any binary, dropped because
  copying 8 KB of stack per sample is on the order of 500 MB/s at 1 kHz
  over 64 threads, incompatible with ADR 0003's 10% budget.
- Fusing py-spy and perf samples into one stack on CPython older than
  3.12: dropped, two clocks and two triggers, it would be double counting
  dressed as measurement.
- Consuming Instruments' symbolization on macOS: less code, dropped
  because the XML export would have to be parsed anyway, and one would
  inherit a second provenance of attribution with inlining semantics that
  are not ours.
- Refusing the `/usr/bin/sample` mode for want of applying the extent
  rule there: dropped, a declared resolution level beats an absent path
  when Xcode is not installed.
- Giving SASS or x86 assembler to the LLM: dropped, see above.

## Consequences

### Grain and views

Attribution goes down to the line, but the line is internal detail of the
Hotspot: the roofline, the Diagnostic and the LLM work at function grain.
Under `-O3` the line table is noisy; that noise earns a motivated
downgrade bearing on the per-line distribution, not on the function's
Measurement.

The inlining chain is kept whole. The report ventilates samples by inline
frame and by line with the real source files. The LLM receives the
physical function's source plus the extracts of the hot inline frames,
without which it would be shown template call lines and asked to explain
a bandwidth.

A transverse view, time by inline frame across all Hotspots, exists as a
secondary. It catches the header routine inlined in twelve places,
invisible otherwise, and it is the only view stable across a
recompilation since it does not depend on the compiler's inlining
choices.

Call stacks serve to attach library leaves to user code - a hot `dgemm`
inside OpenBLAS would otherwise be a Hotspot with no source - to give an
inclusive time, and to reconstitute mixed Python stacks. They do not
enter the Hotspot's identity. The accepted cost: a generic `matvec`
called by three solvers fuses into one averaged roofline point. Stacks
being persisted, a per-context split stays addable without touching the
pivot.

### Resolution, and the refusal to invent

Four resolution levels: line, function, symbol, unresolved. The level is
a visible attribute of the Hotspot, and it conditions what is sent to the
LLM.

The extent rule attributes an address only if it falls inside
`[st_value, st_value + st_size)` of a symbol. An address in the gap
between two symbols becomes an unresolved Hotspot, displayed
`libfoo.so+0x3a1c`, never attached to the preceding symbol.

Debug information is looked for in this order: the binary's sections,
`.gnu_debuglink`, `/usr/lib/debug/.build-id/`, then debuginfod when
`DEBUGINFOD_URLS` is set. debuginfod is used if configured and reachable,
never required, never during the profiled execution (at analysis time
only), can be disabled, and has a short timeout. Its gain bears on
`libc`, `libmpi` and the distribution's libraries, not on the user's
code.

`doctor` inspects the target binary before consuming an allocation and
asks for what is missing: `-g` or `-g1`, `-fno-omit-frame-pointer`,
`-lineinfo` on the GPU side, `dsymutil` on macOS.

### Symbolization tooling

The nominal path is a permissive symbolizer embedded in the wheel. The
pure-Python-package assumption having already fallen, the wheel already
carries binary content; LLVM (Apache-2.0 with the LLVM exception) and the
Rust `gimli`/`addr2line` crates (MIT/Apache-2.0) are redistributable. Raw
addresses, the mapping map and the build-ids come from perf, and we
symbolize ourselves.

> **Revised by ADR 0005.** LLVM is no longer embedded but declared as an
> external dependency (`llvm@19:`), provided by conda-forge and spack.
> Two facts overturned the arbitration: the real weight of a wheel
> embedding LLVM is 40 to 60 MB and not "on the order of ten megabytes"
> as written above, and the two channels that actually carry the
> distribution refuse vendoring. This point's underlying requirement -
> that a Hotspot's identity not vary silently from one site to another -
> is met otherwise: the LLVM version and the `-mcpu` chosen are recorded
> in the Provenance.

A subprocess fallback uses what the machine offers: `llvm-symbolizer` or
`addr2line` on Linux, `atos` on macOS. The latter two are executable but
never redistributable, respectively for GPL reasons and for belonging to
Xcode.

Symbolization only covers the set of distinct addresses produced by
aggregation, a few thousand to a few tens of thousands: its cost is a
deciding criterion for none of the options.

Call stacks come in an order settled cold by `doctor`. `lbr` when the
processor offers it - some thirty frames at near-zero cost with no
compilation requirement, Intel in practice - otherwise `fp` when the
binary and its libraries keep frame pointers, probed from the prologues
of a sample of symbols, which yields a rate and not a yes or no,
otherwise no stacks at all. `dwarf` stays available on explicit demand,
with its cost announced and the sampling frequency lowered automatically.

The absence of stacks is a named functional degradation, not an error:
one loses the attachment of library leaves and the inclusive time, and
keeps the roofline whole, which depends only on the leaf's attribution.

### Python

The interpreter exposes its frames only when `PYTHONPERFSUPPORT=1` is
present in the launch environment, which `nunatak run -- mpirun python
app.py` controls without touching the code.

The `/tmp/perf-<pid>.map` files are local to each node and keyed by PID:
they must be retrieved as Run artifacts before the job's epilogue,
without which the Python Hotspots of a multi-node run are unrecoverable.
That is an orchestration constraint, not a detail.

The interpreter's own frames are never Hotspots: they are folded onto the
innermost Python frame above them, which attributes interpretation time
to the Python function being interpreted, its exact meaning. The native
leaves of extensions (numpy, pybind11, Cython) stay native Hotspots
handled by the ordinary DWARF path, with the calling Python frame visible
in the stack.

On CPython older than 3.12 and on macOS, py-spy samples temporally:
Python Hotspots exist with a complete resolution level but their raw
counters are unavailable, as on macOS in ADR 0003. Anything that writes a
perf map - Numba, a JIT - comes in through the same door with no specific
code.

### macOS

The macOS path serves the short development loop, the laptop where code
is written, and not the reference performance verdict, which is rendered
on the cluster. That framing justifies the degradations already accepted
and says where to stop: fill the same abstractions so that the Mac and
the cluster speak the same language, without trying to rival Instruments,
which will remain better for interactive exploration, the system
timeline, I/O and thermals.

`LC_UUID` replaces the build-id, in exactly the same role.

The executable contains no DWARF section (verified: `otool -l` shows no
`__debug_info`). The information lives in a `.dSYM` or in the debug map
pointing at the `.o` files (verified: `dsymutil -dump-debug-map` lists
their paths). A consequence with no Linux equivalent: a `make clean`
retroactively destroys all line-level attribution, and a binary copied
alone from another machine never had any.

`/usr/bin/xctrace` exists even without Xcode installed (verified: it is a
shim that fails on invocation). `doctor` must therefore really invoke it,
never settle for finding it on the PATH.

Stacks are free and reliable: Apple's arm64 ABI mandates keeping the
frame pointer and both samplers return complete backtraces. It is the one
point where macOS is better than Linux, and the ladder `lbr > fp >
nothing` is moot there.

With `xctrace`, samples carry addresses and the module's UUID: we
symbolize ourselves and the whole resolution scale applies. With
`/usr/bin/sample`, the output is already symbolized and aggregated and no
address is ever seen, so resolution is capped at function, with no
per-line detail and no inlining, and the extent rule is inapplicable. One
then inherits Apple's attribution, and says so through the resolution
level rather than dressing it up.

Python on macOS goes only through py-spy: `PYTHONPERFSUPPORT` writes a
file that only perf reads. py-spy requires root there (`task_for_pid`),
which meets the launch-under-`sudo` mode already accepted.

### GPU

`-lineinfo` (nvcc) or `-g` (hipcc) gives the instruction-to-line
correspondence in the cubin, which `ncu` exposes: one obtains per-line
attribution inside the kernel, including through inlined `__device__`
functions, which is the general case. Without it there is only the name:
resolution level symbol, and no extract sent to the LLM. The flag is not
required, but `doctor` asks for it before the run, its cost in
performance and size being negligible.

On AMD, instruction-to-source correlation goes through ATT, markedly less
established than the `ncu` path. In v1: kernel name and aggregated
counters, per-line attribution unavailable, the NVIDIA/AMD asymmetry
declared and not promised.

Kernels are grouped by name. The launch configuration - grid, block,
stream, size - is internal detail carried by the launch Events. The same
arbitration and the same accepted cost as for CPU call stacks:
heterogeneous launches produce an averaged roofline point.

The host-side call site is collected, since `nsys` can associate the CPU
stack that issued a launch, but bounded to a sample of launches per
kernel name, consistent with the bound already decided for `ncu` and with
the 10% budget.

### What the LLM sees, and the static loop analysis

The LLM receives the source of the physical function and of the hot
inline frames, the per-line distribution, the Diagnostic, and derived
facts stated as facts: "the loop at line 214 is not vectorized: 98% of
retired floating-point instructions are scalar", "45% of this kernel's
cycles wait on `Long Scoreboard`". Where the source counter does not
exist, the fact is unavailable and is not sent, rather than being sent
approximate. The assembler stays consultable in the report, in an
unfoldable detail view: it is data, not prompt context.

Compiler optimisation reports (`-fopt-info-vec-missed`,
`-Rpass-missed=loop-vectorize`) are accepted if already present beside
the binary or the objects, never provoked by a recompilation. They are
attached by `(file, line)` and not used when their correspondence with
the executed binary cannot be verified: a stale report declaring a loop
unvectorized while the current binary vectorizes it would be worse than
nothing.

The static loop analysis is built on the LLVM already embedded for
symbolization: a disassembler and per-microarchitecture scheduling
models. The work proper to the project is limited to reconstructing the
control-flow graph, isolating the hot inner loop - the per-line
distribution already says where it is - and interpreting the result.

Its v1 scope is the vectorization rate and width, the memory access
pattern (contiguous, strided, indirect), cycle bounds on the execution
ports side and on the dependency chain side, and the static arithmetic
intensity. The "estimated gain if the loop were vectorized" comes later,
since it means modelling a transformation rather than measuring what
exists.

LLVM's scheduling models are fine on x86 Intel/AMD and on ARM Neoverse
cores, markedly more approximate on Apple cores: cycle bounds there are
of Quality estimated, with the reason.

A crossed benefit: the static analysis gives an arithmetic intensity with
no hardware counter at all, which consolidates the estimated roofline of
macOS, where the absence of a FLOP counter had been established. But it
is a distinct quantity, at the instruction stream level (L1) and not at
DRAM traffic level. The two are never interchangeable and carry different
names.

> **Clarified by ADR 0005.** The results of the static analysis split
> into two families with different dependencies: the counts
> (vectorization, access pattern, L1 arithmetic intensity) need only the
> disassembler, while the cycle bounds need the scheduling model. The L1
> intensity therefore survives everywhere LLVM can disassemble, Apple
> cores included: the rescue of the roofline on Apple Silicon does not
> depend on the model's precision, contrary to what the previous
> paragraph suggests. When the microarchitecture is absent from the
> installed version's `-mcpu` list, only the cycle bounds become
> unavailable.

### Source, exposure and Provenance

Finding the file goes through the DWARF path as it stands
(`DW_AT_comp_dir` plus a relative path), then a correspondence supplied
by the user (`--source-map /build/x=/home/me/x`), then a search by base
name under the repository root or the current directory. On multiple
ambiguous matches, no choice is made: the Hotspot stays without source,
with the reason.

The MD5 fingerprint of the DWARF 5 line table (`DW_LNCT_MD5`, emitted by
default by clang) acts as a staleness guard. Fingerprint present and
mismatched, the source is neither displayed nor sent, and the report says
why. The same rule as for optimisation reports, the same family of
problem.

The Run embeds the extracts actually needed - the physical function's
body, the hot inline frames, a few lines of context - never whole files:
the report stays self-contained and readable in six months, and its size
and its exposure stay bounded.

Two distinct switches exist, because they are two different risks.
`--no-source` removes the text from the report, line numbers and metrics
kept, for what must leave a sensitive site. And an explicit agreement,
memorised per project, is asked at the first use of a remote LLM
provider, put bluntly: "this run will send extracts of your source code
to that provider". No agreement is asked if the provider configured in Pi
is local, which gives the clean exit for a site that can let nothing out.

No source, no Explanation. The pipeline is "deterministic facts plus
source to advice"; deprived of source it produces only generalities,
which discredits the LLM's output. The report then shows the
deterministic Diagnostic, whole, and the reason for the absence. The
intended effect: the product's most visible feature is conditioned on a
`-g` or a `-lineinfo` that `doctor` asked for before the run, which makes
the incentive legible rather than punitive.

The Provenance is an attribute of the Run, persisted in the JSON manifest
(ADR 0001) and never in the measured pivot. It has three parts. The
identity of the code: the hash of `HEAD`, clean or dirty state, submodule
state, and a patch of uncommitted modifications for every git work tree
met among the resolved sources. The run-time dependencies: the libraries
actually loaded, with path, version and build-id, obtained for free since
they are already collected to symbolize, and often the explanation of a
performance gap between MKL and OpenBLAS or between two of the site's MPI
implementations. And the build-time dependencies: `module list`,
`LOADEDMODULES`, the Spack or conda environment, and above all the
compilation options read from `DW_AT_producer`, clang keeping the
complete command line and GCC being able to through
`-frecord-gcc-switches`, knowing that `-O2` against `-O3 -march=native`
explains a good share of performance surprises on its own.

The patch obeys `--no-source` - protecting the extracts and letting the
diff through would be a gaping hole - and its size is bounded with marked
truncation.

The Provenance is best-effort and never blocking: no git repository, no
modules, the run proceeds normally. It is descriptive and not
certifying: we do not assert that the binary derives from the commit. The
only possible cross-check is the DWARF MD5 fingerprint against the
current work tree, which allows saying "the profiled binary does not
match this tree" rather than archiving a misleading patch.

### Multi-pass, and comparison between Runs

Recompiling during a Run is an accident: the purpose of Passes is to
collect disjoint counter groups on the same program. The rule, carried by
the lineage, is that a derived metric may combine raw counters from
different Passes only if the physical identity of their module is
identical across those Passes. Otherwise it is a refusal, not a
downgrade: fusing pass 1's FLOPs with pass 2's memory traffic when the
code has changed does not produce an imprecise arithmetic intensity, it
produces an arithmetic intensity that describes nothing. That is an
invalidity, not an uncertainty.

The granularity of the refusal is the module, not the Run: recompiling
one's own library between two passes must not invalidate `libmpi`'s
measurements. The Hotspots of modules whose physical identity changed are
presented per Pass, with no fusion and no roofline placement, with the
reason displayed.

Recompiling to measure a gain is two Runs. The unit of comparison between
Runs is the function in the logical sense, inlining included, and not the
physical symbol: when the compiler this time decides to inline the
function one has just optimised, its symbol disappears and its time melts
into the caller, which makes a symbol-grain comparison illegible. The
transverse view by inline frame crosses that change.

v1 delivers a minimal `nunatak compare runA runB`: a terminal summary and
an HTML diff report, with no database and no persistent history, the
latter staying out of scope. Without that command, a user who has just
recompiled compares two HTML reports by eye, doing the work the tool is
supposed to take off their hands; and the foundation is already entirely
there.

Two guards sit on the comparison. It makes sense only on an identical
Machine in the sense of hardware plus allocation shape, with an identical
rank count and identical input data, otherwise the difference is
displayed while being declared not comparable. And each Measurement's
statistical uncertainty (ADR 0003) is carried into the difference: a 3%
gain between two Hotspots at 8% relative error is not a gain, and the
report must say so.

The Provenance makes the difference legible: two Runs carry two commits
and, where applicable, two patches, so the tool can say what changed in
the code instead of noting a difference with no cause.
