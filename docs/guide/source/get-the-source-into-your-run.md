# Get the source into your Run

Profile where you built, and there is nothing to do: the path the
compiler recorded resolves, and each line-level Hotspot gets its extract
beside its name in the report.

The four cases below are the ones where it does not, and each says so in
place of the code rather than showing something else.

## The source is not where it was built

```
source file not found on this machine
```

That is a build directory that no longer exists - a container, a CI
runner, a `$SCRATCH` wiped since. Give nunatak the correspondence:

```sh
nunatak run --source-map /build/solver=/home/me/solver -- ./solver
```

The flag is repeatable and the longest matching prefix wins, so a
subtree can override its parent. A site or a project fixes it once
instead:

```toml
[source_map]
"/build/solver" = "/home/me/solver"
```

With the map in place the extracts come back, and each one records the
path it was actually read from on this machine, next to the path the
compiler had written.

## You edited the file since the build

```
source file changed since the profiled binary was built (line-table MD5 mismatch)
```

The refusal is per file: in a Run whose `kernels.c` had moved on, the
untouched `stencil.c` kept its extract. Rebuild, or profile the code the
binary was built from. This works when the compiler recorded a checksum,
which clang does by default and gcc does not do at all.

## Two files share a basename

```
ambiguous: 2 files named 'solver.c' under /home/me/project
```

The recorded path failed, no map covered it, and the search by name
found more than one candidate. nunatak does not pick: name the right one
with `--source-map`.

## The source must not leave the machine

```sh
nunatak run --no-source -- ./solver
```

Nothing of the code is embedded, and the Run keeps its line numbers, its
per-line sample distribution and every measurement. A Run that already
carries source yields a shareable page without rerunning anything:

```sh
nunatak report --no-source
```

The text is stripped from the payload before the page exists, so the
`report.html` you send out has no copy of the code inside it.
