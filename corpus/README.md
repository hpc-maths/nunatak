# Recording corpus

Real collector outputs, captured once on real hardware and replayed
forever without it. Together with the frozen-binaries corpus (to come with
the attribution chain), this is one of the two durable assets of the
project.

**Entries are captured, never written by hand.** A hand-written entry only
tests our idea of a tool's output. Every entry here was produced by
nunatak itself:

```sh
nunatak run --record corpus/recordings/<tool>/<version>/<platform>/<scenario> -- <command>
```

Recording saves every process invocation crossing nunatak's execution
boundary - argv, exit code, captured output - plus a `meta.json` with the
platform and detected collector versions. Replaying substitutes those
recordings for the real tools:

```sh
nunatak run --replay corpus/recordings/perf/6.12.101/linux-aarch64/workload-c -- /tmp/workload
```

The test suite replays these entries; a hardware campaign's deliverable is
the refresh of this corpus.

| Entry | Captured on | Notes |
|---|---|---|
| `perf/6.12.101/linux-aarch64/workload-c` | Debian trixie (Docker VM), 2026-08-09 | task-clock fallback (no PMU in the VM), C workload built with `-O2 -g` |
