# The site configuration file

`/etc/nunatak.toml` sets defaults for every user of the machine. It is
the lowest of the three layers: a project's `nunatak.toml` overrides it,
and a command-line flag overrides both.

```sh
NUNATAK_SITE_CONFIG=/opt/nunatak/etc/nunatak.toml
```

That variable moves the file, for a machine where `/etc` is not yours to
write, or where the tool is published as an environment module.

## What belongs in it

The keys a user cannot be expected to know, and that are true of the
machine rather than of their code. Every key is listed in the
[configuration reference](../reference/configuration.md); these are the
ones a site sets:

```toml
runs_dir = "/scratch/$USER/nunatak"

[tools]
perf = "/opt/perf/bin/perf"
llvm-symbolizer = "/usr/lib/llvm-20/bin/llvm-symbolizer"
mpicc = "/opt/openmpi-5.0/bin/mpicc"
mpip = "/opt/mpiP/lib/libmpiP.so"

[debuginfod]
enabled = true
```

What does not belong in it: `source_map`, which describes where a
project's build tree lives, and `name`, which names a project. Both
follow the code, not the machine.

No model and no provider setting exists, here or anywhere. pi's own
configuration is the single source of both, and `tools.pi` points at the
executable like any other tool.

Every effective value ends up in each Run's provenance and in its report.
A site can set a threshold; it cannot set one silently.

## Two thresholds worth a site's attention

`sampling.rank_threshold` (64 by default) is where sampling narrows to
rank 0 plus the first rank of each node. Raise it on a machine whose
nodes are small, lower it on a machine where jobs are wide and the
interconnect is what you care about.

`thresholds.coverage` (0.8) is the multiplexing coverage below which a
counter is downgraded to `estimated`. Lowering it makes more numbers look
solid than are; the label loses its meaning before the measurement does.
