# nunatak

Zero-instrumentation profiler for high-performance computing. nunatak
orchestrates existing collectors (`perf`, `nsys`, `rocprofv3`, `mpiP`,
`xctrace`...), places compute units on a roofline, diagnoses CPU, GPU,
memory and network bottlenecks, and has the results explained by a
language model.

```sh
nunatak run -- ./my_binary
```

## Status

Under construction. The full specification lives in
[`docs/spec/`](docs/spec/), the architecture decisions in
[`docs/adr/`](docs/adr/), and the reference glossary in
[`CONTEXT.md`](CONTEXT.md).

## License

BSD-3-Clause.
