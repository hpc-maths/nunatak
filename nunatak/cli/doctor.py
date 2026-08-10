"""doctor: inventory of external tools, permissions, target binary.

doctor probes paths and invokes the tools - observing a presence is not
enough (`xcrun --find` lies on a machine whose Xcode was uninstalled, and
Homebrew's LLVM is keg-only, hence never on PATH). A cheap subset of these
checks runs automatically at the start of every `run`: it announces what
will be degraded, then continues.
"""

from __future__ import annotations

import glob
import json
import platform
import re
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

from nunatak.collect.execution import Executor
from nunatak.config import Config
from nunatak.console import Console
from nunatak.pivot import Degradation
from nunatak.target import real_target

MINIMUM_LLVM = 17
RECOMMENDED_LLVM = 19


@dataclass(frozen=True)
class CheckResult:
    """One doctor verdict. `degradation` is set when a capability is lost."""

    name: str
    status: str  # "ok" | "warning" | "missing"
    detail: str
    remedy: str | None = None
    degradation: Degradation | None = None


def tool_version(executor: Executor, argv: list[str], pattern: str) -> str | None:
    """Invoke a tool and extract its version; None when it cannot run."""
    invocation = executor.run(argv)
    if invocation.exit_code != 0:
        return None
    output = f"{invocation.stdout or ''}\n{invocation.stderr or ''}"
    match = re.search(pattern, output)
    return match.group(1) if match else None


def _cpu_collector(executor: Executor, config: Config) -> list[CheckResult]:
    if platform.system() != "Linux":
        degradation = Degradation(
            name="cpu-collection-unavailable",
            message=f"no CPU collector implemented for {platform.system()} yet",
            remedy="hardware-counter profiling requires Linux perf for now",
        )
        return [
            CheckResult(
                name="cpu-collector",
                status="missing",
                detail=degradation.message,
                remedy=degradation.remedy,
                degradation=degradation,
            )
        ]

    path = config.tools.get("perf", "perf")
    version = tool_version(executor, [path, "--version"], r"perf version (\S+)")
    if version is None:
        degradation = Degradation(
            name="cpu-collection-unavailable",
            message=f"perf not usable at '{path}'",
            remedy="install linux-tools for your kernel, or set tools.perf in nunatak.toml",
        )
        return [
            CheckResult(
                name="cpu-collector",
                status="missing",
                detail=degradation.message,
                remedy=degradation.remedy,
                degradation=degradation,
            )
        ]

    checks = [CheckResult(name="cpu-collector", status="ok", detail=f"perf {version} ({path})")]
    paranoid_file = Path("/proc/sys/kernel/perf_event_paranoid")
    if paranoid_file.is_file():
        paranoid = int(paranoid_file.read_text().strip())
        if paranoid >= 3:
            degradation = Degradation(
                name="perf-permissions",
                message=f"kernel.perf_event_paranoid={paranoid} forbids unprivileged profiling",
                remedy="ask for kernel.perf_event_paranoid<=2 or the CAP_PERFMON capability",
            )
            checks.append(
                CheckResult(
                    name="perf-permissions",
                    status="warning",
                    detail=degradation.message,
                    remedy=degradation.remedy,
                    degradation=degradation,
                )
            )
        else:
            checks.append(
                CheckResult(
                    name="perf-permissions",
                    status="ok",
                    detail=f"kernel.perf_event_paranoid={paranoid}",
                )
            )
    return checks


def _llvm_candidates(config: Config) -> list[str]:
    """Paths worth probing for llvm-symbolizer.

    PATH alone cannot be trusted: Homebrew's llvm formula is keg-only, and
    Linux distributions install versioned, unlinked binaries.
    """
    candidates = []
    if "llvm-symbolizer" in config.tools:
        candidates.append(config.tools["llvm-symbolizer"])
    on_path = shutil.which("llvm-symbolizer")
    if on_path:
        candidates.append(on_path)
    candidates += [
        "/opt/homebrew/opt/llvm/bin/llvm-symbolizer",
        "/usr/local/opt/llvm/bin/llvm-symbolizer",
        *sorted(glob.glob("/usr/lib/llvm-*/bin/llvm-symbolizer"), reverse=True),
        *sorted(glob.glob("/usr/bin/llvm-symbolizer-*"), reverse=True),
    ]
    return candidates


def _llvm(executor: Executor, config: Config) -> CheckResult:
    """Probe and invoke llvm-symbolizer; old versions restrict loop analysis."""
    for candidate in _llvm_candidates(config):
        version = tool_version(
            executor, [candidate, "--version"], r"LLVM version (\d+)\.\S*"
        )
        if version is None:
            continue
        major = int(version)
        if major >= RECOMMENDED_LLVM:
            return CheckResult(name="llvm", status="ok", detail=f"LLVM {major} ({candidate})")
        if major >= MINIMUM_LLVM:
            return CheckResult(
                name="llvm",
                status="warning",
                detail=f"LLVM {major} ({candidate})",
                remedy=f"loop analysis is restricted to microarchitectures known to "
                f"LLVM {major}; LLVM {RECOMMENDED_LLVM}+ recommended",
            )
        degradation = Degradation(
            name="llvm-too-old",
            message=f"LLVM {major} at {candidate} is older than {MINIMUM_LLVM}",
            remedy=f"install LLVM {RECOMMENDED_LLVM} or newer; symbolization falls back "
            "to system tools and loop analysis is unavailable",
        )
        return CheckResult(
            name="llvm",
            status="warning",
            detail=degradation.message,
            remedy=degradation.remedy,
            degradation=degradation,
        )
    degradation = Degradation(
        name="llvm-missing",
        message="no usable llvm-symbolizer found",
        remedy=f"install LLVM {RECOMMENDED_LLVM} or newer (brew install llvm, apt install llvm); "
        "symbolization falls back to system tools and loop analysis is unavailable",
    )
    return CheckResult(
        name="llvm",
        status="missing",
        detail=degradation.message,
        remedy=degradation.remedy,
        degradation=degradation,
    )


def _target(command: list[str]) -> CheckResult:
    """Existence and executability of the real target binary."""
    target = real_target(command) or command[0]
    resolved = shutil.which(target) if "/" not in target else target
    if resolved is None or not Path(resolved).is_file():
        return CheckResult(
            name="target-binary",
            status="missing",
            detail=f"{target}: not found",
            remedy="the run would exit with 127",
        )
    # Debug-info, frame-pointer and -lineinfo inspection arrives with the
    # attribution chain.
    return CheckResult(name="target-binary", status="ok", detail=str(resolved))


def light_checks(
    executor: Executor, config: Config, command: list[str]
) -> list[CheckResult]:
    """The cheap subset run at the start of every `run`: no build, no
    benchmark, a few tool invocations."""
    checks = _cpu_collector(executor, config)
    checks.append(_llvm(executor, config))
    if command:
        checks.append(_target(command))
    return checks


def degradations(checks: list[CheckResult]) -> list[Degradation]:
    """The named capability losses among `checks`."""
    return [c.degradation for c in checks if c.degradation is not None]


def execute(args, command: list[str], console: Console) -> int:
    """`nunatak doctor [--json] [-- <command>]`. Returns 0: a diagnosis is
    informative, only `run --strict` turns degradations into errors."""
    from nunatak.collect.execution import SubprocessExecutor
    from nunatak.config import load

    config, _ = load(Path.cwd())
    checks = light_checks(SubprocessExecutor(), config, command)

    if args.json:
        report = {
            "checks": [
                {k: v for k, v in asdict(check).items() if k != "degradation"}
                for check in checks
            ],
            "degradations": [asdict(d) for d in degradations(checks)],
        }
        print(json.dumps(report, indent=2))
        return 0

    for check in checks:
        console.info(f"{check.status:<8} {check.name:<18} {check.detail}")
        if check.remedy:
            console.info(f"{'':<8} {'':<18} -> {check.remedy}")
    return 0
