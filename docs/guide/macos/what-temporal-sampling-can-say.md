# What temporal sampling can say

On Linux a sample is triggered by an event: every 4,999,999 retired
FLOPs, the hardware interrupts and nunatak learns which address was
executing. macOS exposes no such mechanism to a user-space tool, and no
per-Hotspot counter event either. Sampling is therefore temporal - a
timer fires, the leaf address is recorded - and that single difference
decides everything else on the platform.

## A time profile is still a profile

What a timer answers is the question most readers arrive with: where does
the time go. The shares are real, the line-level attribution is real, and
the call stacks come with every hit rather than depending on how the
application was compiled.

What a timer cannot answer is how much work happened while the time
passed. There is no FLOP count and no DRAM byte count per Hotspot, so
there is no achieved rate and no roofline placement. The report says so
in the place where the placement would be - `no placement: no flops_dp
raw counter in this Run` - rather than leaving an empty cell for a reader
to fill with an assumption.

## The machine code fills part of the hole

The static loop analysis needs no counter: it disassembles the hot loop
and counts what one iteration contains. On macOS that path is Xcode's
own llvm-objdump over Mach-O, with function extents from `nm`'s symbol
starts, and an aarch64 classifier that reads NEON - `fmla.2d` is two
lanes times two FLOPs, exactly as an x86 FMA counts.

So a macOS report carries FLOPs per iteration, bytes per iteration, the
vectorization ratio and its width, and the L1 arithmetic intensity they
imply. That is what the code demands of the machine. What it is not is
what memory served, which is the number a DRAM counter would have given:
the pair of intensities that makes cache reuse visible on Linux has only
one half here.

The Linux exclusion of llvm-objdump does not apply. It names an ELF
mechanism - separate debug files whose empty sections that tool reads
instead of the library's code - and Mach-O has no counterpart. Refusing
it here for symmetry would have cost macOS its loop analysis for a
failure that cannot happen.

## Two rungs, and a counter that says which

xctrace's Time Profiler samples Running threads, so its counter is
`cpu-clock`: time on a CPU. `/usr/bin/sample` samples every thread,
blocked ones included, so its counter is `wall-clock`: time on the
clock. Those are different quantities and they are named differently
rather than both being called "time".

The distinction matters the moment a program waits. A thread blocked on
I/O for a second is a second of `wall-clock` and no `cpu-clock` at all,
and a reader who compares the two rungs without noticing would read a
disappearing bottleneck.

## Names come from atos, and its limits are the platform's

Xcode ships no llvm-symbolizer, so `atos` is the nominal symbolizer:
inline chains with `-i`, and the function anchor from `nm`'s symbol
starts, because Mach-O carries no symbol sizes - a function's extent runs
to the next symbol.

An address outside every symbol comes back as bare hex rather than named
after its neighbour, which is the same extent rule that governs
attribution everywhere. What is genuinely lost without an installed LLVM
is the staleness fingerprint, so a macOS Run cannot tell you that a
source file changed since the build unless you installed LLVM yourself.

## Energy is an aggregate, and says whose

powermetrics is a root tool, so it rides a run only where the sudoers
policy allows it - a site decision, exactly like perf's paranoid level on
Linux. What it yields is three Locus-level aggregates, never per-Hotspot
values, and each carries what it actually measured: `energy_impact` is
Apple's abstract per-process number and explicitly not joules, while
`cpu_energy` and `gpu_energy` are whole-package millijoules over the
sampling window, every other process on the machine included.

The raw stream is filtered as it arrives, because a full powermetrics
sample enumerates every process on the machine - two megabytes per second
under a profiler, measured. Nothing of that reaches the Run beyond the
three aggregates.

## Calibration carries the whole roofline here

Apple Silicon exposes no rated frequency, so the theoretical table has
nothing to cross it with and produces no ceiling at all. Where a Linux
Run without a calibration still has estimated FLOP/s roofs, a macOS Run
has none: the measured ceilings are the only ones it will ever have.

The pollution signals are the same ones, read the same way - the
concurrent-load check goes through `getloadavg(3)`, which every platform
nunatak calibrates on provides. `/proc` was never the point; the load
was.
