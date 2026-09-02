# Multi-pass runs

A PMU has a fixed number of counters, and on some microarchitectures a
complete roofline needs more than that. `--multi-pass` buys the missing
counters by running the application again, once per group, which is
allocation time you paid for - so it is an opt-in, and it comes with a
check on whether the two executions did the same work.

```{toctree}
:maxdepth: 1

run-a-multi-pass-acquisition
the-witness-between-passes
```
