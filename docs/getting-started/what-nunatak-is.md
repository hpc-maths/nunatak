# What nunatak is, and is not

nunatak profiles an application without modifying it: no marker to
insert, no recompilation required. That constraint decides much of what
follows - it rules out region counting, which needs markers in the
source, and leaves event-triggered sampling as the only way to attribute
a hardware counter to a function.

Two other things set it apart. The machine's ceilings are measured
rather than read off a datasheet, so the distance between a Hotspot and
the roofline is a statement about the machine in front of you. And the
analysis is deterministic while the explanation is generated: the engine
computes the facts, the language model explains them and suggests what to
try. That frontier is absolute. The model never diagnoses, never
measures, never classifies.

## What it is not

It is not a tracer. It does not reconstruct an exhaustive trace of
execution. A stream of Events exists - GPU launches, MPI calls - and it
feeds the analysis, not a replay of the run.

It is not a correctness debugger: it measures performance, never whether
the answer is right. It is not a dashboard either. No server, no
database, no persistent history: a Run is a directory, and the only
comparison is a diff between two of them.

It does not replace [Instruments](https://developer.apple.com/xcode/) on
macOS. The macOS path serves the short development loop rather than the
reference verdict, and Instruments stays
the better tool for interactive exploration, the system timeline, I/O and
thermal behaviour.

## What it covers today

| | Covered |
|---|---|
| CPU | Linux x86-64 (Intel, AMD) and aarch64 |
| Laptop | macOS on Apple Silicon, in a [declared degraded mode](../guide/macos/index.md) |
| Distributed | MPI |
| Languages | C, C++, Fortran and Rust through DWARF; Python through [its own path](../guide/python/index.md) |

GPU profiling is designed and not built. NVIDIA and AMD have their place
in the architecture and none in a release, so nothing on this site
describes a GPU capability: the site documents what runs. The same answer
covers Windows, Intel GPUs, and the distributed runtimes other than MPI.

## Who it is for

A developer of scientific applications who can read a profile without
being a microarchitecture expert, works on a laptop and runs on a
cluster, and whose compute time is limited and paid for. Two rules follow
from that last point, and both are visible in the product: the
application is never relaunched without being asked, and what will be
missing is announced before the allocation is spent, not after.
