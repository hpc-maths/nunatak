# Gate performance in CI

Profile the branch, compare it against a stored reference Run, and read
one boolean. The statistics are already done: a gate that re-derives them
from percentages reimplements the sampling error, and gets it wrong.

## Fail the profile before the gate

```sh
nunatak run --strict --json --name ci-$GITHUB_SHA -- ./bench > run.json
```

`--strict` turns every named degradation into an error and exits 121. A
run that lost its counters to a kernel setting still writes a report, and
comparing that report against a healthy reference measures the runner
rather than the branch - which is the failure a gate is least able to
notice on its own.

The payload on stdout carries the Run's directory, the application's own
exit code and every degradation with its remedy. nunatak's console lines
go to stderr, so the payload parses.

## Compare against the reference Run

A Run is one self-sufficient directory, so the reference travels as a
build artifact and needs no server to serve it:

```sh
nunatak compare "$reference" "$(jq -r .run run.json)" --json > delta.json
```

## Read `significant`, never the percentage

Two checks, in this order:

```sh
jq -e '.findings == []' delta.json
jq -e '.total.significant == false or .total.change <= 0' delta.json
```

The first fails when the two Runs are not comparable - a different
Machine, a different command, a different rank topology or a different
time base. A hosted runner changes machine without telling anyone, and
this is the check that catches it; `compare` prints the diff anyway and
exits 0, because a human reading the page can judge what a script cannot.

The second fails when the total time grew by more than the two Runs'
combined sampling error. `change` is expressed in the payload's `unit`
and is positive when the branch is slower. `significant` is `false` when
the difference is smaller than that error, and no threshold of yours can
make such a difference real.

To name the functions rather than the run:

```sh
jq -r '.deltas[] | select(.significant and .change > 0)
       | "\(.function) (\(.file)) +\(.change_fraction * 100 | round)%"' delta.json
```

The [machine-readable reference](../../reference/machine-readable.md)
lists every field of the payload.

## Keep the pair comparable

Same runner class, same command line, same rank count. Measure the noise
floor once, by profiling the same unchanged binary twice and comparing
the two Runs: what comes back is the resolution of every gate built on
that workload, and a threshold below it fires on the sampler instead of
on the code. [What makes a delta
real](../compare/what-makes-a-delta-real.md) has the arithmetic - the
error falls as 1/sqrt(n) in the number of samples, so a longer benchmark
buys a tighter gate.

## Refresh the reference on purpose

A reference Run ages: the runner image moves, the machine is replaced,
the benchmark itself is edited. Regenerate it in the same job shape that
produced it, and keep it beside the commit it describes, so that a gate
which fires points at a Run someone can open.
