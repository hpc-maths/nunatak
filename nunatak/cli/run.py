"""run: measure the application, write the Run, propagate its exit code.

Order of operations: the light doctor announces degradations before any
compute time is spent; `--strict` stops there with code 121; the command is
checked (127/126) before the Run directory is created; the application then
executes with its output untouched, and the pivot is written whatever its
exit code - a failing application still deserves its measurements.
"""

from __future__ import annotations

import dataclasses
import datetime
import json
import os
import platform
import re
import shutil
import sys
from pathlib import Path

from nunatak import analysis, attribution, corpus, ingestion, launch, machine, probe, provenance, summary
from nunatak.attribution import debuginfod, loops as loop_analysis, source, staleness
from nunatak.collect import events as counter_events
from nunatak.calibration import theory
from nunatak.cli import calibrate, doctor
from nunatak.collect import cpu_collector
from nunatak.collect.execution import Executor, SubprocessExecutor
from nunatak.config import Config, load
from nunatak.console import Console
from nunatak.exit_codes import (
    COMMAND_NOT_EXECUTABLE,
    COMMAND_NOT_FOUND,
    FAILURE_BEFORE_LAUNCH,
    STRICT_VIOLATION,
)
from nunatak.collect import mpip, stacks
from nunatak.ingestion import mpip_report, rank_counting
from nunatak.pivot import (
    Collector,
    Degradation,
    Pass,
    ResolutionLevel,
    Run,
    hotspot_level,
    write_run,
)
from nunatak.report import html
from nunatak.launch import real_target

COLLECT_DIR = "collect"

# Copying stack memory at every sample costs orders of magnitude more
# than walking frame pointers: the explicit dwarf opt-in lowers the
# sampling frequency to keep the observer effect within budget.
DWARF_FREQUENCY = 97


def _now() -> str:
    """Local timestamp with timezone, second precision."""
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def _deduplicated(degradations: list) -> list:
    """Identical announcements collapse into one.

    Per-rank ingestion meets the same condition on every rank of one
    microarchitecture; repeating it per rank would drown the log.
    """
    seen = {}
    for degradation in degradations:
        seen.setdefault((degradation.name, degradation.message), degradation)
    return list(seen.values())


def collection_command(
    plan: launch.LaunchPlan,
    collect_dir: Path,
    config: Config,
    preload: str | None = None,
    call_graph: str | None = None,
    frequency: int | None = None,
) -> list[str]:
    """The launch the orchestrator actually runs for an MPI command.

    The rank shim, interposed inside each rank, carries both collection
    layers: every rank counts, the sampling subset records itself, and
    each rank writes into the Run directory - which is the multi-node
    retrieval. `preload` rides along for the application's LD_PRELOAD
    (mpiP); `call_graph` carries the stack mode the ladder settled on
    the orchestrator - decided once, cold, never re-probed on every
    compute node. The launcher itself runs bare.
    """
    shim = [
        sys.executable, "-m", "nunatak.rank",
        "--directory", str(collect_dir),
        "--frequency", str(frequency or config.sampling_frequency),
        "--rank-threshold", str(config.sampling_rank_threshold),
    ]
    if preload is not None:
        shim += ["--preload", preload]
    if call_graph is not None:
        shim += ["--call-graph", call_graph]
    return plan.wrap([*shim, "--"])


def _settle_stacks(args, executor, config, command, sampling, console):
    """The stack mode and frequency this run will sample with, plus the
    degradation when the ladder settles on nothing.

    `--call-graph dwarf` bypasses the ladder: the cost is announced and
    the frequency lowered, that is the whole point of it being explicit.
    Otherwise the ladder is settled cold - lbr from the recorded
    processor, fp from real prologues - exactly as doctor announces it.
    A target binary absent from this machine leaves nothing to probe:
    replayed commands take that path, and live ones cannot, having
    already passed the executable check by launch time.
    """
    frequency = config.sampling_frequency
    if not sampling or executor.system != "Linux":
        return None, frequency, None
    if args.call_graph == "dwarf":
        frequency = min(frequency, DWARF_FREQUENCY)
        console.info(
            "--call-graph dwarf: stack memory copied at every sample; "
            f"frequency lowered to {frequency} Hz"
        )
        return "dwarf", frequency, None
    target = real_target(command) or command[0]
    resolved = shutil.which(target) if os.sep not in target else target
    if resolved is None or not Path(resolved).is_file():
        return None, frequency, None
    decision = stacks.decide(executor, config, str(resolved), executor.cpu_model())
    if decision.mode is not None:
        console.info(f"call stacks: {decision.detail}")
        return decision.mode, frequency, None
    return None, frequency, Degradation(
        name="call-stacks-unavailable",
        message=decision.detail,
        remedy=decision.remedy,
    )


def _pass_plan(args, snapshot, executor, console):
    """What the collection loop runs: labeled passes under --multi-pass,
    one anonymous pass otherwise, None when multi-pass was asked but the
    microarchitecture offers no groups to split.

    The microarchitecture comes from the executor's identification, not
    from the live host: the pass structure decides how many times the
    application runs, and a replay must build the same passes the
    recording ran. Each multi-pass Pass carries the witness on top of
    its group: the replicated counter is what makes the final
    reproducibility check - and any cross-pass fusion - honest.
    """
    if not getattr(args, "multi_pass", False):
        return [(None, counter_events.sampling_events(snapshot))]
    microarchitecture = theory.identify(executor.cpuinfo())
    if microarchitecture is None:
        return None
    groups = counter_events.groups_for(microarchitecture.name)
    if not groups:
        return None
    witness = counter_events.witness_for(microarchitecture.name)
    console.info(
        f"multi-pass: {len(groups)} passes "
        f"({', '.join(label for label, _ in groups)}), "
        "witness replicated in each"
    )
    # The witness may be one of a group's own events (the flops pass
    # already counts FLOPs): asking perf for the same selector twice
    # would burn a counter for nothing.
    return [
        (
            label,
            witness
            + tuple(e for e in events if e.selector not in {w.selector for w in witness}),
        )
        for label, events in groups
    ]


def _pass_consistency(measurements, threshold) -> list[Degradation]:
    """What a multi-pass run must declare before its passes are fused.

    The witness verdict names a non-reproducible application; a module
    whose build-id changed between passes was recompiled mid-run - an
    invalidity, not an uncertainty: its Hotspots keep separate physical
    identities and are presented per Pass, never fused, never placed.
    """
    declared = []
    verdict = analysis.witness_check(measurements, threshold)
    if verdict is not None and not verdict.consistent:
        totals = ", ".join(
            f"pass {index}: {total:.3e}" for index, total in verdict.totals
        )
        declared.append(
            Degradation(
                name="passes-inconsistent",
                message=f"the witness ({verdict.counter}) moved by "
                f"{verdict.spread:.0%} between passes ({totals}), beyond "
                f"the {verdict.threshold:.0%} threshold: the application "
                "is not reproducible and cross-pass fusion is estimated",
                remedy="a convergence criterion, dynamic scheduling or "
                "non-deterministic MPI can cause this; tune "
                "[passes] witness in nunatak.toml if the spread is expected",
            )
        )
    identities: dict[str, dict[str, set]] = {}
    for measurement in measurements:
        hotspot = measurement.hotspot
        if hotspot is None or hotspot.physical_identity is None:
            continue
        module = identities.setdefault(hotspot.logical_identity.module, {})
        module.setdefault(hotspot.physical_identity.module_id, set()).add(
            measurement.pass_index
        )
    for module, ids in sorted(identities.items()):
        if len(ids) > 1:
            declared.append(
                Degradation(
                    name="module-recompiled-between-passes",
                    message=f"{module} changed identity between passes "
                    f"({len(ids)} build-ids): its Hotspots are presented "
                    "per pass, never fused, never placed",
                    remedy="do not rebuild while a multi-pass run is "
                    "measuring; comparing two versions is two Runs",
                )
            )
    return declared


def executable_status(program: str) -> tuple[int, str] | None:
    """None when `program` can launch, else (exit code, message): 127 not
    found, 126 found but not executable."""
    if os.sep in program:
        path = Path(program)
        if not path.exists():
            return COMMAND_NOT_FOUND, f"{program}: no such file or directory"
        if path.is_dir() or not os.access(path, os.X_OK):
            return COMMAND_NOT_EXECUTABLE, f"{program}: not executable"
        return None
    if shutil.which(program) is not None:
        return None
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        if directory and (Path(directory) / program).is_file():
            return COMMAND_NOT_EXECUTABLE, f"{program}: found but not executable"
    return COMMAND_NOT_FOUND, f"{program}: command not found"


def repository_root(executor: Executor, cwd: Path) -> Path | None:
    """The git toplevel containing `cwd`, None outside any repository."""
    toplevel = executor.run(["git", "-C", str(cwd), "rev-parse", "--show-toplevel"])
    if toplevel.exit_code == 0 and toplevel.stdout and toplevel.stdout.strip():
        return Path(toplevel.stdout.strip())
    return None


def project_name(config: Config, command: list[str], root: Path | None) -> str:
    """Naming cascade: `--name` and `nunatak.toml` (already merged into the
    config), else the git repository name, else the base name of the real
    target binary - `solver`, not `mpirun`."""
    if config.project_name:
        name = config.project_name
    elif root is not None:
        name = root.name
    else:
        name = Path(real_target(command) or command[0]).name
    return re.sub(r"[^A-Za-z0-9._-]+", "-", name) or "run"


def source_mapping(config: Config, flags: list[str] | None) -> dict[str, str] | None:
    """Merge the configured source map with the `--source-map OLD=NEW`
    flags, the flags winning; None when a flag is not of that shape."""
    mapping = dict(config.source_map)
    for flag in flags or []:
        prefix, separator, replacement = flag.partition("=")
        if not separator or not prefix:
            return None
        mapping[prefix] = replacement
    return mapping


def run_directory(output: str | None, config: Config, name: str, cwd: Path) -> Path:
    """`-o` names the exact directory; otherwise
    `<runs_dir>/<name>-YYYYMMDD-HHMMSS`, with a `.gitignore` containing `*`
    written next to the Runs so the user's `git status` stays clean."""
    if output:
        return Path(output)
    runs_dir = Path(config.runs_dir)
    if not runs_dir.is_absolute():
        runs_dir = cwd / runs_dir
    runs_dir.mkdir(parents=True, exist_ok=True)
    gitignore = runs_dir / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("*\n")
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    directory = runs_dir / f"{name}-{stamp}"
    suffix = 2
    while directory.exists():
        directory = runs_dir / f"{name}-{stamp}-{suffix}"
        suffix += 1
    return directory


def execute(args, command: list[str], console: Console) -> int:
    """Measure `command`, write the Run, and return the exit code to
    propagate - the application's own in the general case."""
    if not command:
        console.error("run requires a command: nunatak run [options] -- <command>")
        return FAILURE_BEFORE_LAUNCH

    cwd = Path.cwd()
    config, effective = load(cwd, name=args.name)
    mapping = source_mapping(config, args.source_map)
    if mapping is None:
        console.error("--source-map expects OLD=NEW")
        return FAILURE_BEFORE_LAUNCH
    replaying = args.replay is not None
    if replaying:
        executor: Executor = corpus.ReplayExecutor(Path(args.replay))
    elif args.record:
        executor = corpus.RecordingExecutor(SubprocessExecutor(), Path(args.record))
    else:
        executor = SubprocessExecutor()

    adapter, version = cpu_collector(executor, config)
    symbolizer = attribution.locate_any(executor, config)
    checks = doctor.light_checks(
        executor, config, command, cpu=(adapter, version), llvm=(symbolizer,)
    )
    degradations = doctor.degradations(checks)
    for degradation in degradations:
        console.degradation(degradation)
    if args.strict and degradations:
        console.error(
            f"--strict: {len(degradations)} degradation(s) turned into an error"
        )
        return STRICT_VIOLATION

    if not replaying:
        # A replayed command does not exist here; its recorded exit code
        # is the truth.
        status = executable_status(command[0])
        if status is not None:
            code, message = status
            console.error(message)
            return code

    root = repository_root(executor, cwd)
    name = project_name(config, command, root)
    directory = run_directory(args.output, config, name, cwd)

    # The first Run on an unknown Machine calibrates it before the
    # application launches - the only moment the node is truly ours. A
    # cached profile short-circuits the measurement; --no-calibrate skips
    # it at the price of theoretical Ceilings.
    snapshot = machine.snapshot(executor)
    cached = machine.load(snapshot)
    if cached is not None:
        snapshot = dataclasses.replace(snapshot, ceilings=cached.ceilings)
    elif adapter is not None and not args.no_calibrate:
        console.info(
            f"calibrating Machine {machine.identity(snapshot)} "
            "(first Run; --no-calibrate to skip)"
        )
        snapshot, _ = calibrate.calibrated_machine(executor, config, snapshot)
    else:
        snapshot = dataclasses.replace(
            snapshot, ceilings=theory.theoretical_ceilings(snapshot)
        )

    started = _now()
    collectors: tuple[Collector, ...] = ()
    pass_records: list[Pass] = []
    loop_analyses = []
    measurements = []
    stacks_collected = []
    address_details = []
    source_extracts = []
    plan = launch.split(command)
    gathered = []
    mpi_stack = None
    measured = True
    call_graph, frequency, ladder_degradation = _settle_stacks(
        args, executor, config, command,
        sampling=(plan.mpi and bool(plan.application)) or adapter is not None,
        console=console,
    )
    if ladder_degradation is not None:
        console.degradation(ladder_degradation)
        degradations = degradations + [ladder_degradation]
    if plan.mpi and plan.application:
        # Both collection layers live inside the ranks: an outer record
        # would fight the ranks' events for the same physical counters
        # and corrupt them (measured on Zen 2, not feared). The launcher
        # runs bare here; each rank samples or counts itself and writes
        # home, and ingestion below reads what came back.
        if args.multi_pass:
            fallback = Degradation(
                name="multi-pass-unavailable",
                message="multi-pass does not cover MPI runs yet; "
                "sampling a single pass",
                remedy="run the per-rank binary under --multi-pass directly",
            )
            console.degradation(fallback)
            degradations = degradations + [fallback]
        console.info(
            "launching ranks (each one counting; sampling narrows to rank 0 "
            f"plus one rank per node beyond {config.sampling_rank_threshold} "
            f"ranks): {' '.join(command)}"
        )
        mpi_stack = probe.stack(executor, config)
        mpip_library = mpip.locate(config, mpi_stack=mpi_stack)
        if not args.no_calibrate:
            # The probe launches through the allocation's own launcher,
            # before the application - the only moment the network is
            # ours - and its rates become the Machine's network Ceilings.
            console.info("probing the network inside this allocation")
            network, network_degradations = probe.network_ceilings(
                executor, plan, mpi_stack
            )
            if network:
                snapshot = dataclasses.replace(
                    snapshot, ceilings=snapshot.ceilings + network
                )
            gathered += network_degradations
        exit_code = executor.run(
            collection_command(
                plan, directory / COLLECT_DIR, config, preload=mpip_library,
                call_graph=call_graph, frequency=frequency,
            ),
            capture=False,
        ).exit_code
        versions = set()
        for rank_dir, meta in rank_counting.rank_metas(directory / COLLECT_DIR):
            if meta.get("perf"):
                versions.add(meta["perf"])
            if not meta.get("sampled"):
                continue
            sampled, sampled_stacks, sampled_degradations = ingestion.ingest(
                "perf", meta["perf"], rank_dir, node=meta["node"], rank=meta["rank"]
            )
            measurements += sampled
            stacks_collected += sampled_stacks
            gathered += sampled_degradations
        collectors = tuple(
            Collector(tool="perf", version=v) for v in sorted(versions)
        )
        mpi_measurements, mpi_degradations, mpip_version = mpip_report.ingest_mpip(
            directory / COLLECT_DIR, expected=mpip_library is not None
        )
        measurements += mpi_measurements
        gathered += mpi_degradations
        if mpip_version is not None:
            collectors += (Collector(tool="mpiP", version=mpip_version),)
    elif adapter is not None:
        collectors = (Collector(tool=adapter.tool, version=version),)
        passes = _pass_plan(args, snapshot, executor, console)
        if passes is None:
            gathered.append(
                Degradation(
                    name="multi-pass-unavailable",
                    message="no counter groups for this microarchitecture: "
                    "there is nothing to split into passes",
                    remedy="a single time-only pass is being sampled instead",
                )
            )
            passes = [(None, counter_events.sampling_events(snapshot))]
        exit_code = 0
        for index, (label, events) in enumerate(passes):
            named = f" [pass {index}: {label}]" if label is not None else ""
            console.info(
                f"collecting with {adapter.tool} {version}{named}: "
                f"{' '.join(command)}"
            )
            pass_dir = (
                directory / COLLECT_DIR / f"pass-{index}"
                if label is not None
                else directory / COLLECT_DIR
            )
            pass_start = _now()
            pass_exit, collect_degradations = adapter.collect(
                list(command),
                pass_dir,
                executor,
                frequency,
                events=events,
                call_graph=call_graph,
            )
            sampled, sampled_stacks, ingest_degradations = ingestion.ingest(
                adapter.tool, version, pass_dir,
                node=platform.node(), pass_index=index,
            )
            measurements += sampled
            stacks_collected += sampled_stacks
            gathered += collect_degradations + ingest_degradations
            pass_records.append(
                Pass(
                    index=index,
                    exit_code=pass_exit,
                    collectors=collectors,
                    start=pass_start,
                    end=_now(),
                )
            )
            if index == 0:
                exit_code = pass_exit
            if pass_exit != 0 and index + 1 < len(passes):
                # Relaunching an application that just failed spends the
                # user's allocation on reproducing a failure: the first
                # pass's measurements are kept, the rest is declared.
                gathered.append(
                    Degradation(
                        name="passes-skipped",
                        message=f"the application exited with {pass_exit} on "
                        f"pass {index}; the remaining "
                        f"{len(passes) - index - 1} pass(es) were skipped",
                        remedy="fix the failure, or run without --multi-pass",
                    )
                )
                break
    else:
        measured = False
        console.info(f"launching: {' '.join(command)}")
        exit_code = executor.run(command, capture=False).exit_code

    if measured:
        gathered += _pass_consistency(
            measurements, config.passes_witness_threshold
        )
        measurements, address_details, stacks_collected, attribution_degradations = (
            attribution.attribute(
                measurements, symbolizer, executor,
                environment=debuginfod.environment(config),
                stacks=stacks_collected,
            )
        )
        if not args.no_source:
            # The fallback symbolizer reads no line-table fingerprints:
            # nothing is present, so nothing can be discordant, and the
            # extracts are accepted exactly as gcc's unfingerprinted ones
            # already are.
            checksums = (
                staleness.checksums_for(
                    executor, symbolizer.dwarfdump, address_details
                )
                if symbolizer is not None and symbolizer.dwarfdump is not None
                else {}
            )
            source_extracts = source.extract(
                address_details, mapping, root or cwd, checksums
            )
        loop_analyses, loop_degradations = loop_analysis.analyze(
            executor, config, address_details,
            floor_samples=analysis.STATISTICAL_FLOOR_SAMPLES,
        )
        gathered += loop_degradations
        counting, counting_degradations = rank_counting.ingest_counting(
            directory / COLLECT_DIR
        )
        measurements = measurements + counting
        after_launch = _deduplicated(
            gathered + attribution_degradations + counting_degradations
        )
        for degradation in after_launch:
            console.degradation(degradation)
        degradations = degradations + after_launch
    ended = _now()

    if args.record:
        corpus.write_meta(
            Path(args.record),
            list(command),
            [{"tool": c.tool, "version": c.version} for c in collectors],
            sampling_blocked=executor.sampling_blocked(),
            cpu_model=executor.cpu_model(),
            cpuinfo=executor.cpuinfo(),
        )

    collected_provenance = provenance.collect(executor, cwd, effective)
    if plan.mpi and plan.application and mpi_stack is not None:
        # A network analysis whose underlying stack is unknown is not
        # interpretable: the stack travels with the Run.
        collected_provenance.dependencies["mpi"] = mpi_stack.label
        collected_provenance.dependencies["mpicc"] = mpi_stack.mpicc
    run = Run(
        name=directory.name,
        created=started,
        command=list(command),
        exit_code=exit_code,
        machine=snapshot,
        provenance=collected_provenance,
        passes=pass_records
        or [
            Pass(
                index=0,
                exit_code=exit_code,
                collectors=collectors,
                start=started,
                end=ended,
            )
        ],
        degradations=list(degradations),
        measurements=measurements,
        address_details=address_details,
        source_extracts=source_extracts,
        stacks=stacks_collected,
        loop_analyses=loop_analyses,
    )
    write_run(directory, run)

    hotspots = {m.hotspot for m in hotspot_level(measurements)}
    resolved = sum(
        1 for h in hotspots if h.resolution_level is not ResolutionLevel.UNRESOLVED
    )
    report_path = None
    if measurements:
        console.info(
            f"{len(measurements)} measurements across {len(hotspots)} hotspots "
            f"({resolved} resolved)"
        )
        diagnostics = analysis.diagnose(run)
        # A missing compiled app was already announced by the light
        # doctor as `report-unavailable`: the run silently keeps going.
        if html.assets_available():
            report_path = html.write_report(directory, run, diagnostics)
        # The three closing moments of the log: the summary, then the
        # degradations again - the announcements scrolled past long ago
        # in a job log - then the paths.
        for line in summary.summarize(run, diagnostics):
            console.info(line)
        for degradation in degradations:
            console.degradation(degradation)

    if args.json:
        print(
            json.dumps(
                {
                    "run": str(directory),
                    "name": run.name,
                    "exit_code": exit_code,
                    "measurements": len(run.measurements),
                    "hotspots": len(hotspots),
                    "resolved_hotspots": resolved,
                    "report": str(report_path) if report_path else None,
                    "degradations": [
                        {"name": d.name, "message": d.message, "remedy": d.remedy}
                        for d in degradations
                    ],
                }
            )
        )
    console.info(f"Run: {directory}")
    if report_path is not None:
        console.info(f"Report: {report_path}")

    if args.strict and degradations:
        # Degradations met after launch (ingestion): the Run is written and
        # the JSON summary carries the application's exit code, but a strict
        # invocation still fails.
        console.error(
            f"--strict: {len(degradations)} degradation(s) turned into an error"
        )
        return STRICT_VIOLATION
    return exit_code
