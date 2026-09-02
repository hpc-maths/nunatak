# Profile on macOS

The command is the one from every other page:

```sh
nunatak run -- ./stencil
```

```
degraded [llvm-missing]: no usable llvm-symbolizer found; atos macOS 26.5.2 (/usr/bin/atos) stands in - attribution works, without staleness fingerprints; install LLVM 19+ for them and for loop analysis
collecting with xctrace 16.0: ./stencil
grid 4096 x 4096, 60 steps, 0.77 s (1302.2 Mcell/s), checksum 0.562487
8 measurements across 5 hotspots (4 resolved)
summary: 3 Hotspots above the statistical floor hold 98% of the sampled time (783 samples of cpu-clock over 0.783 s)
  laplacian (line) - 38% of the sampled time - no placement: no flops_dp raw counter in this Run
  update (line) - 32% of the sampled time - no placement: no flops_dp raw counter in this Run
  reaction (line) - 29% of the sampled time - no placement: no flops_dp raw counter in this Run
what this report does not say:
  - 2% of the sampled time sits below the statistical floor of 30 samples, aggregated as "others"
```

That is `examples/stencil` on an Apple M5 Max. Line-level Hotspots, their
shares, and a stated absence where a roofline placement would be on
Linux.

## Which collector you get

| Rung | Requirement | Counter | Grain |
|---|---|---|---|
| xctrace's Time Profiler | Xcode installed | `cpu-clock`, Running threads only | the exact leaf address of every sample |
| `/usr/bin/sample` | present on every Mac | `wall-clock`, blocked threads included | function |

The run picks the first that works and says which one it used. Call
stacks come with every hit on both rungs, so callers and inclusive time
do not depend on how the application was compiled the way they do on
Linux.

The `.trace` bundle stays in the Run as its raw artifact, and the
application's real exit status is read from the trace's own table of
contents - xctrace does not propagate it.

## Install LLVM if you want the whole picture

Xcode ships no llvm-symbolizer, so `atos` is the platform's nominal
symbolizer and the `llvm-missing` line above is the normal state of a
Mac. It costs two things: the staleness fingerprints that catch a source
file edited since the build, and the cycle bounds of the loop analysis.

The per-iteration counts survive without it - Xcode's own llvm-objdump
reads the Mach-O. On the run above they came back for all three kernels,
which is where a macOS report gets its arithmetic intensity:

| | `laplacian` | `reaction` | `update` |
|---|---|---|---|
| instructions per iteration | 38 | 61 | 38 |
| FLOPs per iteration | 40 | 80 | 24 |
| vectorized FP instructions | 100%, 128-bit | 100%, 128-bit | 100%, 128-bit |
| bytes loaded, stored | 272, 64 | 64, 64 | 192, 64 |

## Energy, if the site allows it

With `NOPASSWD: /usr/bin/powermetrics` in the sudoers policy,
powermetrics rides the run and leaves three aggregates, all `estimated`
with their reason:

| Aggregate | On the run above | The reason it carries |
|---|---|---|
| `energy_impact` | 0.33 | Apple's abstract per-process energy number, not joules; tasks matched by process name |
| `cpu_energy` | 20122 mJ | whole-package energy over the sampling window: every process on the machine included |
| `gpu_energy` | 49 mJ | whole-package energy over the sampling window: every process on the machine included |

[Allowing powermetrics](../../deployment/powermetrics.md) is where the
rule gets written. Without it the run declares
`power-aggregates-unavailable` and loses nothing else; an application
shorter than the one-second sampling interval leaves no sample and says
so too.

## Calibrate, because theory has nothing to offer here

Apple Silicon exposes no rated frequency, so the theoretical table
yields nothing at all and the measured ceilings are the only ones a
macOS roofline will ever have. On the M5 Max above:

```
Machine 6bc6b4652030894e already calibrated (--force to redo)
dram_bandwidth   3.652e+11 byte/s   measured
flops_dp         6.065e+11 flop/s   measured
flops_sp         1.279e+12 flop/s   measured
```

[Calibrating the Machine](../machine/calibrate-the-machine.md) is the
same operation as everywhere; it simply matters more here.
