# Install nunatak

There is no released package yet: nothing on PyPI, nothing on
conda-forge, no spack entry and no tag. Install from the repository.

## Build the wheel, then install it

The report is a compiled TypeScript application that the packaging hook
builds into the wheel, so Node is needed where the wheel is built and
nowhere else:

```sh
git clone https://github.com/hpc-maths/nunatak
cd nunatak
uv build --wheel            # or: python -m build --wheel
pip install dist/nunatak-*.whl
```

nunatak runs on Python 3.10 or newer and depends on `pyarrow`, plus
`tomli` below 3.11.

Installing the checkout in place with `pip install -e .` skips the hook,
which costs the HTML report: `doctor` declares `report-unavailable`, and
`npm install && npm run build` in `report-app/` fixes it without
reinstalling anything.

The interpreter you install into has nothing to do with the one you
profile. They are separate processes, and the Python version that decides
what a profiled Python application shows is the application's. Installing
nunatak for a whole team is [Deployment's own
page](../deployment/installing.md).

## Check what this machine can measure

```sh
nunatak doctor
```

Every check invokes the tool it is about instead of trusting `PATH`, so
what it prints is what your next run will find:

```
ok       cpu-collector      perf 6.14.11 (/usr/bin/perf)
ok       llvm               LLVM 20 (/usr/lib/llvm-20/bin/llvm-symbolizer)
missing  explanation        Node.js or pi not usable at 'pi': no LLM explanations
                            -> install Node.js and pi (npm install -g @earendil-works/pi-coding-agent), or set tools.pi in nunatak.toml
```

A `missing` row is a named degradation rather than an error: the run goes
ahead and the Run carries fewer measurements. Each name has an entry in
the [degradation catalogue](../reference/degradations.md) saying what was
lost and what to do about it.

## What the machine has to provide

nunatak orchestrates tools it never redistributes. On Linux,
[`perf`](https://perfwiki.github.io/main/) decides whether anything is
sampled at all; [LLVM](https://llvm.org/) 19 or newer decides whether
Hotspots carry source positions, staleness fingerprints and loop facts;
[GNU binutils](https://www.gnu.org/software/binutils/) provides the
`objdump` that the loop analysis and the frame-pointer probing read. What
each absence costs is tabulated in
[Installing nunatak for a team](../deployment/installing.md), and
`doctor` names it on the machine in front of you.

`perf` also needs the kernel to allow unprivileged profiling, which is
not something a user can install:
[kernel permissions](../deployment/kernel-permissions.md) is the page to
hand to whoever administers the machine.

Optional, each with its own named loss: `mpicc` for the network probe and
[mpiP](https://github.com/LLNL/mpiP),
[py-spy](https://github.com/benfred/py-spy) for Python below 3.12,
[Node.js](https://nodejs.org/) and [pi](https://pi.dev) for the
explanations.

## On macOS

Sampling is temporal there and no per-Hotspot counter exists, so the
roofline stays out of reach while the rest of the loop works.
[macOS](../guide/macos/index.md) says what the platform can and cannot
say, and `powermetrics` needs
[a sudoers rule](../deployment/powermetrics.md) to report power.
