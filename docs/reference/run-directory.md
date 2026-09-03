# The Run directory

A Run is one directory, whatever the number of ranks and nodes. There is
no registry and no identifier: the directory name *is* the identifier, so
a Run survives `scp`, archiving, and being attached to a ticket.

```
.nunatak/solver-20260809-142233/
  manifest.json     machine, provenance, passes, degradations, file map
  pivot/            measured data, ten Parquet tables
  collect/          the collectors' own output, unmodified
```

The directory is named `<project>-<date>-<time>`. The project name comes
from `nunatak.toml`, else from the git repository, else from the base
name of the real target binary: in `nunatak run -- mpirun -n 256
./solver` the name is `solver`, not `mpirun`. `--name` always wins.

The path is printed at the end of every run, the parent directory being
hidden. `runs_dir` moves it, typically to `$SCRATCH`; `-o` names it
exactly. A `.gitignore` containing `*` is written inside `.nunatak/`, and
the repository's own `.gitignore` is left alone.

A command that takes a Run also accepts none and takes the most recent
under `runs_dir`. That is the convenience of a registry without being
one: "most recent" is read off the directory names, and there is no index
to repair.

## The global cache

Everything that describes a Run lives in the Run. `$XDG_CACHE_HOME/nunatak`
holds only what can be recomputed: Calibrations by Machine, network
probes and mpiP built per MPI stack, and the memorised agreements to send
source to a remote provider. Losing the cache costs time, never
information.

It is deliberately not under a node-local `TMPDIR`: a Calibration has to
outlive the job that measured it.

## manifest.json

Plain JSON, indented, readable without nunatak. That readability is the
point: it is what a Run is worth in ten years.

| Key | Content |
|---|---|
| `format` | `name`, `schema`, and the nunatak version that wrote the Run |
| `run` | name, creation time, the command as a list, the application's exit code |
| `machine` | system, kernel, architecture, CPU model, logical cores, the allocation shape, and the Ceilings with their quality |
| `provenance` | commit, whether the tree was dirty, observed dependency versions, the effective configuration |
| `passes` | one entry per pass: index, exit code, start, end, the collectors with their versions |
| `degradations` | every named capability that was missing, with its message and its remedy |
| `files` | the map from table name to path, so the pivot can be read without knowing this page |

The schema number is `2`. It changes when a reader written for the old
form would misread the new one, never for an addition.

`machine.allocation` is what makes a Machine a couple of hardware and
allocation rather than a node: visible cores, affinity mask, cgroup CPU
quota and memory limit. A job given 8 cores of a 128-core node is a
different Machine, and its Ceilings belong to those 8 cores.

## The pivot

The pivot holds measurements and nothing else. No classification, no
roofline placement, no advice: everything derived is recomputed on
demand, which is what keeps a Run analysable years after it was written,
by a later version of nunatak, on a machine where the binary no longer
exists.

Ten [Parquet](https://parquet.apache.org/) tables. `hotspots` and `loci`
carry integer ids that the other tables reference; nothing else is joined
by name.

No absolute address is ever persisted. Every address is normalised at
ingestion into `(module identity, offset)`, which is what makes ASLR and
function reordering irrelevant, and what makes two ranks that loaded a
library at different addresses converge on the same Hotspot.

### `pivot/hotspots.parquet`

| Column | Type | |
|---|---|---|
| `id` | int32 | referenced by the other tables |
| `module` | string | logical identity |
| `name` | string | logical identity, demangled |
| `source_file` | string | logical identity |
| `resolution_level` | string | `line`, `function`, `symbol`, `unresolved` |
| `module_id` | string | physical identity: build-id or LC_UUID, absent for Python and GPU |
| `offset` | int64 | physical identity, or the sampled address of an unresolved Hotspot |

### `pivot/loci.parquet`

| Column | Type | |
|---|---|---|
| `id` | int32 | referenced by the other tables |
| `node` | string | |
| `rank` | int32 | MPI rank |
| `thread` | int64 | |
| `device` | int32 | GPU device |
| `stream` | int64 | GPU stream |

### `pivot/measurements.parquet`

One value at one `(hotspot, locus)` couple, with what is needed to judge
it. A row whose `hotspot` is absent is a Locus-level measurement: a
whole-rank aggregate from the counting layer, which has nothing to
attribute.

| Column | Type | |
|---|---|---|
| `hotspot` | int32 | |
| `locus` | int32 | |
| `pass_index` | int32 | the pass this value came from |
| `counter` | string | |
| `value` | double | |
| `unit` | string | |
| `quality` | string | `measured`, `estimated`, `unavailable` |
| `reason` | string | why it was downgraded, when it was |
| `sample_count` | int64 | what the relative error follows from |
| `coverage` | double | `time_running / time_enabled` when counters were multiplexed |

### `pivot/events.parquet`

| Column | Type | |
|---|---|---|
| `locus` | int32 | |
| `pass_index` | int32 | |
| `kind` | string | |
| `name` | string | |
| `start_ns` | int64 | |
| `duration_ns` | int64 | |
| `attributes` | string | JSON |

### `pivot/addresses.parquet`

The weight of every sampled address inside a Hotspot. This is detail
*within* a Hotspot, never a unit of analysis, and it is what lets a later
command ventilate a Hotspot by line on a machine where neither the binary
nor the symbolizer exists.

| Column | Type | |
|---|---|---|
| `hotspot` | int32 | |
| `offset` | int64 | |
| `pass_index` | int32 | |
| `counter` | string | |
| `value` | double | |
| `sample_count` | int64 | |

### `pivot/frames.parquet`

The inlining chain of each sampled address, innermost first.

| Column | Type | |
|---|---|---|
| `hotspot` | int32 | |
| `offset` | int64 | |
| `depth` | int32 | 0 is the innermost inline frame |
| `function` | string | |
| `file` | string | |
| `line` | int64 | |
| `declaration_line` | int64 | an attribute, never part of an identity |

### `pivot/extracts.parquet`

One extract per file a Hotspot's addresses reach. `text` is absent under
`--no-source`, and `reason` says why when there is no text: not found,
fingerprint mismatch, or ambiguous match.

| Column | Type | |
|---|---|---|
| `hotspot` | int32 | |
| `file` | string | as DWARF recorded it |
| `resolved_path` | string | where it was actually found |
| `start_line` | int64 | |
| `end_line` | int64 | |
| `text` | string | |
| `truncated` | bool | |
| `reason` | string | |

### `pivot/stacks.parquet`

Recorded call paths, aggregated by path. Frames are normalised to
`(module, offset)` like every other address, so a per-context split of a
Hotspot stays addable years later. Stacks never enter a Hotspot's
identity.

| Column | Type | |
|---|---|---|
| `id` | int32 | referenced by `stack-frames` |
| `locus` | int32 | |
| `pass_index` | int32 | |
| `counter` | string | |
| `value` | double | |
| `unit` | string | |
| `sample_count` | int64 | |

### `pivot/stack-frames.parquet`

| Column | Type | |
|---|---|---|
| `stack` | int32 | |
| `depth` | int32 | 0 is the leaf |
| `module` | string | |
| `offset` | int64 | |
| `function` | string | present when the collector named it, as for a Python trampoline |

### `pivot/loops.parquet`

Static analysis of the innermost hot loop: facts of the machine code,
blind to cache reuse. Nothing derived from them is ever of quality
`measured`.

| Column | Type | |
|---|---|---|
| `hotspot` | int32 | |
| `start_offset` | int64 | |
| `end_offset` | int64 | |
| `instructions` | int32 | per iteration |
| `flops_per_iteration` | double | |
| `vector_fp` | int32 | vector floating-point instructions |
| `scalar_fp` | int32 | |
| `vector_width_bits` | int32 | |
| `loaded_bytes` | int64 | per iteration |
| `stored_bytes` | int64 | |
| `gathers` | int32 | |
| `cycles_ports` | double | what the execution ports allow |
| `cycles_effective` | double | what the simulated steady state reaches |
| `scheduling_model` | string | the llvm-mca model used |
| `bounds_reason` | string | why the two cycle bounds are absent, when they are |

## collect/

The collectors' own output, kept unmodified: `perf.data` and the text of
`perf script`, an `xctrace` bundle, an mpiP report, the Python perf maps
retrieved from each node. They are the raw material a future parser can
be run against, and they are why a hardware campaign is worth more than a
green check.
