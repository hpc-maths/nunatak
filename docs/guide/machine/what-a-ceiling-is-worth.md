# What a ceiling is worth

A roofline is only as honest as its roof. A ceiling that cannot be
reached in practice makes every Hotspot look bad; one measured over the
wrong scope makes them look good. So a ceiling in nunatak is an upper
bound measured on the allocation it will be compared against, and it says
which of those two it failed at when it fails.

## A Machine is not a node

The identity of a Machine is a couple: the hardware, and the shape of the
allocation. Two jobs holding different shares of one node are two
Machines; a thousand identical nodes of a cluster are one.

That definition exists to make ceilings comparable to measurements. A
ceiling holds for a scope - the allocation's - and it is compared against
measurements aggregated over that same scope. Measuring on 8 cores and
dividing by a peak measured on 128 is the mistake this makes impossible,
and it is a mistake that produces a number nobody can see is wrong.

It is also why the cached profile is keyed by hardware plus allocation
shape, and why a job that asks for half a node gets its own calibration
rather than the whole node's.

## An upper bound, not an average

A ceiling is the maximum of its repetitions, never their mean: 5
repetitions of 300 ms per kernel, and the best one wins. An average would
answer a different question - what the machine typically does - and a
roofline compared against typical performance would place a perfectly
optimised Hotspot above its own roof.

The kernels run as a separate process, compiled locally with
`-march=native` (or `-mcpu=native`), never inside the Python interpreter
that runs nunatak. The interpreter, its allocator and its garbage
collector would pollute exactly the quantity being measured, which is the
peak of the machine and not the peak of a machine running a profiler.

Within the 60-second budget the order is fixed: DRAM bandwidth, then the
double-precision peak, then single precision. Without the first two there
is no roofline; what the budget cuts off keeps a theoretical value.

## Pollution downgrades a ceiling, it never discards one

Four signals make the calibration say `estimated` instead of `measured`,
each with its reason attached to the ceiling:

| Signal | Threshold |
|---|---|
| the repetitions disperse | more than 10% between the best and the worst |
| something else is running | load above 0.5 per allocated core |
| the FMA kernel came out scalar | the compiler emitted no SIMD, so this is not the peak |
| the rate is impossible | above 1.25x the microarchitecture's theoretical peak |

Discarding would be worse than downgrading. A Hotspot with no ceiling
cannot be placed at all, whereas a Hotspot placed against a ceiling
labelled `estimated: repetitions disperse by 18%` still tells a reader
which order of magnitude they are in, and tells them what to distrust.

## Without a measurement, theory - and never an extrapolation

Until a calibration has run, the FLOP/s ceilings come from a table of
microarchitectures crossed with the exposed frequency and scaled to the
allocation. Those are always `estimated`, because a theoretical peak is
systematically unreachable - turbo, throttling, cgroup limits.

An unknown microarchitecture yields no ceiling at all. Extrapolating from
a neighbouring entry would produce a wrong roof wearing an `estimated`
label, and every classification built on it would bend quietly. Memory
bandwidth has no theoretical entry either: it depends on the DIMM
population, which nothing exposes reliably, so it exists only once it has
been measured.

What was measured wins, and the table fills whatever stayed unmeasured -
a calibration cut short by its budget still yields a complete roofline,
with two qualities in it.

## The interconnect can only be measured from inside the allocation

The network ceilings come from a probe launched through the job's own
launcher, before the application, because that is the only moment the
network belongs to this job. Measured on a login node or after the fact,
the numbers would describe someone else's traffic as much as this job's.

The probe counts its own nodes, and a single-node world is declared
rather than published as an interconnect measurement: both ceilings then
carry `measured over shared memory: single-node allocation, not the
interconnect`. Shared memory is genuinely faster than any fabric, so a
roof taken from it would make every communication pattern look
catastrophic.
