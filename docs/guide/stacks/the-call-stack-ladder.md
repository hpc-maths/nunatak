# The call-stack ladder

Three ways to walk a stack, in a fixed order, decided before the
application launches: hardware branch stacks when the processor has them,
frame pointers when the machine code keeps them, and nothing otherwise.
The order is by cost, and the decision is cold - it costs no allocation
time and it is made once.

## A rate, never a yes or no

No header and no section declares that a binary keeps frame pointers.
The only witness is the machine code, so nunatak disassembles the
prologues of a sample of functions and counts those that establish one.
What comes out is a share, and a threshold decides.

The sample is not random: functions under 64 bytes are runtime
scaffolding whose prologues say nothing about how the application was
compiled, and samples land in large functions, so the 8 largest
functions of each module are the ones probed. Each module gets one vote, which is what
keeps a large libc from outvoting the one binary being profiled, and the
worst offender is named so the answer points at something actionable.

A yes/no would have to invent the threshold anyway, and it would hide
which module dragged the answer down.

## GNU objdump, and why not the other one

The prologues are read by GNU objdump, executed and never redistributed
like every other tool nunatak orchestrates. llvm-objdump is not a
candidate, and that is a behavioural exclusion rather than a preference:
on distributions that ship separate debug files, it silently substitutes
their section content - all zeros - for the library's and reads no code at
all. A tool that answers "no frame pointers anywhere" for a perfectly
compiled system is worse than a missing tool.

## Decided once, cold, and never re-probed

The rung is settled on the orchestrating node, before launch, and the
same decision rides `perf record --call-graph` on a single process and
inside every sampling MPI rank alike. Probing per rank would multiply the
disassembly by the rank count for an answer that cannot differ: the
binary is the same one.

perf validates its options before recording, so a mode the kernel
refuses fails immediately: the recording retries without stacks
(`call-stacks-rejected`), then time-only. The application runs exactly
once whatever happens, which is the constraint every fallback here is
shaped by - a profiler that reruns a twelve-hour job to fix its own
configuration is not usable.

## `dwarf` is never chosen for you

Copying stack memory at every sample works on any binary and costs
enough to break the observer-effect budget at full rate. So it is a mode
you ask for, the sampling frequency drops to 97 Hz when you do, and the
cost is announced on the line where it is paid.

There is no silent dwarf, and no automatic promotion to it when the
ladder ends up at no stacks: a run that quietly became ten times coarser
would invalidate the comparison you were about to make against yesterday's
Run.

## What a recorded stack becomes

Stacks are aggregated by call path and persisted in the pivot, with every
frame normalised to `(module, offset)` exactly like every other sampled
address. A per-context split of a Hotspot therefore stays addable years
later, on a machine where the binary no longer exists.

Stacks never enter a Hotspot's identity. A function is one Hotspot
whatever the paths that reached it, which is what keeps two Runs
comparable when a call site moves.

The report consumes them twice. Each Hotspot's detail names its immediate
callers with their shares, which is what attaches a hot `dgemm` inside
OpenBLAS to the solver code that called it instead of leaving a Hotspot
with no source of yours in sight. And the metrics gain an inclusive
share: how much of the sampled time this function was anywhere on the
path, callers included, a recursive function counting once per path.
Callers are attributed by the same pass as the leaves, extent rule
included, so a return address in a gap keeps its honest `module+0x...`.
