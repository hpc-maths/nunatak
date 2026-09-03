# Configuration

Three layers, by increasing precedence:

| Layer | Where |
|---|---|
| site | `/etc/nunatak.toml`, or the path in `NUNATAK_SITE_CONFIG` |
| project | `nunatak.toml`, searched from the working directory upwards |
| command line | the flags of the verb being run |

The project file is never `pyproject.toml`: the profiled application is
rarely written in Python.

The two files cover what a flag cannot. A site sets defaults for
everyone on the machine: a usable `perf`, a `runs_dir` on the shared
filesystem, a local model provider. A project remembers what belongs
to the code rather than to the invocation, typically its source map.

No provider and no model appear here. pi's own configuration is the
single source of both, and nunatak neither duplicates nor overrides it;
`tools.pi` points at the executable, like any other tool.

Every effective value, thresholds included, is recorded in the Run's
provenance and shown in the report. A threshold can be tuned; it cannot
be tuned silently.

## Keys

| Key | Default | Effect |
|---|---|---|
| `name` | the git repository, else the target binary's base name | Names the Run directory. `--name` always wins. |
| `runs_dir` | `.nunatak` | Where Runs are written. Typically moved to `$SCRATCH`. |
| `tools.<tool>` | found on `PATH` | Absolute path to an external tool, taking precedence over the search. One of `addr2line`, `atos`, `cc`, `llvm-symbolizer`, `mpicc`, `mpifort`, `mpip`, `objdump`, `perf`, `pi`, `py-spy`, `sample`, `xctrace`. |
| `source_map.<prefix>` | none | Rewrites a path prefix recorded in DWARF, for a binary built where the sources no longer are. Same effect as `--source-map`. |
| `thresholds.coverage` | `0.8` | Multiplexing coverage, `time_running / time_enabled`, below which a counter is downgraded to `estimated`. Above it the kernel's extrapolation over most of the run is still the quantity. |
| `sampling.frequency` | `997` | Sampling frequency in hertz, handed to the collector and to every sampling rank. `--call-graph dwarf` lowers it to 97, stack memory being copied at every sample. |
| `sampling.rank_threshold` | `64` | Above this many MPI ranks, sampling narrows to rank 0 plus the first rank of each node; below it, every rank samples. The counting layer covers all ranks either way. |
| `stacks.fp_threshold` | `0.75` | Share of probed prologues that must keep the frame pointer for the `fp` stack mode to be used. It is a rate because no header declares frame pointers: the only witness is the machine code. |
| `debuginfod.enabled` | `true` | `false` strips `DEBUGINFOD_URLS` from symbolizer invocations. |
| `debuginfod.timeout` | `10` | Seconds before an unreachable server is given up on. The client's own default is 90, long enough to hang an analysis. An explicit `DEBUGINFOD_TIMEOUT` in the environment wins. |
| `passes.witness` | `0.05` | Witness spread above which a multi-pass fusion is downgraded to `estimated`. Beyond it the application did different work in different passes. |

A key nunatak does not know is ignored, not refused: a site file written
for a newer version stays usable.

## An example

```toml
name = "solver"
runs_dir = "/scratch/me/runs"

[tools]
perf = "/opt/perf/bin/perf"
llvm-symbolizer = "/usr/lib/llvm-19/bin/llvm-symbolizer"

[source_map]
"/build/app" = "/home/me/app"

[thresholds]
coverage = 0.8

[sampling]
rank_threshold = 128
```
