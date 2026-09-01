# Regenerate a report, and share it

A report is not a record: the analysis is never persisted, so the page is
recomputed from the Run's measured pivot every time. That is what makes
the four operations below possible on a Run that arrived by `scp`,
without the application, the binary or the machine that produced it.

## Regenerate it

```sh
nunatak report                # the most recent Run under runs_dir
nunatak report <run-dir>      # or the one you name
```

The path is printed at the end:

```
Report: .nunatak/stencil-20260901-121746/report.html
```

Do this after upgrading nunatak - the analysis is the new one, on the
same measurements - and on a machine that only received the directory.

## Share it without a line of code

```sh
nunatak report --no-source
```

This writes `report-no-source.html` **next to** the full report, never
in its place, and the source text is stripped from the payload before
the page exists: the file you send out never contained a line of code. A
toggle inside the page would be a trap, hiding text that stays embedded.

Line numbers, the per-line distribution of the samples and every
measurement remain, so the shared page still says where the time goes.

## Fill in the advice

A Run profiled on a compute node usually has no advice: the model is
reached from a login node. Ask afterwards, then regenerate:

```sh
nunatak explain <run-dir>
nunatak report <run-dir>
```

`explain` says the same thing when it is done:

```
Explanations: .nunatak/stencil-20260901-121746/explanations.json
regenerate the report to include them: nunatak report .nunatak/stencil-20260901-121746
```

## Compare two Runs

```sh
nunatak compare <before> <after>
```

The terminal carries the verdict and the page carries the table:

```
compare: stencil-before-20260901-132849 -> stencil-fixed-20260901-132928
total: 8.53 s -> 6.17 s: -27.7% (significant, sampling error ±1.4%)
  update (kernels.c) 2.98 s -> 3.27 s: +9.8% (significant, sampling error ±2.7%)
  reaction (kernels.c) 3.11 s -> 2.86 s: -8.0% (significant, sampling error ±2.5%)
  laplacian (kernels.c) vanished (was 2.42 s)
Report: .nunatak/stencil-fixed-20260901-132928/compare.html
```

That is `examples/stencil` before and after the fix its own report points
at: the laplacian computed where it is used, so one array and one pass
over the grid disappear. `update` grew because it absorbed that work, and
the run still lost 27.7% of its time.

## When no page is written

```
degraded [report-unavailable]: the compiled report app is missing from this installation
  -> reinstall nunatak from a built wheel; on a development checkout, run `npm install && npm run build` in report-app/
```

Installed wheels carry the page's application already compiled. A
development checkout builds it once, and the run itself never fails for
want of it.
