# Commands

nunatak has six verbs. `run` measures an application; the other five work
on a Run that already exists, or on the Machine.

Everything after `--` is the command to profile, and nunatak never
touches it: its arguments, its stdout, its stderr and its exit code pass
through unchanged.

```sh
nunatak run -- mpirun -n 8 ./solver --input case.nml
```

A verb that takes a Run also accepts none, and then takes the most recent
one under `runs_dir`. A usage error exits with 125, the code reserved for
a nunatak failure before launch.

```{eval-rst}
.. argparse::
   :module: nunatak.cli
   :func: build_parser
   :prog: nunatak

   run : @after
      A single execution. Event groups that do not fit the PMU are
      multiplexed by the kernel rather than costing the application a
      second run.

      --strict : @after
         Every named degradation becomes an error and the run exits 121.
         Written for scripted use and for performance CI, where a profile
         that quietly lost its counters is worse than no profile at all.

      --multi-pass : @after
         The application runs once per counter group, each group small
         enough that the kernel multiplexes nothing, which is what the
         extra executions buy: exact counts.

         A witness group is replicated in every pass and compared at the
         end. Within the threshold, quantities that fuse one pass with
         another stay what they claim; beyond it, the application did
         different work in different passes and every fused quantity is
         downgraded to estimated with that reason.

         nunatak never turns this on by itself. Relaunching an
         application inside an allocation someone is paying for is not a
         decision a tool takes alone.

      --call-graph : @after
         `dwarf` records call stacks by copying stack memory at every
         sample. It works on any binary, frame pointers or not, and it
         costs enough that the sampling frequency drops to 97 Hz and the
         cost is announced.

         Without this flag the stack mode is settled before launch, from
         the processor and from the prologues of the binary itself.

      --no-source : @after
         No source text enters the Run. Line numbers, the per-line sample
         distribution and every measurement stay, so one still sees where
         the time goes.

         This is the control for code that must not leave a site. It is
         not the control for what leaves the machine over the network:
         the model is shown source, so its advice is withheld along with
         the text.

      --source-map : @after
         Rewrites a path prefix recorded in DWARF, for a binary built
         somewhere the sources no longer are. Repeatable, and the same
         table can live in `nunatak.toml` under `[source_map]`.

      --no-calibrate : @after
         Skips the calibration and the network probe. The Machine keeps
         its theoretical ceilings, which are always of quality
         `estimated`, and memory-bandwidth ceilings do not exist at all
         until they are measured.

      --no-explain : @after
         No model is called at the end of the run. The deterministic
         analysis is unaffected: it never depends on the model.

      --name : @after
         Otherwise the name comes from `nunatak.toml`, then from the git
         repository, then from the base name of the real target binary -
         `solver`, not `mpirun`.

   doctor : @after
      Every check invokes the tool it is about rather than trusting its
      presence on `PATH`, and prints what it found or the named
      capability that is missing with the way forward. A cheap subset of
      it runs at the start of every `run`.

      Given a command, `doctor` also inspects the target binary and says
      how far attribution will reach, before any compute time is spent.

   explain : @after
      Measurement runs in a job, on compute nodes that usually have no
      network egress. This verb is what runs afterwards, from a login
      node.

      Calls go out in parallel, and a single Hotspot asked about on a
      terminal streams its answer as the model writes it.

      --model : @after
         Passed to pi verbatim. pi's own configuration is the single
         source of providers and models, and nunatak neither duplicates
         nor overrides it.

   report : @after
      The analysis is never persisted, so the report is recomputed from
      the measured pivot. Regenerating is a real operation: after an
      upgrade, or on a machine that only received the Run directory.

      --no-source : @after
         Writes `report-no-source.html` beside the full report, never in
         its place. The payload is stripped before the page exists, so
         the shared file never contained a line of code.

   compare : @after
      The unit of comparison is the logical function, inlining included,
      never the physical symbol: when a recompiled build inlines the
      function you just optimised, its symbol vanishes and its time melts
      into the caller, while the inline frames carry it through.

      Every displayed delta carries its own statistical uncertainty, and
      a difference smaller than the combined sampling error of its two
      sides is written `not a difference`.

      The exit code stays 0. A comparison informs; deciding what a
      regression means belongs to whoever reads it.

   calibrate : @after
      Ceilings are measured by an embedded microbenchmark, compiled
      locally and run as a separate process. A ceiling is the maximum of
      its repetitions, never their mean: it is an upper bound.

      The calibration also triggers by itself at the first `run` on an
      unknown Machine, before the application launches, which is the only
      moment the node is truly yours. The verb exists so that the budget
      can be spent in a small dedicated job instead of at the head of a
      large allocation.

      --force : @after
         The cached profile is keyed by hardware and allocation shape.
         Recalibrate when the machine changed underneath that key.
```
