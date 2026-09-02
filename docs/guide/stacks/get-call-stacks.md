# Get call stacks

Ask before you run. Given a command, `doctor` settles which stacks a run
of that binary can afford and says so in one row:

```sh
nunatak doctor -- ./stencil
```

```
missing  call-stacks        frame pointers kept in 44% of prologues (12 probed across 2 modules), below the 75% threshold; worst offender: stencil (0%)
                            -> recompile with -fno-omit-frame-pointer, libraries included, to walk stacks at sampling cost
```

On a processor with hardware branch stacks - Intel, in practice - the row
reads `lbr` instead and there is nothing to do: some thirty frames at
near-zero cost, whatever the binary was compiled from.

## Recompile, and check the rate again

The rate counts prologues that establish a frame pointer, in the target
and in its shared libraries. Adding the flag to your own code moves it:

```
missing  call-stacks        frame pointers kept in 56% of prologues (12 probed across 2 modules), below the 75% threshold; worst offender: stencil (25%)
                            -> recompile with -fno-omit-frame-pointer, libraries included, to walk stacks at sampling cost
```

That is `examples/stencil` rebuilt with `-fno-omit-frame-pointer`, and it
is still refused. The reason is worth knowing before spending an
afternoon on it: gcc establishes no frame pointer in a function that
needs no stack frame of its own, leaf numerical kernels included, whether
or not the flag is on. On such code the rate stays where it is, and the
libraries you did not rebuild hold the rest of it down.

## The mode that always works

```sh
nunatak run --call-graph dwarf -- ./stencil
```

```
--call-graph dwarf: stack memory copied at every sample; frequency lowered to 97 Hz
```

It works on any binary, frame pointers or not, by copying stack memory at
every sample. That cost is why the frequency drops from 997 Hz to 97 Hz
and why the line announcing it exists: the ladder never selects this mode
on its own. On the run above, each of the three kernels came back with
`main` as its caller at 100%.

## Move the threshold

The rate below which the `fp` rung is refused is configuration, and it
rides in the Run's provenance like every other effective setting:

```toml
[stacks]
fp_threshold = 0.75
```

Lower it to accept stacks that are partially walkable, knowing the
missing frames will not announce themselves. The [configuration
reference](../../reference/configuration.md) lists the key with the rest
of the file.

## What a run without stacks still gives you

Every measurement, every classification, and the whole roofline: a
placement depends on the leaf, never on the path that reached it. What is
lost is named `call-stacks-unavailable` in the [degradation
catalogue](../../reference/degradations.md) - the immediate callers of
each Hotspot, and the inclusive share of time. Neither is reported as
zero; both say they are unknown.
