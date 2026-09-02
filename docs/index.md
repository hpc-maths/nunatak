# nunatak

Zero-instrumentation profiler for high-performance computing. nunatak
orchestrates existing collectors (`perf`, `nsys`, `rocprofv3`, `mpiP`,
`xctrace`...), places compute units on a roofline, diagnoses CPU, GPU,
memory and network bottlenecks, and has the results explained by a
language model.

```sh
nunatak run -- ./my_binary
```

The application runs once, untouched, and the measurements land in a
single self-sufficient directory with an HTML report beside them. Where
a capability is missing, the run names it and carries fewer
measurements: no number here is invented to keep a table full.

::::{grid} 1 1 2 2
:gutter: 3

:::{grid-item-card} Getting started
:link: getting-started/index
:link-type: doc

Install nunatak, then profile a program end to end: seven steps, a
five-line fix, and a gain that clears its own sampling error.
:::

:::{grid-item-card} User guide
:link: guide/index
:link-type: doc

For whoever profiles an application: the recipe for each situation, and
why nunatak behaves as it does.
:::

:::{grid-item-card} Reference
:link: reference/index
:link-type: doc

Commands, configuration keys, the Run format, the machine-readable
payloads, and every name nunatak can print.
:::

:::{grid-item-card} Deployment
:link: deployment/index
:link-type: doc

For whoever administers the machine: the kernel settings, the site's own
tools, and the defaults every user inherits.
:::

:::{grid-item-card} Development
:link: development/index
:link-type: doc

For whoever changes nunatak: the architecture, the test tiers, the code
map, and the decision log.
:::

::::

```{toctree}
:maxdepth: 2
:hidden:

getting-started/index
guide/index
reference/index
deployment/index
development/index
```
