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

from nunatak.attribution import debuginfod, inspection
from nunatak.attribution.addr2line import Addr2Line
from nunatak.attribution.atos import Atos
from nunatak.attribution.symbolizer import (
    MINIMUM_LLVM,
    RECOMMENDED_LLVM,
    TESTED_LLVM,
)
from nunatak.collect.execution import Executor
from nunatak.config import Config
from nunatak.console import Console
from nunatak.pivot import Degradation
from nunatak import launch, probe
from nunatak.collect import mpip, stacks
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
        if executor.system == "Darwin":
            path = config.tools.get("sample", "/usr/bin/sample")
            degradation = Degradation(
                name="cpu-collection-unavailable",
                message=f"sample not usable at '{path}'",
                remedy="set tools.sample in nunatak.toml; the tool ships "
                "with macOS",
            )
        elif executor.system != "Linux":
            degradation = Degradation(
                name="cpu-collection-unavailable",
                message=f"no CPU collector implemented for {executor.system} yet",
                remedy="profiling requires Linux perf or macOS sample for now",
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
            name="cpu-collector",
            status="ok",
            detail=f"{adapter.tool} {version} ({adapter.path})",
        )
    ]
    if adapter.tool in ("sample", "xctrace"):
        # The platform's degraded mode, announced where the user checks:
        # not a capability this machine lost, the shape of macOS itself.
        checks.append(
            CheckResult(
                name="hotspot-counters",
                status="warning",
                detail="macOS exposes no per-Hotspot counter events: "
                "temporal sampling, roofline from estimated ceilings",
                remedy="the L1 arithmetic intensity comes from the static "
                "loop analysis where LLVM can disassemble",
            )
        )
    if executor.system == "Darwin":
        from nunatak.collect import powermetrics

        if powermetrics.allowed(executor):
            checks.append(
                CheckResult(
                    name="power-aggregates",
                    status="ok",
                    detail=f"powermetrics allowed by the sudoers policy "
                    f"({powermetrics.TOOL})",
                )
            )
        else:
            degradation = Degradation(
                name="power-aggregates-unavailable",
                message="powermetrics needs root and the sudoers policy "
                "does not allow it: no energy aggregates",
                remedy="optional; allow it with a sudoers rule: "
                f"NOPASSWD: {powermetrics.TOOL}",
            )
            checks.append(
                CheckResult(
                    name="power-aggregates",
                    status="warning",
                    detail=degradation.message,
                    remedy=degradation.remedy,
                    degradation=degradation,
                )
            )
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
    """Verdict on the located symbolizer; old LLVM versions restrict loop
    analysis, the addr2line fallback is declared second-choice, and a
    major newer than the validated window earns a warning and nothing
    else - too-new is not a capability loss, so it carries no
    degradation."""
    if isinstance(symbolizer, (Addr2Line, Atos)):
        tool = "GNU addr2line" if isinstance(symbolizer, Addr2Line) else "atos"
        degradation = Degradation(
            name="llvm-missing",
            message=f"no usable llvm-symbolizer found; {tool} "
            f"{symbolizer.version} ({symbolizer.path}) stands in",
            remedy=f"attribution works, without staleness fingerprints; "
            f"install LLVM {RECOMMENDED_LLVM}+ for them and for loop analysis",
        )
        return CheckResult(
            name="llvm",
            status="warning",
            detail=degradation.message,
            remedy=degradation.remedy,
            degradation=degradation,
        )
    if symbolizer is not None:
        if symbolizer.major > TESTED_LLVM:
            return CheckResult(
                name="llvm",
                status="warning",
                detail=f"LLVM {symbolizer.major} ({symbolizer.path}): not yet "
                "validated with this version of nunatak",
                remedy=f"the validated window ends at LLVM {TESTED_LLVM}; "
                "everything runs, and a parser this version breaks fails "
                "loudly, not silently",
            )
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
    if resolved is None or symbolizer is None or symbolizer.readelf is None:
        # atos rides with no section reader: Mach-O is not ELF, and a
        # ceiling claimed without an inventory would be a guess.
        return None
    sections = inspection.inspect(
        executor, symbolizer.readelf, str(resolved)
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


def _debuginfod(config: Config) -> CheckResult | None:
    """What debuginfod will do at analysis time, None when no server is
    configured - absence is the normal case, not a finding. The controls
    exist because both symbolization paths consult the client on their
    own: better a declared timeout than a silent 90-second hang."""
    sentence = debuginfod.status(config)
    if sentence is None:
        return None
    return CheckResult(name="debuginfod", status="ok", detail=sentence)


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


def _mpi_analysis(executor: Executor, config: Config) -> CheckResult:
    """Presence of mpiP for the MPI counting layer of this launch."""
    library = mpip.locate(config, mpi_stack=probe.stack(executor, config))
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


def _mpip_build(executor: Executor, config: Config) -> CheckResult:
    """Locate mpiP or build the pinned source for this MPI stack.

    Building belongs here, like the probe's: doctor runs where the
    compilers are, the download is checksummed against the pin, and the
    library lands in the stack's cache entry for every later run.
    """
    mpi_stack = probe.stack(executor, config)
    library = mpip.locate(config, mpi_stack=mpi_stack) if mpi_stack else None
    if library is not None:
        return CheckResult(name="mpiP-build", status="ok", detail=library)
    remedy = (
        "install mpiP through your site's modules or spack and set "
        "tools.mpip in nunatak.toml"
    )
    if mpi_stack is None:
        degradation = Degradation(
            name="mpi-analysis-unavailable",
            message="no usable mpicc: mpiP cannot be located or built",
            remedy=remedy,
        )
    else:
        fortran = mpip.fortran_wrapper(executor, config)
        if fortran is None:
            degradation = Degradation(
                name="mpi-analysis-unavailable",
                message="mpiP needs a Fortran MPI wrapper (mpifort) to build,"
                " and none answers",
                remedy=remedy,
            )
        else:
            built = mpip.build(executor, mpi_stack, fortran)
            if built is not None:
                return CheckResult(
                    name="mpiP-build",
                    status="ok",
                    detail=f"built for {mpi_stack.label}: {built}",
                )
            degradation = Degradation(
                name="mpi-analysis-unavailable",
                message="the pinned mpiP source could not be fetched or built",
                remedy="offline login node? " + remedy,
            )
    return CheckResult(
        name="mpiP-build",
        status="missing",
        detail=degradation.message,
        remedy=degradation.remedy,
        degradation=degradation,
    )


def _call_stacks(
    executor: Executor, config: Config, command: list[str], cpu_model: str | None
) -> CheckResult | None:
    """The call-stack ladder settled for this target: lbr, fp, or none.

    None when there is no binary to probe, or outside Linux - macOS
    stacks are free and reliable by ABI, the ladder has no meaning
    there. Losing the ladder is a degradation, not an error: it removes
    the attachment of library leaves to user code and the inclusive
    time, never the roofline, which only depends on the leaf.
    """
    _, resolved = _resolved_target(command)
    if resolved is None or executor.system != "Linux":
        return None
    decision = stacks.decide(executor, config, str(resolved), cpu_model)
    if decision.mode is not None:
        return CheckResult(
            name="call-stacks", status="ok", detail=decision.detail
        )
    degradation = Degradation(
        name="call-stacks-unavailable",
        message=decision.detail,
        remedy=decision.remedy,
    )
    return CheckResult(
        name="call-stacks",
        status="missing",
        detail=degradation.message,
        remedy=degradation.remedy,
        degradation=degradation,
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
    from nunatak.attribution import locate_any

    symbolizer = llvm[0] if llvm is not None else locate_any(executor, config)
    checks = _cpu_collector(executor, config, preselected=cpu)
    checks.append(_llvm(symbolizer))
    server = _debuginfod(config)
    if server is not None:
        checks.append(server)
    checks.append(_report_asset())
    if command:
        checks.append(_target(command))
        if launch.split(command).mpi:
            checks.append(_mpi_analysis(executor, config))
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
    # The probe and mpiP builds belong to the doctor verb, not to the
    # light checks a run opens with: doctor runs where the compilers
    # are, and the cached artifacts make the next MPI run's network
    # analysis possible. The call-stack ladder sits here for the same
    # reason of cost - probing prologues means a dozen tool invocations.
    checks.append(_network_probe(executor, config))
    checks.append(_mpip_build(executor, config))
    if command:
        ladder = _call_stacks(executor, config, command, executor.cpu_model())
        if ladder is not None:
            checks.append(ladder)

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
