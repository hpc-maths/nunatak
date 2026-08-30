# powermetrics on macOS

`powermetrics` is a root tool, and letting it run is a site decision in
exactly the way perf's paranoid level is one.

Allowed, it rides along with a run and leaves three Locus-level
aggregates, each `estimated` with its reason: the profiled process's
`energy_impact`, which is Apple's abstract number and explicitly not
joules, and the package-wide `cpu_energy` and `gpu_energy` in millijoules
over the sampling window.

```
%admin ALL=(root) NOPASSWD: /usr/bin/powermetrics
```

Refused, the run declares `power-aggregates-unavailable` and loses
nothing else: no measurement, no Hotspot and no roofline depends on
these three numbers.

A full `powermetrics` sample enumerates every process on the machine, two
megabytes per second under a profiler, measured. nunatak filters the
stream as it arrives, down to what the three aggregates need.
