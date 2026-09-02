# Profile where source cannot leave

Two things can carry code out of the machine it was measured on: the Run,
which embeds source extracts, and the explanation, which sends them to a
provider. Each has its own switch, and neither implies the other.

## Keep the source out of the Run

```sh
nunatak run --no-source -- ./solver
```

The Run then holds no source text at all. Line numbers, the per-line
distribution of the samples and every measurement stay, so a Hotspot
still says which line of which file the time went to - the file is read
where it lives. Advice is withheld for the same Hotspots, with that
reason: the model is asked about source, and it quotes source back.

## Strip the source from a report you already have

A Run measured with its source stays shareable without it:

```sh
nunatak report --no-source <run>
```

That writes `report-no-source.html` beside the full report, never in its
place, and the text is stripped from the payload before the page exists -
so the file you send out never contained a line of code. [Regenerate and
share a report](../report/regenerate-and-share-a-report.md) is the
subject.

## Let the advice happen without leaving the machine

A provider whose endpoint is on this machine - `localhost`,
`127.0.0.0/8` or `::1` in pi's `models.json` - is never asked about,
because nothing goes out. `doctor` states which kind you have:

```
ok       explanation        pi 0.84.3: provider ollama (local), model qwen3-coder
```

`(remote)` in that row is the other case, and then the consent question
is what stands between the code and the provider. That row is also how a
site checks the arrangement it thinks it has.

## Answer the consent question once, or refuse it for good

The first remote explanation of a project asks on the terminal, bluntly,
and remembers the answer in `~/.cache/nunatak/consents` per project and
provider. Switching providers asks again.

Where the answer is no, say so at the call site and nothing is probed:

```sh
nunatak run --no-explain -- ./solver
```

A Run without advice keeps every measurement it had, and declares
nothing - there is no degradation for advice nobody asked for. [The
contract with the
model](../explanations/the-contract-with-the-model.md) lists what a
prompt carries, which is what the question is about.
