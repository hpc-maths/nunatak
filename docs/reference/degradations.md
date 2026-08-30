# Degradations

A degradation is a capability nunatak could not use. It is named,
announced before the run rather than after, and it never stops the run:
the Run simply carries fewer measurements.

**A degradation is not an error.** Under `--strict` it becomes one, and
the run exits 121; that is what the flag is for.

Every entry below says the same four things: what is lost, what is still
measured, why it happens, and what to do. Each name is an anchor, so
`degradations.html#cpu-collection-unavailable` is where a message from
nunatak leads.

## Collection

### cpu-collection-unavailable

No sampling at all, so no Hotspot and no Measurement attributed to one.
The Run is still written, with its machine snapshot and its provenance.

Either `perf` is missing, or the kernel forbids event sampling. On Linux
that is `kernel.perf_event_paranoid` above 2. See
[kernel permissions](../deployment/kernel-permissions.md).

### counter-events-rejected

The FLOP and DRAM counters of this microarchitecture, so no roofline
placement. Time per Hotspot is still sampled and attributed.

The kernel refused the event names, usually because it is older than the
microarchitecture. Report the perf version.

### call-stacks-unavailable

Callers, and the inclusive time that follows from them: a hot `dgemm`
inside OpenBLAS stays a Hotspot with no caller. The roofline is
untouched, since it depends only on the leaf.

No hardware branch stacks, and too few frame pointers in the probed
prologues. Recompile with `-fno-omit-frame-pointer`, libraries included,
or ask for `--call-graph dwarf` and accept its cost.

### call-stacks-rejected

The same, after the kernel refused the stack mode at launch. The
recording retried without stacks rather than failing.

### ingestion-unsupported

The measurements of one collector output, whose raw file is kept in the
Run so that a later version can read it.

No parser matches the version of the tool that produced it. Upgrade
nunatak, or use a version of the tool the parsers know.

### perf-script-missing

Every Measurement of the Run. The `perf.data` stays, so the Run can be
re-ingested later.

`perf script` produced nothing. Its own messages, above in the log, say
why.

### perf-script-unparsed

The samples on the lines that were not recognised. Every other sample is
ingested, and the count is stated.

A sample line in a format the parser does not know. Report it with the
perf version.

### multi-pass-unavailable

The exact counts `--multi-pass` was asked for. A single time-only pass
runs instead.

MPI runs are not covered yet, and an unknown microarchitecture has no
counter groups to split.

### passes-skipped

The passes after the one that failed. The Run keeps the passes that ran.

The application exited non-zero on a pass, and relaunching a failure
would spend the allocation reproducing it.

### passes-inconsistent

The exactness of every cross-pass quantity: they stay, downgraded to
`estimated` with the reason. Quantities measured within one pass are
untouched.

The witness group moved between passes beyond `passes.witness`, so the
application did different work each time. A convergence criterion,
dynamic scheduling or non-deterministic MPI does this.

### module-recompiled-between-passes

The fusion of that module's Hotspots across passes, and their roofline
placement. They are presented per pass instead.

The module's build-id changed while the run was measuring, which is an
invalidity rather than an uncertainty. Comparing two builds is two Runs,
never two passes.

## Attribution

### llvm-missing

Staleness fingerprints on source extracts, and the static loop analysis.
Names and line numbers survive through the platform's own tool, GNU
`addr2line` on Linux and `atos` on macOS.

No usable `llvm-symbolizer`. Install LLVM 19 or newer, or set
`tools.llvm-symbolizer`.

### llvm-too-old

The static loop analysis on microarchitectures the installed LLVM does
not know. Symbolization is complete at any version from 17.

### symbolization-failed

The names of the Hotspots in the modules concerned, which stay
`unresolved` and are displayed `module+0x3a1c`. Their measurements are
exact: the time really was spent at those addresses.

The module's file was not readable at analysis time. A Run analysed on
another machine takes this path.

### loop-analysis-unavailable

The hot loop's instruction counts and its cycle bounds. Everything
measured is untouched: a static analysis is a model, never a measurement.

No GNU `objdump`. Install binutils, or set `tools.objdump`.

## MPI

### counting-unavailable

The per-rank aggregates of the ranks named: their time, cycles,
instructions and MPI volumes. Sampled ranks are unaffected, and the
balance verdict is computed on the ranks that did report.

No usable `perf` on those nodes.

### counting-incomplete

The aggregates of ranks the world size announced and that left nothing
behind. They are named by number rather than passed over in silence,
because silence would read as "nothing ran there".

Their own job logs say more.

### perf-stat-unparsed

The counts on the lines that were not recognised. The others are
ingested.

### mpi-analysis-unavailable

`mpi_time`, `app_time` and `mpi_sent_bytes` per rank, so the MPI share
of the run cannot be stated. Sampling and counting are unaffected.

mpiP was not found. Load the site's mpiP module so that it appears in
`LD_LIBRARY_PATH`, set `tools.mpip`, or run `nunatak doctor` where a
compiler is, which builds it once per MPI stack.

### mpi-report-missing

The same, after mpiP was preloaded and produced no report. The
application may not have reached `MPI_Finalize`.

### network-analysis-unavailable

The network Ceilings, so no interconnect roof on the roofline.

No usable `mpicc` to build the probe with. Load the MPI module, or set
`tools.mpicc`.

### network-ceiling-unavailable

The same, at run time: the probe is never built during a run. Run
`nunatak doctor` where the compilers are, on a login node, then run
again.

## Python

### python-hotspots-unavailable

The Python side of the profile: functions stay invisible and only native
frames are attributed.

The interpreter predates CPython 3.12 and its perf trampolines. Install
py-spy, which samples the interpreter from outside, or use CPython 3.12
or newer.

### python-counters-unavailable

The hardware counters, and with them the roofline placement of the Python
Hotspots. The Hotspots themselves are complete, sampled temporally by
py-spy.

No hardware counter rides a temporal sampler. CPython 3.12 or newer
restores the counter path.

### python-sampling-failed

Every Python Measurement of the Run. py-spy wrote no exit witness, so the
application may not have run at all; py-spy's own messages say more.

### python-sampling-missing

The same, when py-spy ran and produced no stack.

### python-sampling-unparsed

The stacks on the lines that were not recognised. The others are
ingested.

## macOS

### exit-status-unavailable

The application's own exit code. xctrace's code stands instead, which
says the run failed without saying with which code. Every measurement is
unaffected.

The trace's table of contents did not name the launched target's status.
Run again: that export answers intermittently.

### sample-images-unavailable

Address-level attribution: hits are attributed to whole modules instead,
so Hotspots keep their module name without offsets.

`sample` could not enumerate the binary images, which a binary's very
first launch typically causes. Run again.

### sample-report-missing

Every Measurement of the Run. `sample` produced no report; sampling
another user's process needs elevated rights.

### sample-report-unparsed

The samples on the lines that were not recognised. The others are
ingested.

### xctrace-export-missing

Every Measurement of the Run. The `.trace` bundle is kept, so the Run can
be re-ingested.

### xctrace-export-unparsed

The samples on the rows that were not recognised. The others are
ingested.

### power-aggregates-unavailable

The three energy aggregates: the process's `energy_impact`, and the
package-wide `cpu_energy` and `gpu_energy`. Optional, and nothing else
depends on them.

`powermetrics` needs root, and the sudoers policy does not allow it.
Allowing it is a site decision, exactly like perf's paranoid level. See
[powermetrics](../deployment/powermetrics.md).

### power-aggregates-empty

The same, because the application ended before the first sampling
interval. Aggregates need a run longer than that interval.

### power-aggregates-unparsed

The samples that were not recognised. The others are summed.

## Explanation and report

### explanation-unavailable

The advice. The deterministic analysis never depends on the model, so
the Run and its report lose nothing else.

Node.js or pi is not usable. Install them, or set `tools.pi`.

### explanation-withheld

The advice, because sending source to a remote provider has not been
agreed to. A batch job cannot ask, so the remedy is the exact command to
run from a terminal.

A provider whose endpoint is provably local asks nothing, which is the
clean exit for a site that can let nothing out.

### report-unavailable

The HTML report. The Run, the pivot and the terminal summary are
complete, and `nunatak report` regenerates the page once the app is
present.

The compiled report app is missing from this installation. Reinstall from
a built wheel; on a development checkout, run `npm install && npm run
build` in `report-app/`.
