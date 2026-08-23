# Recording corpus

Real collector outputs, captured once on real hardware and replayed
forever without it. Together with the frozen-binaries corpus
([`binaries/`](binaries/README.md), with its derived llvm-mca listings
in `listings/`), this is one of the two durable assets of the project:
recordings freeze the tools' outputs so the parsers replay without the
tools, binaries freeze the tools' *inputs* so the real tools of a new
version can be run against known ground.

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
| `perf/6.14.11/linux-x86_64/workload-c` | Ubuntu 25.04, AMD EPYC 7702 (self-hosted runner), 2026-08-10 | real PMU cycles, `perf_event_paranoid` lowered to 2 for the capture, same C workload |
| `calibration/v0/darwin-arm64/apple-m5-max` | macOS 26.5.2, Apple M5 Max (18 cores), 2026-08-23 | Apple clang (`-march=native` accepted since Xcode 16), NEON kernel, cold cache so the build is recorded; no load average on macOS |
| `xctrace/16.0/darwin-arm64/triad-c` | macOS 26.5.2, Apple M5 Max, Xcode 16, 2026-08-23 | nominal temporal mode: Time Profiler export with per-address weights, atos + nm symbolization, exit status from the trace TOC |
| `sample/26.5.2/darwin-arm64/triad-c` | macOS 26.5.2, Apple M5 Max, 2026-08-23 | temporal mode via /usr/bin/sample, triad built `cc -O2 -g`, warmed binary (a first launch loses the image list), no LLVM on the machine: atos + nm recorded as the symbolization path |
