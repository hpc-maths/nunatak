# Profile a Python application

Name the interpreter in the command:

```sh
nunatak run -- python3 solver.py
nunatak run -- mpirun -n 8 python3 solver.py
```

Detection reads that name and nothing else. A script launched through
its own shebang, `nunatak run -- ./solver.py`, is profiled as a native
program and no Python frame appears in the Run: the name in the command
is the only witness a replayed Run can reproduce. Both of the paths
below are Linux's.

## Check the path before you spend an allocation

`nunatak doctor -- python3 solver.py` adds one row for the interpreter it
found:

```
ok       python-target      CPython 3.13: Python frames exposed to perf via trampolines (PYTHONPERFSUPPORT=1)
```

An older CPython prints one of two other rows, depending on whether
[py-spy](https://github.com/benfred/py-spy) is installed:

```
warning  python-target      py-spy 0.4.2 stands in: temporal sampling, no hardware counters
warning  python-target      CPython 3.10 predates the perf trampolines: Python functions stay invisible, only native frames are attributed
```

The second one is the degradation `python-hotspots-unavailable`, and the
row carries its remedy.

## Read what the run prints

Nothing in the application changes, and the Hotspots are Python
functions:

```
call stacks: fp: frame pointers kept in 92% of prologues (40 probed across 5 modules)
CPython 3.13: Python frames exposed to perf (PYTHONPERFSUPPORT=1)
collecting with perf 6.14.11: python3 solver.py
edge 0.982162
summary: 2 Hotspots above the statistical floor hold 100% of the sampled time (12232 samples of task-clock over 12.3 s)
  sweep (function) - 61% of the sampled time - no placement: no dram_bytes raw counter in this Run
  residual (function) - 39% of the sampled time - no placement: no dram_bytes raw counter in this Run
```

`sweep` and `residual` are the two functions of `solver.py`, named at
`(file, function)` grain. `edge 0.982162` is the application's own
output, which passes through untouched.

## Below CPython 3.12, install py-spy

```sh
pip install py-spy
```

The run then says what it collects with and what that costs, before the
application starts:

```
CPython 3.10 predates the perf trampolines: py-spy 0.4.2 samples temporally
degraded [python-counters-unavailable]: CPython 3.10 predates the perf trampolines; py-spy samples temporally: no hardware counters for this Run - CPython 3.12 or newer restores the counter path
collecting with py-spy 0.4.2: ~/.local/bin/python3.10 solver.py
summary: 2 Hotspots above the statistical floor hold 100% of the sampled time (8228 samples of cpu-clock over 8.25 s)
  sweep (function) - 65% of the sampled time - no placement: no flops_dp raw counter in this Run
  residual (function) - 34% of the sampled time - no placement: no flops_dp raw counter in this Run
```

The same two Hotspots, at the same grain, with time and no hardware
counter. The fallback covers Linux and non-MPI launches: an old CPython
under `mpirun` keeps its native attribution and declares
`python-hotspots-unavailable`.

## Name the Run yourself

The Run directory is named after the profiled binary, which for an
interpreted application is the interpreter:

```
Run: .nunatak/python3-20260901-045122
```

`--name solver` wins over everything, and a `name` in `nunatak.toml`
names every Run of the project. The
[Run directory](../../reference/run-directory.md) reference has the
whole cascade.
