# nunatak

Zero-instrumentation profiler for high-performance computing. nunatak
orchestrates existing collectors (`perf`, `nsys`, `rocprofv3`, `mpiP`,
`xctrace`...), places compute units on a roofline, diagnoses CPU, GPU,
memory and network bottlenecks, and has the results explained by a
language model.

```sh
nunatak run -- ./my_binary
```

```{toctree}
:maxdepth: 2

guide/getting-started
reference/index
deployment/index
development/index
```
