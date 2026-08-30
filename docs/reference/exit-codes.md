# Exit codes

**The application's own exit code is propagated.** nunatak observes; it
never masks. Without that, `nunatak run -- ./solver && post_process`
would chain on broken results.

| Code | Meaning |
|---|---|
| the application's | the general case |
| `127` | command not found |
| `126` | found but not executable |
| `125` | nunatak failed before launch, a usage error included |
| `121` | a named degradation under `--strict` |

The reserved codes follow `timeout` and `env`, and they carry the same
accepted ambiguity: an application that exits 125 by itself cannot be
told from a nunatak failure. That is the price of transparency, and
`--json` settles it when certainty is needed.

Without `--strict`, a degradation never fails a run: a successful run
with an estimated roofline returns 0. With it, any named degradation
becomes an error.
