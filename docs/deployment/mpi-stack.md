# The site's MPI stack

Two of nunatak's pieces link against MPI: the **network probe**, which
measures the interconnect's bandwidth and latency, and **mpiP**, which
gives the per-rank MPI times and volumes. The ABIs of OpenMPI, MPICH,
Intel MPI and Cray MPICH are mutually incompatible, so neither is ever
shipped built. Both are compiled with the site's own compilers, once per
stack, and cached.

## Build them where the compilers are

```sh
nunatak doctor
```

That is the whole procedure, and a login node is where to run it: compute
nodes often carry no compiler, and on a cluster with modules the MPI
loaded at install time is rarely the job's.

`doctor` identifies the stack, builds what is missing, and caches both
artifacts under one key:

```
$XDG_CACHE_HOME/nunatak/probes/<implementation-version-mpicc>/
  probe-v1
  libmpiP.so
  stack.json
```

The key is the triple of implementation, version and `mpicc`, so a
machine with three modules ends up with three entries and no confusion
between them. The identified stack is recorded in each Run's provenance:
a network measurement whose underlying stack is unknown is not
interpretable.

**A run never builds anything.** Without a cached probe it declares
`network-ceiling-unavailable` and names `doctor` as the way forward,
because building inside an allocation the user pays for is not a
decision the tool takes.

## What each one needs

| | Needs | Without it |
|---|---|---|
| network probe | a working `mpicc` | `network-analysis-unavailable` at diagnosis, `network-ceiling-unavailable` at run time: no interconnect roof |
| mpiP | `mpicc`, a Fortran wrapper, and one network fetch | `mpi-analysis-unavailable`: no per-rank MPI time or volume |

Point them at the site's compilers when they are not first on `PATH`:

```toml
[tools]
mpicc = "/opt/openmpi-5.0/bin/mpicc"
mpifort = "/opt/openmpi-5.0/bin/mpifort"
```

mpiP's own build requires a Fortran wrapper: `tools.mpifort` wins, then
the conventional names. Its source is pinned to one commit and verified
against a checksum, fetched once. **Once fetched it rebuilds offline
forever**, which matters on a login node with no outbound network: fetch
it on a machine that has one, or install mpiP yourself and point
`tools.mpip` at the library.

## If mpiP is already installed here

nunatak looks for `libmpiP.so` in order: `tools.mpip`, then each
directory of `LD_LIBRARY_PATH` - which is how an environment module
exposes it - then `/usr/local/lib` and `/usr/lib`, then its own cache.

A site that publishes mpiP as a module therefore needs no configuration
at all: loading the module is enough. The library is preloaded into every
rank with `LD_PRELOAD`, appended to whatever the site already preloads,
and the application is never recompiled.

The path is resolved on the login node and used on the compute nodes, so
it has to hold there too. A shared filesystem gives that for free.
