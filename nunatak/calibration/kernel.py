"""Calibration kernel driver: build locally, run autonomously, keep the max.

The embedded C sources are compiled with whatever compiler the machine
offers - there is always a compiler on a cluster - cached next to the
Machine profiles, and run as a separate process through the execution
boundary, so a calibration records and replays like any collector. A
Ceiling is the maximum of its repetitions, never their mean: the goal is
an upper bound. Pollution signals (dispersion between repetitions,
concurrent load, a kernel built without SIMD, a value above the
theoretical peak) downgrade the Ceiling to `estimated` with the reason,
they never discard it.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from nunatak import machine as machine_module
from nunatak.collect.execution import Executor
from nunatak.config import Config
from nunatak.pivot import Ceiling, Machine, Quality

# Priority order: without DRAM bandwidth and the double-precision peak
# there is no roofline; anything after them is refinement. A partial
# profile is exploitable, the budget cuts from the tail.
KERNELS = (
    ("dram_bandwidth", "triad", "byte/s"),
    ("flops_dp", "fma_dp", "flop/s"),
    ("flops_sp", "fma_sp", "flop/s"),
)

REPETITIONS = 5
MILLISECONDS_PER_REPETITION = 300
BUDGET_SECONDS = 60.0
DISPERSION_THRESHOLD = 0.10
LOAD_PER_CORE_THRESHOLD = 0.5
# The theoretical peak itself can be approximate (observed frequency,
# widest-SKU table entry): an anomaly is a gross violation - a broken
# timer, a miscounted loop - not a boost-induced few percent.
ANOMALY_FACTOR = 1.25

_SOURCE = Path(__file__).parent / "kernel.c"


@dataclass(frozen=True)
class KernelRun:
    """Parsed output of one kernel invocation: the self-reported build
    ISA and load average travel with the rates, so a replayed
    calibration sees the same pollution signals as the recorded one."""

    kernel: str
    isa: str | None
    threads: int | None
    load: float | None
    rates: tuple[float, ...]


def compiler(executor: Executor, config: Config) -> str | None:
    """The first C compiler that answers, None when the machine has none.

    `tools.cc` in the configuration wins, then the conventional names.
    """
    candidates = []
    if "cc" in config.tools:
        candidates.append(config.tools["cc"])
    candidates += ["cc", "gcc", "clang"]
    for candidate in candidates:
        if executor.run([candidate, "--version"]).exit_code == 0:
            return candidate
    return None


def build(executor: Executor, cc: str, directory: Path) -> Path | None:
    """Compile the embedded kernel into `directory`, reusing a previous
    build of the same kernel version.

    `-march=native` first; Apple's clang on arm64 only accepts
    `-mcpu=native`, hence the second attempt.
    """
    # The version lives in the directory, never in the binary's name:
    # replayed corpus entries match invocations by base name, so a
    # bumped kernel keeps replaying yesterday's recordings, while the
    # versioned directory still guarantees a stale cached build is
    # never reused.
    binary = (
        directory / "kernel" / f"v{machine_module.KERNEL_VERSION}" / "kernel"
    )
    if binary.is_file():
        return binary
    binary.parent.mkdir(parents=True, exist_ok=True)
    for isa_flag in ("-march=native", "-mcpu=native"):
        invocation = executor.run(
            [cc, "-O3", isa_flag, "-pthread", str(_SOURCE), "-o", str(binary)]
        )
        if invocation.exit_code == 0:
            return binary
    return None


def parse(stdout: str) -> KernelRun | None:
    """Parse the kernel's output lines, None when they are not its."""
    kernel = isa = None
    threads = None
    load = None
    rates = []
    for line in stdout.splitlines():
        parts = line.split()
        if parts[:1] == ["kernel"] and len(parts) == 2:
            kernel = parts[1]
        elif parts[:1] == ["isa"] and len(parts) == 2:
            isa = parts[1]
        elif parts[:1] == ["threads"] and len(parts) == 2:
            threads = int(parts[1])
        elif parts[:1] == ["load"] and len(parts) == 2:
            load = float(parts[1])
            if load < 0:
                load = None
        elif parts[:1] == ["rep"] and len(parts) == 3:
            rates.append(float(parts[2]))
    if kernel is None:
        return None
    return KernelRun(
        kernel=kernel, isa=isa, threads=threads, load=load, rates=tuple(rates)
    )


def measure(
    executor: Executor,
    binary: Path,
    kernel: str,
    threads: int,
    repetitions: int = REPETITIONS,
    milliseconds: int = MILLISECONDS_PER_REPETITION,
) -> KernelRun | None:
    """One autonomous kernel process, its output parsed; None on failure."""
    invocation = executor.run(
        [str(binary), kernel, str(threads), str(repetitions), str(milliseconds)]
    )
    if invocation.exit_code != 0 or not invocation.stdout:
        return None
    return parse(invocation.stdout)


def _pollution(
    outcome: KernelRun, threads: int, theoretical: float | None
) -> list[str]:
    """The reasons this measurement does not deserve `measured`, empty
    when none apply.

    The load is judged against the thread count the kernel itself
    reports, never the caller's: a replayed measurement must be judged
    in the context it was recorded in, not the replaying machine's.
    """
    reasons = []
    if outcome.rates:
        top, bottom = max(outcome.rates), min(outcome.rates)
        if top > 0 and (top - bottom) / top > DISPERSION_THRESHOLD:
            reasons.append(
                f"repetitions disperse by {(top - bottom) / top:.0%}"
            )
    cores = outcome.threads if outcome.threads else threads
    if outcome.load is not None and outcome.load > LOAD_PER_CORE_THRESHOLD * cores:
        reasons.append(
            f"concurrent load {outcome.load:g} on {cores} allocated cores"
        )
    if outcome.isa == "scalar" and outcome.kernel != "triad":
        reasons.append("kernel built without SIMD: this is not the machine's peak")
    if theoretical is not None and outcome.rates:
        # `theoretical` is scaled to the caller's allocation; the kernel
        # may have run with another thread count (a replayed entry).
        # Re-scale per core so the reference matches the measurement's
        # own context - on a live run the two are equal.
        reference = theoretical
        if outcome.threads and threads:
            reference = theoretical / threads * outcome.threads
        if max(outcome.rates) > ANOMALY_FACTOR * reference:
            reasons.append(
                "far above the theoretical peak of this microarchitecture"
            )
    return reasons


def calibrate(
    executor: Executor,
    machine: Machine,
    config: Config,
    directory: Path | None = None,
    budget_seconds: float = BUDGET_SECONDS,
    theoretical: dict[str, float] | None = None,
    clock=time.monotonic,
) -> tuple[Ceiling, ...]:
    """Measure the Ceilings of `machine`, in priority order, within the
    budget.

    Returns the measured Ceilings only - possibly none, when no compiler
    exists or the kernel cannot be built: the theoretical table remains
    the caller's fallback for whatever is missing. `theoretical` maps
    Ceiling names to the table's peaks, so a measurement above its
    theoretical bound is caught and downgraded.
    """
    cc = compiler(executor, config)
    if cc is None:
        return ()
    binary = build(
        executor, cc, machine_module.cache_directory() if directory is None else directory
    )
    if binary is None:
        return ()

    threads = max(1, int(machine_module.allocated_cores(machine) or 1))
    started = clock()
    ceilings = []
    for name, kernel, unit in KERNELS:
        if clock() - started > budget_seconds:
            break
        outcome = measure(executor, binary, kernel, threads)
        if outcome is None or not outcome.rates:
            continue
        reasons = _pollution(
            outcome, threads, (theoretical or {}).get(name)
        )
        ceilings.append(
            Ceiling(
                name=name,
                value=max(outcome.rates),
                unit=unit,
                quality=Quality.ESTIMATED if reasons else Quality.MEASURED,
                reason="; ".join(reasons) if reasons else None,
            )
        )
    return tuple(ceilings)
