# Static loop analysis

Counters say how fast a loop ran. They do not say what the loop asked
the machine to do, and the difference between those two questions is
where an optimisation decision lives: a kernel at 3% of peak because it
is scalar needs a different action from one at 3% of peak because it is
waiting on memory.

So every measuring run also reads the machine code of its Hotspots, and
counts what one iteration contains.

## What one iteration contains

The sampled address distribution names the innermost hot loop, a
disassembler reads the physical function, and the instruction stream
between the loop's bounds is counted: floating-point instructions split
into vector and scalar, the vector width used, the bytes each iteration
loads and stores, the gathers.

Here are two loops from the shipped examples, measured on the same
machine, differing only in how they were built:

| | `laplacian`, built `-O2` | `gemm`, built `-O3` |
|---|---|---|
| instructions per iteration | 10 | 164 |
| FLOPs per iteration | 5 | 42 |
| vectorized FP instructions | 0% | 67%, 256-bit |
| bytes loaded, stored | 40, 8 | 656, 248 |
| gathers | 0 | 0 |
| cycle bounds (`znver2`) | 2.3 port-bound, 2.5 steady state | 38.8 port-bound, 39.19 steady state |

The first row of that table is a count, not an estimate of a rate, and
the `0%` in the third row is why `laplacian` gets the advice it gets: the
wide floating-point datapath of that node is idle in that loop, whatever
its DRAM traffic says.

These counts cover the CQA and [MAQAO](https://www.maqao.org/) use cases
without MAQAO, and they survive anywhere a disassembler can read the
binary.

## Two disassemblers, and one refusal that does not travel

On Linux the disassembler is
[GNU objdump](https://www.gnu.org/software/binutils/) over x86-64 AT&T
syntax, the same tool, excluded for the same measured reason, that probes
prologues for the call-stack ladder. On macOS it is
[Xcode](https://developer.apple.com/xcode/)'s llvm-objdump over Mach-O
aarch64, with function extents taken from `nm`'s symbol starts and a NEON
classifier that counts no gathers, NEON having none.

The Linux exclusion of llvm-objdump names an ELF mechanism - separate
debug files whose empty sections it reads instead of the library's code -
and that mechanism has no Mach-O counterpart. A rule copied from one
platform to the other for symmetry would have left macOS with no loop
analysis at all, for a failure mode that cannot occur there.

## Facts of the code, blind to cache reuse

Nothing derived from these counts is ever `measured`. That is an
invariant rather than a caution: a static analysis reads the code, so it
cannot know how many of those 40 bytes came from L1 and how many from
DRAM.

The report states it as two intensities side by side. The L1 arithmetic
intensity is what the code demands - FLOPs over the bytes the
instructions touch. The DRAM intensity beside it is what memory actually
served. The gap between the two is cache reuse, and reading them as one
number is the mistake the pair exists to prevent.

## Cycle bounds, and the gap that means dependencies

On top of the counts,
[llvm-mca](https://llvm.org/docs/CommandGuide/llvm-mca.html)'s scheduling
model gives two bounds per
iteration: what the execution ports allow, and what the simulated steady
state reaches. The gap between them is dependency chains speaking. On the
two loops above the gap is a fraction of a cycle - both are port-bound.
On a gather loop from the corpus it is 1.8 cycles on the ports against
103 in steady state, which is a latency chain and nothing else.

Their availability rule is mechanical, because LLVM can list the `-mcpu`
models it knows: a microarchitecture absent from the installed LLVM's
list leaves the bounds `unavailable` with `install LLVM 19 or newer` in
the reason, and the counts survive it. A model that is present yields
bounds `estimated`, naming the model used - `znver2` in the table above.

The exact listing fed to llvm-mca is persisted next to the Run's raw
artifacts, because the input of an estimate is part of explaining it.

## When there is nothing to analyse

The analysis needs the binary readable where the run executes, so a Run
replayed elsewhere carries no loop facts at all rather than stale ones. A
function whose samples fall outside every loop has nothing to analyse.
An ISA the classifier does not cover yields no counts rather than
guesses, and the fact is `unavailable` rather than transmitted as zero.

A missing disassembler is the one case declared as a degradation,
`loop-analysis-unavailable`, because it is the one a reader can act on.
