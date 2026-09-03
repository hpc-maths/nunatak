# Profile a program end to end

By the end of this page you will have profiled a program, found where
its time goes, changed five lines and measured that the change worked.
The program is `examples/stencil` from this repository, so every number
below is one you can produce.

This tutorial runs on Linux, with `perf` and a usable LLVM. It ends on a
roofline, which needs hardware counters. On macOS sampling is temporal
and no per-Hotspot counter exists: the loop still closes, the verdict is
weaker, and [macOS](../guide/macos/index.md) is where to start instead.

The transcripts come from one core of an AMD EPYC 7702. Your numbers
will differ; the shape is what to compare.

## 1. Ask what this machine can measure

`doctor` invokes each tool instead of trusting `PATH`, and given a
command it also inspects the binary:

```sh
make -C examples
nunatak doctor -- ./examples/stencil
```

```
ok       cpu-collector      perf 6.14.11 (/usr/bin/perf)
ok       perf-permissions   kernel.perf_event_paranoid=2
ok       llvm               LLVM 20 (/usr/lib/llvm-20/bin/llvm-symbolizer)
ok       report-app         /opt/nunatak/lib/python3.13/site-packages/nunatak/report/assets
ok       target-binary      /home/me/nunatak/examples/stencil
ok       target-attribution debug information present: line-level attribution
missing  network-probe      no usable mpicc: the network probe cannot be built
                            -> load the MPI module (mpicc must answer) or set tools.mpicc in nunatak.toml
missing  mpiP-build         no usable mpicc: mpiP cannot be located or built
                            -> install mpiP through your site's modules or spack and set tools.mpip in nunatak.toml
missing  explanation        Node.js or pi not usable at 'pi': no LLM explanations
                            -> install Node.js and pi (npm install -g @earendil-works/pi-coding-agent), or set tools.pi in nunatak.toml
missing  call-stacks        frame pointers kept in 44% of prologues (12 probed across 2 modules), below the 75% threshold; worst offender: ./stencil (0%)
                            -> recompile with -fno-omit-frame-pointer, libraries included, to walk stacks at sampling cost
```

Read the `missing` rows before the `ok` ones. A named degradation is not
an error: the run proceeds and the Run carries fewer measurements.
This one will have no call stacks, which costs the callers of each
Hotspot and the inclusive time, and no advice from a language model.
Two of the rows are about MPI, which this program does not use - an
inventory names what it did not find, whether or not you need it. Every
name has an entry in the [degradation
catalogue](../reference/degradations.md) stating what was lost and what
to do about it.

The `target-attribution` row is the one that decides how much of the
rest of this page works. `debug information present` means Hotspots will
carry file and line; without `-g` the same run would name functions and
no lines, and the row would say so with the remedy in it. `examples/`
compiles with `-O2 -g`, which is what a code you intend to profile
should do.

## 2. Run the program once

Put the command after `--`. nunatak never touches it:

```sh
nunatak run --name stencil-before -- ./examples/stencil
```

```
collecting with perf 6.14.11: ./examples/stencil
grid 4096 x 4096, 60 steps, 7.15 s (140.8 Mcell/s), checksum ...
```

`--name` is what will make the pair legible at step 7:
`stencil-before-<date>-<time>` reads as itself three weeks later, a bare
timestamp does not. The program's own stdout is untouched and its exit
code is propagated, so `nunatak run -- ./stencil && ./next_step` behaves
like the bare command. On a Machine nunatak has not measured before, the
run first spends up to 60 seconds on the ceilings its roofline needs and
says so;
[Calibrate the Machine](../guide/machine/calibrate-the-machine.md) is
that step, and it happens once per machine.

## 3. Read the summary

The run closes on the report's first reading level - the sampling
coverage, then one finding per Hotspot in decreasing order of time:

```
summary: 5 Hotspots above the statistical floor hold 100% of the sampled time (7130 samples of task-clock over 7.15 s)
  reaction (line) - 38% of the sampled time - latency-bound
    achieved 3.69 GFLOP/s of 1.17 TFLOP/s attainable: 0.3% of the envelope
    DRAM intensity 309 flop/byte
    downgraded to estimated: demand fills only: hardware-prefetched traffic is not counted; FLOPs not split by precision on this microarchitecture; compared against the double-precision peak
  update (line) - 33% of the sampled time - latency-bound
    achieved 1.3 GFLOP/s of 169 GFLOP/s attainable: 0.8% of the envelope
    DRAM intensity 1.69 flop/byte
    downgraded to estimated: demand fills only: hardware-prefetched traffic is not counted; FLOPs not split by precision on this microarchitecture; compared against the double-precision peak
  laplacian (line) - 29% of the sampled time - latency-bound
    achieved 2.35 GFLOP/s of 1.17 TFLOP/s attainable: 0.2% of the envelope
    DRAM intensity 154 flop/byte
    downgraded to estimated: demand fills only: hardware-prefetched traffic is not counted; FLOPs not split by precision on this microarchitecture; compared against the double-precision peak
  main (line) - 0.6% of the sampled time - no placement: no flops_dp raw counter in this Run
  [unknown] (unresolved) - no placement: no dram_bytes raw counter in this Run
```

Two more lines follow: the Run's directory and the path of its report.

Three kernels, about a third of the time each. That is the first fact,
and the rest of the page acts on it: there is no single hot spot to
attack, so whatever you do has to change how the three work together.

The `(line)` beside each name is the resolution level, and it says the
Hotspot has a source position. The last two rows are what a report looks
like when it says less: `main` cannot be placed on a roofline because
this Run has no double-precision FLOP counter of its own, and one
Hotspot has no name at all - an address the symbol table does not cover,
declared rather than attached to the nearest symbol.

## 4. Open the report, and read what a number is worth

```sh
xdg-open .nunatak/stencil-before-*/report.html
```

The page is one self-contained file: no server, no network, and it still
opens in ten years out of an archive. That is what lets this
documentation publish one instead of describing it: the Run quoted
above, `stencil-20260901-121746`, is <a
href="../_static/example-report.html">published here</a>. Open it and
read this section beside it.

Click `laplacian`. The third level of the page is one Hotspot: its
roofline, its source annotated with samples per line, the facts of its
hot loop. The chart carries this Hotspot's point, the machine's compute
peak, its bandwidth diagonal, and the other Hotspots as pale points for
scale.

Then read the downgrade reason carried by the intensity, because it
disqualifies the verdict above it. `laplacian` is placed at 154
flop/byte, and that value is labelled estimated, `demand fills only:
hardware-prefetched traffic is not counted`.

154 flop/byte for a 5-point stencil is not credible: the kernel reads
five doubles and writes one for four additions and a multiply. What
happened is stated rather than hidden. On this microarchitecture the DRAM
counters see demand fills only, and a stencil is perfectly prefetched, so
most of the traffic is invisible: the intensity comes out enormous and
the classification lands on `latency-bound`. The classification is correct
arithmetic on incomplete inputs, and the label that says so is attached
to the number that carries the incompleteness.

This is the lesson worth more than the verdict: read what a number is
worth before acting on it. A profiler that had quietly reported
`memory-bound` here would have been right by accident, and wrong on the
next machine.

One more figure needs the same care. `0.2% of the envelope` compares one
core against the whole node's peak - 1.17 TFLOP/s is 32 cores of this
machine, and `stencil` is single-threaded. The envelope fraction is not
the number to read on a serial program; the intensity and the time split
are.

## 5. Read the annotated source

Still in `laplacian`'s detail, the Run carries the source it measured
and the share of samples that landed on each line:

```c
void laplacian(const double *u, double *lap, int n)
{
    for (int j = 1; j < n - 1; j++)
        for (int i = 1; i < n - 1; i++)
            lap[j * n + i] = u[(j - 1) * n + i] + u[(j + 1) * n + i]
                           + u[j * n + i - 1] + u[j * n + i + 1]
                           - 4.0 * u[j * n + i];
}
```

Line 13, the inner `for`, holds 31% of this Hotspot's samples, and the
three lines of the sum hold 28%, 29% and 12%. The addresses are spread
across one expression, which is what a memory-bound kernel looks like
from the sampler's side: no single instruction is guilty.

The loop facts sit beside it, read from the machine code rather than
from the source: 10 instructions, 5 flops and 48 bytes per iteration, 40
loaded and 8 stored, an L1 intensity of 0.104 flop/byte. Not one vector
floating-point instruction. Four scalar FP operations where the compiler
could have used SIMD.

Now open `update` and read its first line: it reads `lap[j * n + i]`,
the array `laplacian` has just written. The two functions sweep the same
4096 x 4096 grid one after the other, and the array between them exists
only to carry values from the first to the second. That is 128 MiB
written and read back per time step, sixty times over, for values that
were in a register a moment earlier.

Nothing in the classification says this. The time split, the source and
the traffic say it, which is why step 4 stopped at what the numbers are
worth.

## 6. Change five lines and run again

Compute the laplacian where it is used. In `examples/kernels.c`, replace
the body of `update`:

```c
void update(double *u, double *next, const double *f, double dt, int n)
{
    for (int j = 1; j < n - 1; j++)
        for (int i = 1; i < n - 1; i++) {
            double lap = u[(j - 1) * n + i] + u[(j + 1) * n + i]
                       + u[j * n + i - 1] + u[j * n + i + 1]
                       - 4.0 * u[j * n + i];
            next[j * n + i] = u[j * n + i] + dt * (lap + f[j * n + i]);
        }
}
```

Then delete `laplacian`, declare the new signature in `kernels.h`, and
in `stencil.c` drop the `laplacian(u, lap, n)` call and swap `u` with
`next` at the end of each step. The FLOP count is unchanged. One array
and one pass over the grid are gone.

```sh
make -C examples
nunatak run --name stencil-fixed -- ./examples/stencil
```

## 7. Compare the two Runs

```sh
nunatak compare .nunatak/stencil-before-* .nunatak/stencil-fixed-*
```

```
compare: stencil-before-20260901-132849 -> stencil-fixed-20260901-132928
total: 8.53 s -> 6.17 s: -27.7% (significant, sampling error ±1.4%)
  update (kernels.c) 2.98 s -> 3.27 s: +9.8% (significant, sampling error ±2.7%)
  reaction (kernels.c) 3.11 s -> 2.86 s: -8.0% (significant, sampling error ±2.5%)
  laplacian (kernels.c) vanished (was 2.42 s)
Report: .nunatak/stencil-fixed-20260901-132928/compare.html
```

Read the total first: 27.7% of the run is gone, and it is `significant`
because 27.7% is far beyond the ±1.4% the two Runs know their own totals
to. Then the rows: `laplacian` has no second side because the function
no longer exists, `update` grew because it absorbed that work, and the
sum of the two is a quarter of the run.

That pair was measured in a session where the program took 8.53 s rather
than the 7.15 s above. Two Runs are compared to each other, never to a
number from another session, which is why both sides of a comparison are
measured on one machine, with one command line, close together in time.

The verdict is arithmetic, and it cuts the other way too. Profile the
same unchanged binary twice and the diff says so of every row:

```
total: 8.37 s -> 8.39 s: +0.3% (within the sampling error of ±1.5%: not a difference)
  reaction (kernels.c) 3.06 s -> 3.06 s: -0.1% (within the sampling error of ±2.6%: not a difference)
```

Each kernel knows its time to ±2.6% on this workload, so a 1% win
claimed here would be the sampler being read as code. A longer Run
lowers that floor: the error falls as 1/sqrt(n) in the number of
samples. Measure it once on your own machine and you know what any later
comparison can resolve.

## Where to go next

The loop you just closed is the whole method. What changes in a real
setting is the launch line and the reading:

- [MPI runs](../guide/mpi/index.md), because your code is probably
  launched by `mpirun` or `srun`, and because ranks add a column to
  every table above;
- [How to read what nunatak tells you](../guide/reading-what-nunatak-tells-you.md),
  which is step 4 generalised: the four registers a report keeps
  separate, and why an absence is written rather than filled;
- [Profile a job on a scheduler](../guide/workflows/profile-a-job-on-a-scheduler.md),
  for the part that happens on a login node and the part that happens
  inside the allocation.
