# 0007. The CLI surface: a Run is a directory, six verbs, and nothing that masks

*Recorded 2026-08-09.*

## Context and decision

Six earlier decisions loaded the command line with responsibilities
without ever drawing it: `doctor` accumulated the tool inventory, the
permissions, the target binary's inspection and the network probe's
build; `compare` and `--strict` entered v1; `--no-source`,
`--source-map` and the multi-pass mode were added along the way. This
record assembles them.

**A Run is a self-sufficient directory, not an entry in a store.** There
is no registry and no identifier: the directory's name *is* the
identifier. The reason is specific to HPC: a Run is born **inside a
job**, on compute nodes, with output landing on `$SCRATCH` and not in a
tightly quota'd `$HOME`, and it is then copied, archived, attached to a
ticket, sent to a colleague. A directory survives all of that; an
identifier in a local store does not survive the first `scp`.

Hence the rule that governs all of the product's state:

> **Everything that describes a Run lives in the Run. The global cache
> contains only what can be recomputed.** Losing the cache costs time,
> never information.

**The LLM's Explanation is separated from measurement by necessity, not
by comfort.** The 24 to 60 seconds per kernel already argued for not
blocking. But the decisive reason lies elsewhere: `run` executes inside a
job, on compute nodes that **generally have no network egress**.
Measurement and explanation do not merely differ in duration, they run
**in different places**.

**nunatak observes, it does not mask.** The profiled application's exit
code is propagated as it stands, as `time`, `strace`, `env` and `timeout`
do.

## Options considered

- **A managed local store** (`~/.nunatak`) with Runs designated by
  identifier and a `list` command: dropped, the identifier does not
  survive a copy and `$HOME` is the wrong filesystem on a cluster.
- **Writing Runs flat into the current directory**: dropped in favour of
  a hidden `.nunatak/`, which keeps the working directory clean after
  twenty runs without reintroducing a registry.
- **The Explanation as a mandatory step of `run`**: dropped, it would
  make `run` unusable in a job with no network egress.
- **The Explanation as an entirely manual command**: dropped too, it
  would degrade the experience on a laptop where everything works first
  time. `run` tries and degrades.
- **Returning nunatak's status rather than the application's**: dropped,
  `nunatak run -- mpirun ./solver && post_process` would then chain on
  broken results.
- **Making every degradation exit with an error**: dropped, it would
  break every `set -e` in a job script for a perfectly usable run. That
  is precisely the role of `--strict`, and of it alone.
- **A `[tool.nunatak]` section in `pyproject.toml`**: dropped, the
  profiled application is most often written in C++ or Fortran and has no
  reason to own a Python file.
- **Duplicating the LLM provider and model in our configuration**:
  dropped, pi's configuration is the single source.
- **An animated text interface during the run**: dropped, the output
  lands in a job log file and not in a terminal.

## Consequences

### Where the state lives

- Runs land in **`.nunatak/PROJECT-YYYYMMDD-HHMMSS/`**. The project name
  follows a cascade: the one declared in `nunatak.toml`, else the git
  repository's name, else the **base name of the real target binary**,
  with `--name` always winning.
- That last point has a trap: in `nunatak run -- mpirun -n 256
  ./solver`, the expected name is `solver` and not `mpirun`. nunatak
  already knows how to see through the launcher, since `doctor` has to
  find the target binary to inspect it; that machinery is reused rather
  than a second one written.
- The **`runs_dir`** configuration key (default `.nunatak`) moves the
  parent, typically to `$SCRATCH` on a site that wants it; **`-o`**
  designates the Run's directory exactly, for stepping outside the
  scheme.
- The directory being hidden, **`run` prints the Run's path at the end**,
  and the commands that take a Run accept receiving none: they then take
  **the most recent** under `runs_dir`. That is the convenience of a
  registry without being one, since "the most recent" is read off the
  directory names and there is no index to keep up to date or repair.
- nunatak writes a **`.nunatak/.gitignore` containing `*`**, which avoids
  polluting the user's `git status` without touching their own
  `.gitignore`.
- **Whatever the number of ranks, a Run is a single directory.** Per-rank
  data is retrieved into it, including the `/tmp/perf-<pid>.map` files
  that must be recovered before the job's epilogue cleans the nodes. The
  user never has 256 directories to glue back together.
- The **global cache** lives under `$XDG_CACHE_HOME/nunatak` and contains
  only what can be recomputed: Calibrations per Machine, network probes
  built per MPI stack, agreements to send source to a remote provider. It
  must be **shared across nodes**: a node-local `TMPDIR` would be the
  wrong place, a Calibration having to outlive the job. Its size is
  negligible.

### The six verbs

| Command | Role |
|---|---|
| `nunatak run -- <command>` | Measure, analyse, report. Entirely deterministic, no network. |
| `nunatak doctor [-- <command>]` | Diagnosis. Builds the network probe, recompiles a calibration kernel locally for an uncovered ISA. Without the target command it cannot inspect the binary. |
| `nunatak explain <run>` | Generates or regenerates the Explanations of an existing Run. |
| `nunatak report <run>` | Regenerates the HTML report from the pivot. |
| `nunatak compare <runA> <runB>` | The diff. |
| `nunatak calibrate` | Idempotent, respects the cache, `--force` to redo it. |

- **`report` is not a duplicate**: the Diagnostic is never persisted but
  recomputed, so regenerating is a real operation - after an `explain`,
  after a nunatak upgrade, or to produce a shareable `--no-source`
  variant without profiling again.
- **`calibrate` stays automatic at the first Run**; exposing it allows
  doing it in a small dedicated job rather than at the head of a large
  allocation, which any informed user will want.
- **`run` tries the Explanation and never depends on it.** Failing that,
  it degrades by name with the exact command to replay: "Explanation not
  generated: no route to the provider from this node. Run `nunatak
  explain .nunatak/solver-20260809-1422` again from a login node."
  `--no-explain` skips it deliberately.

### Exit codes

- **The application's code is propagated** in the general case.
- A reserved range, in the manner of `timeout` and `env`: **127** command
  not found, **126** found but not executable, **125** nunatak failure
  before launch, **121** a `--strict` violation.
- The residual ambiguity is accepted and documented: an application that
  exits 125 by itself cannot be told from a nunatak failure. That is the
  price of transparency, `timeout` pays it too, and the JSON output
  settles it when certainty is needed.
- **Without `--strict`, a degradation never exits with an error.** A run
  that succeeded with an estimated roofline returns 0.
- **JSON** on `doctor`, on `run` (the Run's summary: totals, Hotspots
  above the floor, Quality, degradations met) and above all on
  `compare`, which is what a performance CI really consumes, with the
  statistical uncertainty carried in the difference. `explain` and
  `report` do not need it.

### Configuration

- **Three layers by increasing precedence**: site configuration, project
  configuration, flags. TOML format, `nunatak.toml` at the repository
  root.
- They serve two needs the command line does not cover: a **site** that
  wants defaults for all its users (a local provider, systematic
  `--no-source`, a usable path to `perf`), and a **project** that wants
  to remember its source mapping.
- **The LLM provider and model never appear there**: pi's configuration
  stays the single source, and nunatak neither duplicates nor overrides
  it.
- **The effective configuration is recorded in the Provenance**, Quality
  thresholds included - the multiplexing coverage threshold, the
  statistical floor. Without that, a site default would silently change
  results, which is exactly the invisible variation this project fights.
  **A threshold can be tuned; it cannot be tuned silently.**

### Terminal output

It is a first-class output: on a cluster, `run`'s display lands in a
**job log file**, not in a terminal.

- **It adapts to its medium and detects it.** On a terminal: colour, and
  the LLM's generation streamed as it arrives. Off a terminal: no colour,
  no line rewriting, no progress bar, but timestamped lines that
  accumulate and stay readable in a `tail -f` as in a file reread three
  weeks later.
- **Three moments, three contents**: before launch, the light subset of
  `doctor` announces what will be degraded and the way forward; during,
  progress at the real steps - Calibration, Pass, per-rank retrieval,
  analysis - with no false precision about the time remaining; at the
  end, a summary that takes up the **report's first level**, the findings
  with their share of the time and their key figure, then the
  degradations, then the paths of the Run and of the report.
- **The terminal's vocabulary is the report's.** Quality and resolution
  level are written there in the same words, and a downgraded value
  displays its reason. Whoever reads only the log learns fewer details,
  never less about how solid their numbers are.
