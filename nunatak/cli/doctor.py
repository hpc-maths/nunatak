"""doctor: inventory of external tools, permissions, target binary.

doctor probes paths and invokes the tools - observing a presence is not
enough (`xcrun --find` lies on a machine whose Xcode was uninstalled, and
Homebrew's LLVM is keg-only, hence never on PATH). A cheap subset of these
checks runs automatically at the start of every `run`: it announces what
will be degraded, then continues.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

from nunatak.attribution import inspection
from nunatak.attribution.symbolizer import MINIMUM_LLVM, RECOMMENDED_LLVM, locate
from nunatak.collect.execution import Executor
from nunatak.config import Config
from nunatak.console import Console
from nunatak.pivot import Degradation
from nunatak import launch, probe
from nunatak.collect import mpip
from nunatak.launch import real_target


@dataclass(frozen=True)
class CheckResult:
    """One doctor verdict. `degradation` is set when a capability is lost."""

    name: str
    status: str  # "ok" | "warning" | "missing"
    detail: str
    remedy: str | None = None
    degradation: Degradation | None = None


def _cpu_collector(
    executor: Executor,
    config: Config,
    preselected: tuple | None = None,
) -> list[CheckResult]:
    """Presence, version and usability of the CPU collector."""
    from nunatak.collect import cpu_collector

    adapter, version = (
        preselected if preselected is not None else cpu_collector(executor, config)
    )
    if adapter is None:
        if executor.system != "Linux":
            degradation = Degradation(
                name="cpu-collection-unavailable",
                message=f"no CPU collector implemented for {executor.system} yet",
                remedy="hardware-counter profiling requires Linux perf for now",
            )
        elif version is not None:
            # The tool is there; the environment forbids sampling.
            reason = executor.sampling_blocked() or "event sampling unavailable"
            degradation = Degradation(
                name="cpu-collection-unavailable",
                message=f"perf {version} found, but {reason}",
                remedy="ask for kernel.perf_event_paranoid<=2 or the CAP_PERFMON capability",
            )
        else:
            path = config.tools.get("perf", "perf")
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

    checks = [
        CheckResult(
            name="cpu-collector", status="ok", detail=f"perf {version} ({adapter.path})"
        )
    ]
    paranoid_file = Path("/proc/sys/kernel/perf_event_paranoid")
    if paranoid_file.is_file():
        checks.append(
            CheckResult(
                name="perf-permissions",
                status="ok",
                detail=f"kernel.perf_event_paranoid={paranoid_file.read_text().strip()}",
            )
        )
    return checks


def _llvm(symbolizer) -> CheckResult:
    """Verdict on the located llvm-symbolizer; old versions restrict loop
    analysis."""
    if symbolizer is not None:
        if symbolizer.major >= RECOMMENDED_LLVM:
            return CheckResult(
                name="llvm",
                status="ok",
                detail=f"LLVM {symbolizer.major} ({symbolizer.path})",
            )
        if symbolizer.major >= MINIMUM_LLVM:
            return CheckResult(
                name="llvm",
                status="warning",
                detail=f"LLVM {symbolizer.major} ({symbolizer.path})",
                remedy=f"loop analysis is restricted to microarchitectures known to "
                f"LLVM {symbolizer.major}; LLVM {RECOMMENDED_LLVM}+ recommended",
            )
        degradation = Degradation(
            name="llvm-too-old",
            message=f"LLVM {symbolizer.major} at {symbolizer.path} is older "
            f"than {MINIMUM_LLVM}",
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


def _resolved_target(command: list[str]) -> tuple[str, Path | None]:
    """The real target binary of `command` and where it lives, None when
    it cannot be found on this machine."""
    target = real_target(command) or command[0]
    resolved = shutil.which(target) if "/" not in target else target
    if resolved is None or not Path(resolved).is_file():
        return target, None
    return target, Path(resolved)


def _target(command: list[str]) -> CheckResult:
    """Existence and executability of the real target binary."""
    target, resolved = _resolved_target(command)
    if resolved is None:
        return CheckResult(
            name="target-binary",
            status="missing",
            detail=f"{target}: not found",
            remedy="the run would exit with 127",
        )
    return CheckResult(name="target-binary", status="ok", detail=str(resolved))


def _attribution_ceiling(
    executor: Executor, command: list[str], symbolizer
) -> CheckResult | None:
    """How far attribution will go on the target binary, announced before
    any compute time is spent: the `-g` incentive made readable, not
    punitive. None when there is no binary to inspect or no LLVM to
    inspect it with - the other checks already said so.
    """
    _, resolved = _resolved_target(command)
    if resolved is None or symbolizer is None:
        return None
    sections = inspection.inspect(
        executor, inspection.readelf_path(symbolizer.path), str(resolved)
    )
    if sections is None:
        return CheckResult(
            name="target-attribution",
            status="warning",
            detail=f"cannot inspect {resolved}",
            remedy="attribution will be decided at analysis time",
        )
    if sections.debug_info:
        return CheckResult(
            name="target-attribution",
            status="ok",
            detail="debug information present: line-level attribution",
        )
    if sections.symtab:
        return CheckResult(
            name="target-attribution",
            status="warning",
            detail="no debug information: attribution capped at function level",
            remedy="compile with -g to get line numbers, inlining and source extracts",
        )
    if sections.dynsym:
        return CheckResult(
            name="target-attribution",
            status="warning",
            detail="stripped binary: attribution capped at symbol level",
            remedy="keep the symbol table, or compile with -g",
        )
    return CheckResult(
        name="target-attribution",
        status="warning",
        detail="no symbol table at all: Hotspots will stay unresolved",
        remedy="compile with -g, or at least keep the symbol table",
    )


def _report_asset() -> CheckResult:
    """Presence of the compiled report mini-app in this installation."""
    from nunatak.report import html

    if html.assets_available():
        return CheckResult(name="report-app", status="ok", detail=str(html.ASSETS))
    degradation = Degradation(
        name="report-unavailable",
        message="the compiled report app is missing from this installation",
        remedy="reinstall nunatak from a built wheel; on a development checkout, "
        "run `npm install && npm run build` in report-app/",
    )
    return CheckResult(
        name="report-app",
        status="missing",
        detail=degradation.message,
        remedy=degradation.remedy,
        degradation=degradation,
    )


def _mpi_analysis(config: Config) -> CheckResult:
    """Presence of mpiP for the MPI counting layer of this launch."""
    library = mpip.locate(config)
    if library is not None:
        return CheckResult(name="mpiP", status="ok", detail=library)
    degradation = Degradation(
        name="mpi-analysis-unavailable",
        message="libmpiP.so not found: no per-rank MPI times or volumes",
        remedy="load the site's mpiP module (it must appear in "
        "LD_LIBRARY_PATH) or set tools.mpip in nunatak.toml",
    )
    return CheckResult(
        name="mpiP",
        status="missing",
        detail=degradation.message,
        remedy=degradation.remedy,
        degradation=degradation,
    )


def _network_probe(executor: Executor, config: Config) -> CheckResult:
    """MPI stack identification and the probe build, cached by stack.

    Building here is deliberate: doctor runs on a login node, where the
    compilers are; the compute nodes reuse the cached binary.
    """
    mpi_stack = probe.stack(executor, config)
    if mpi_stack is None:
        degradation = Degradation(
            name="network-analysis-unavailable",
            message="no usable mpicc: the network probe cannot be built",
            remedy="load the MPI module (mpicc must answer) or set "
            "tools.mpicc in nunatak.toml",
        )
        return CheckResult(
            name="network-probe",
            status="missing",
            detail=degradation.message,
            remedy=degradation.remedy,
            degradation=degradation,
        )
    binary = probe.build(executor, mpi_stack)
    if binary is None:
        degradation = Degradation(
            name="network-analysis-unavailable",
            message=f"the network probe failed to build with {mpi_stack.mpicc} "
            f"({mpi_stack.label})",
            remedy="the compiler's messages above say more",
        )
        return CheckResult(
            name="network-probe",
            status="missing",
            detail=degradation.message,
            remedy=degradation.remedy,
            degradation=degradation,
        )
    return CheckResult(
        name="network-probe", status="ok", detail=f"{mpi_stack.label}: {binary}"
    )


def light_checks(
    executor: Executor,
    config: Config,
    command: list[str],
    cpu: tuple | None = None,
    llvm: tuple | None = None,
    build_probe: bool = False,
) -> list[CheckResult]:
    """The cheap subset run at the start of every `run`: no build, no
    benchmark, a few tool invocations. `cpu` carries an already-selected
    (adapter, version) and `llvm` an already-located (symbolizer,), so no
    tool is probed twice."""
    symbolizer = llvm[0] if llvm is not None else locate(executor, config)
    checks = _cpu_collector(executor, config, preselected=cpu)
    checks.append(_llvm(symbolizer))
    checks.append(_report_asset())
    if command:
        checks.append(_target(command))
        if launch.split(command).mpi:
            checks.append(_mpi_analysis(config))
            if build_probe:
                checks.append(_network_probe(executor, config))
        ceiling = _attribution_ceiling(executor, command, symbolizer)
        if ceiling is not None:
            checks.append(ceiling)
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
    executor = SubprocessExecutor()
    checks = light_checks(executor, config, command)
    # The probe build belongs to the doctor verb, not to the light
    # checks a run opens with: doctor runs where the compilers are, and
    # a cached probe makes the next MPI run's network analysis possible.
    checks.append(_network_probe(executor, config))

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
