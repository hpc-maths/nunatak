# Machine-readable output

Every verb carries `--json`, and two of the payloads are contracts rather
than conveniences: the report's, which the embedded page reads, and the
comparison's, which a performance CI reads.

A payload that is a contract declares itself:

```json
"format": {"name": "nunatak-compare", "schema": 1, "generated_by": "nunatak 0.1.0"}
```

| Format | Schema | Written to |
|---|---|---|
| `nunatak-run` | 2 | `manifest.json`, and the trunk of the report payload |
| `nunatak-report` | 6 | embedded in `report.html`, printed by nothing |
| `nunatak-compare` | 1 | embedded in `compare.html`, printed by `compare --json` |

A schema number changes when a reader written for the old form would
misread the new one, never for an addition.

## `compare --json`

The performance CI surface. One payload, two consumers: the HTML diff
embeds exactly what this prints, so the page and the pipeline cannot
disagree.

| Key | Content |
|---|---|
| `format` | `nunatak-compare`, schema 1 |
| `before`, `after` | `{run, name}`, the directory and the Run's name |
| `unit` | the time unit both sides are expressed in |
| `findings` | what is not comparable, each `{name, message}`: different Machines, commands, rank topologies, time bases |
| `total` | the delta over the whole run, same shape as an entry of `deltas` |
| `deltas` | one entry per compared logical function |

Each delta:

| Key | Content |
|---|---|
| `function`, `file` | the logical identity, inlining included, never the physical symbol |
| `before`, `after` | each side's value, its sample count and its relative error |
| `change` | the difference, in `unit` |
| `change_fraction` | the difference relative to the `before` side |
| `combined_error` | the two sides' sampling errors combined |
| `significant` | `false` when the change is smaller than `combined_error` |

A CI reads `significant`, not `change`. A 3% gain between two
Hotspots carrying 10% relative error is not a gain, and the payload says
so rather than leaving the pipeline to reinvent the statistics.

The findings never suppress the diff and never change the exit code,
which stays 0. A comparison informs; deciding what a regression means
belongs to whoever reads it.

## The report payload

Schema 6, embedded in `report.html`. Its first five keys are the Run
manifest's, unchanged, so the page and the archived Run never drift
apart.

| Key | Content |
|---|---|
| `format` | `nunatak-report`, schema 6 |
| `run`, `machine`, `provenance`, `passes`, `degradations` | the manifest's own trunk |
| `coverage` | the share of sampled time the report accounts for |
| `floor_samples` | the statistical floor, below which a Hotspot joins `others` |
| `hotspots` | one entry per Hotspot above the floor, with its diagnostic, its metrics and their quality, its source extract, its callers and its advice |
| `others` | the below-floor aggregate, which preserves the totals |
| `ranks` | the per-rank balance, absent outside an MPI run |
| `inline_view` | time by innermost inline frame, all Hotspots combined, absent when nothing was inlined |
| `explanations` | when the advice was generated, absent when it never was |

`--no-source` strips the payload before the page exists, so the
shared file never contained a line of code. A toggle in the page would
have hidden text that stayed embedded.

## `run --json`

| Key | Content |
|---|---|
| `run` | the Run directory |
| `name` | the Run's name |
| `exit_code` | the application's own code |
| `measurements`, `hotspots`, `resolved_hotspots` | counts |
| `report` | the report's path, `null` when none was written |
| `degradations` | each `{name, message, remedy}` |

## `doctor --json`

| Key | Content |
|---|---|
| `checks` | one entry per check: `{name, status, detail, remedy}` |
| `degradations` | the checks that name a missing capability, each `{name, message, remedy}` |

## `report --json`

| Key | Content |
|---|---|
| `run` | the Run directory |
| `report` | the path of the page just written |

## `calibrate --json`

| Key | Content |
|---|---|
| `machine` | the Machine identity this profile is keyed by |
| `cached` | `true` when the profile was reused rather than measured |
| `ceilings` | each `{name, value, unit, quality, reason}` |
