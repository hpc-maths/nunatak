# Get advice on your Hotspots

`run` tries the explanation at the end of the measurement and never
depends on it. On a compute node the attempt usually fails, and it fails
by naming itself:

```
degraded [explanation-unavailable]: Node.js or pi not usable: no LLM explanations for this Run - run `nunatak explain /tmp/nunatak-src/examples/.nunatak/stencil-a-20260902-072014` from a login node where pi is installed
```

The remedy is the command to replay, with the Run's path already in it.

## Ask from a login node

The Run travels: it is one directory, it carries the source extracts its
Hotspots point at, and `explain` reads it back wherever the model can be
reached.

```sh
nunatak explain                 # the most recent Run under .nunatak/
nunatak explain <run-dir>
```

The Run below was measured on a 32-core EPYC compute machine and
explained from a laptop, which is the arrangement the verb exists for:

```
withheld: [unknown] - Hotspot not resolved: nothing to anchor source on
Explanations send source code of this project to opencode-go (model deepseek-v4-flash), a remote service.
Send source there, now and for this project? [y/N] y
asking opencode-go for 4 explanation(s), in parallel; tens of seconds per Hotspot
reaction: advice received
update: advice received
main: advice received
laplacian: advice received
Explanations: stencil-a-20260902-072203/explanations.json
regenerate the report to include them: nunatak report stencil-a-20260902-072203
```

The calls go out in parallel because one answer takes tens of seconds.
A Hotspot that cannot be explained is named before anything is sent,
with the reason - here an unresolved Hotspot, which has no source to
anchor advice on. When a single Hotspot is asked about on a terminal,
the answer streams as the model writes it; the line that reaches a job
log is the same either way. Run `nunatak report <run-dir>` afterwards to
fold the advice into the page.

A provider that refuses says so per Hotspot, in its own words:

```
error: update: pi exited with 1: Error: Model "acme/does-not-exist" not found. Use --list-models to see available models.
error: reaction: pi exited with 1: Error: Model "acme/does-not-exist" not found. Use --list-models to see available models.
error: main: pi exited with 1: Error: Model "acme/does-not-exist" not found. Use --list-models to see available models.
error: laplacian: pi exited with 1: Error: Model "acme/does-not-exist" not found. Use --list-models to see available models.
error: no explanation was generated; the errors above say why
```

An authentication, quota or network failure arrives the same way and
exits 125. What it never does is pass for an empty answer.

## The question about your source

Explanations send source code to the configured provider, so a remote
provider is asked about once per project, and the answer is remembered in
`~/.cache/nunatak/consents`. Switching providers asks again. A provider
whose endpoint is on this machine - `localhost`, `127.0.0.0/8` or `::1`
in pi's `models.json` - is never asked about at all, which is the exit
for a site that can let nothing out.

A batch job cannot answer a question, and nunatak does not answer it for
you:

```
warning: explanations withheld: no consent recorded for this project and no terminal to ask on: no source was sent
```

Grant it once from a terminal, and the job's next Run explains itself.
This is a different control from `--no-source`, which keeps the code out
of the report: two risks, two switches.

## Choose the model

pi's own configuration is the single source of providers and models, so
there is no model setting in `nunatak.toml`. `doctor` reports what pi
would use:

```
ok       explanation        pi 0.84.3: provider opencode-go (remote), model deepseek-v4-flash, credentials ready (api_key)
```

To use another one for a single call, pass it through - the value reaches
pi verbatim:

```sh
nunatak explain --model provider/some-model
```

Pick a code-oriented model with reasoning capability. The answer quoted
in the next page came from `deepseek-v4-flash`. What `nunatak.toml` does
carry is the path to the tool, `tools.pi`, like every other external
tool.

## Skip it, and what happens without it

```sh
nunatak run --no-explain -- ./solver
```

Nothing is probed and nothing is declared: a Run without advice is a Run
with all of its measurements. The same silence covers a Run in which no
Hotspot is eligible - the verb says `no Hotspot is eligible for an
explanation in this Run` and exits 0.

## Where the advice lives

`explanations.json`, at the Run's root, beside the pivot rather than
inside it. Each entry names the model and the provider that wrote it.
Regenerating replaces the file wholesale, which is what to do after a
declined first attempt, a model change or a nunatak upgrade - and it
never reprofiles anything.
