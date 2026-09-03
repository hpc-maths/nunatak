# nunatak

[![ci](https://github.com/hpc-maths/nunatak/actions/workflows/ci.yml/badge.svg)](https://github.com/hpc-maths/nunatak/actions/workflows/ci.yml)

Zero-instrumentation profiler for high-performance computing. nunatak
orchestrates existing collectors
([`perf`](https://perfwiki.github.io/main/),
[`nsys`](https://developer.nvidia.com/nsight-systems),
[`rocprofv3`](https://rocm.docs.amd.com/),
[`mpiP`](https://github.com/LLNL/mpiP), `xctrace`...), places compute
units on a roofline, diagnoses CPU, GPU, memory and network bottlenecks,
and has the results explained by a language model.

```sh
nunatak run -- ./my_binary
```

## Status

Under construction, and there is no released package yet. The
documentation is published at
[hpc-maths.github.io/nunatak](https://hpc-maths.github.io/nunatak/) and
built from [`docs/`](docs/); the architecture decisions are in
[`docs/development/decisions/`](docs/development/decisions/) and the
reference glossary in
[`docs/reference/glossary.md`](docs/reference/glossary.md).

## License

BSD-3-Clause.
