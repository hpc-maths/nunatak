# Installing nunatak for a team

There is no released package yet. nunatak is not on PyPI, not on
conda-forge and not in spack, and there is no tagged release. What
follows is how to install the development version for a group of users,
and it is what the whole of this site documents.

## Build a wheel once, install it everywhere

The report is a compiled TypeScript application, built into the wheel by
the packaging hook. Node is needed where the wheel is built, and
nowhere else - not on the login node your users work from, not on the
compute nodes.

```sh
git clone https://github.com/hpc-maths/nunatak
cd nunatak
python -m build --wheel        # or: uv build --wheel
```

The result installs into any environment, and a `nunatak doctor` there
reports the report application as present:

```sh
python -m venv /opt/nunatak
/opt/nunatak/bin/pip install dist/nunatak-*.whl
/opt/nunatak/bin/nunatak doctor
```

Installing the checkout directly with `pip install -e .` works too and
skips the hook, which costs the HTML report: `doctor` then declares
`report-unavailable`, and `npm install && npm run build` in `report-app/`
fixes it in place.

The Python that runs nunatak has nothing to do with the Python of the
application being profiled. They are different processes, and the
version thresholds that matter for Python profiling are the
application's. Pick the interpreter for the module or environment you
publish; nunatak itself needs 3.10 or newer and depends only on
`pyarrow`.

## What the site provides

nunatak orchestrates tools it never redistributes. Three of them decide
what a run can measure:

| Tool | Without it |
|---|---|
| `perf` | no sampling at all on Linux: `cpu-collection-unavailable` |
| LLVM 19 or newer | no staleness fingerprints and no loop analysis; 17 and 18 symbolize completely and restrict only the loop analysis, and below that the platform's own `addr2line` or `atos` stands in |
| GNU binutils | no `objdump`, so no loop analysis and no frame-pointer probing |

Optional, each with its own named loss: `mpicc` for the network probe
and mpiP, py-spy for Python below 3.12, Node and pi for the explanations.

`perf` also needs the kernel to allow it. See
[kernel permissions](kernel-permissions.md).

## Check it from a login node

```sh
nunatak doctor
```

Every check invokes the tool it is about rather than trusting `PATH`, so
what it prints is what a user's run will find. Anything missing is named,
with the way forward on the next line, and the
[degradation catalogue](../reference/degradations.md) says what each name
costs.
