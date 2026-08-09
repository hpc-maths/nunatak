# Getting started

nunatak profiles an application without modifying it:

```sh
nunatak run -- ./my_binary
nunatak run -- mpirun -n 8 ./solver --input case.nml
```

The application runs once, its stdout/stderr untouched, and its exit code
is propagated - `nunatak run -- ./solver && post_process` behaves exactly
like the bare command. The measurements land in a **Run**: a single
self-sufficient directory under `.nunatak/`, named
`<project>-<date>-<time>`, that survives `scp`, archiving, and being
attached to a ticket. Its path is printed at the end of the run.

On Linux, sampling is collected with `perf`. On other platforms, or when
`perf` is missing, the run still executes: the missing capability is
announced **before** launch as a named degradation with the way forward,
and the Run simply carries fewer measurements.

## Checking the environment

```sh
nunatak doctor                  # tool inventory, permissions
nunatak doctor -- ./my_binary   # + target binary inspection
nunatak doctor --json
```

`doctor` invokes the tools instead of trusting their presence on `PATH`.
A cheap subset of it runs automatically at the start of every `run`.

## Exit codes

The application's code is propagated in the general case. Reserved codes,
in the manner of `timeout`: **127** command not found, **126** found but
not executable, **125** nunatak failure before launch, **121** violation
of `--strict`.

Without `--strict`, a degradation never fails the run. With it, any named
degradation becomes an error - for scripted use and performance CI.

## Configuration

Three TOML layers, by increasing precedence: site (`/etc/nunatak.toml`),
project (`nunatak.toml` at the repository root), command-line flags.

```toml
name = "solver"          # Run naming; --name always wins
runs_dir = "/scratch/me/runs"

[tools]
perf = "/opt/perf/bin/perf"

[thresholds]
coverage = 0.8           # multiplexing coverage below which a value degrades
```

Every effective value, thresholds included, is recorded in the Run's
provenance: a threshold can be tuned, it cannot be tuned silently.

## The Run directory

```
.nunatak/solver-20260809-142233/
  manifest.json        machine snapshot, provenance, passes, degradations
  pivot/               measurements and events (Parquet)
  collect/             raw collector outputs (perf.data, perf script text)
```

The manifest is plain JSON, readable without nunatak. The pivot holds
measured data only; analyses are recomputed on demand by later commands,
so a Run remains fully exploitable years after being written.
