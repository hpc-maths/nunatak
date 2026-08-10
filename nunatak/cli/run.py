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
from pathlib import Path

from nunatak import attribution, corpus, ingestion, machine, provenance
from nunatak.attribution import source, staleness
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
from nunatak.pivot import Collector, Pass, ResolutionLevel, Run, write_run
from nunatak.target import real_target

COLLECT_DIR = "collect"


def _now() -> str:
    """Local timestamp with timezone, second precision."""
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


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
    symbolizer = attribution.locate(executor, config)
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
    measurements = []
    address_details = []
    source_extracts = []
    if adapter is not None:
        console.info(f"collecting with {adapter.tool} {version}: {' '.join(command)}")
        exit_code = adapter.collect(
            command, directory / COLLECT_DIR, executor, config.sampling_frequency
        )
        collectors = (Collector(tool=adapter.tool, version=version),)
        measurements, ingest_degradations = ingestion.ingest(
            adapter.tool, version, directory / COLLECT_DIR, node=platform.node()
        )
        measurements, address_details, attribution_degradations = attribution.attribute(
            measurements, symbolizer, executor
        )
        if not args.no_source:
            checksums = (
                staleness.checksums_for(
                    executor,
                    staleness.dwarfdump_path(symbolizer.path),
                    address_details,
                )
                if symbolizer is not None
                else {}
            )
            source_extracts = source.extract(
                address_details, mapping, root or cwd, checksums
            )
        for degradation in ingest_degradations + attribution_degradations:
            console.degradation(degradation)
        degradations = degradations + ingest_degradations + attribution_degradations
    else:
        console.info(f"launching: {' '.join(command)}")
        exit_code = executor.run(command, capture=False).exit_code
    ended = _now()

    if args.record:
        corpus.write_meta(
            Path(args.record),
            list(command),
            [{"tool": c.tool, "version": c.version} for c in collectors],
        )

    run = Run(
        name=directory.name,
        created=started,
        command=list(command),
        exit_code=exit_code,
        machine=snapshot,
        provenance=provenance.collect(executor, cwd, effective),
        passes=[
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
    )
    write_run(directory, run)

    hotspots = {m.hotspot for m in measurements}
    resolved = sum(
        1 for h in hotspots if h.resolution_level is not ResolutionLevel.UNRESOLVED
    )
    if measurements:
        console.info(
            f"{len(measurements)} measurements across {len(hotspots)} hotspots "
            f"({resolved} resolved)"
        )

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
                    "degradations": [
                        {"name": d.name, "message": d.message, "remedy": d.remedy}
                        for d in degradations
                    ],
                }
            )
        )
    console.info(f"Run: {directory}")

    if args.strict and degradations:
        # Degradations met after launch (ingestion): the Run is written and
        # the JSON summary carries the application's exit code, but a strict
        # invocation still fails.
        console.error(
            f"--strict: {len(degradations)} degradation(s) turned into an error"
        )
        return STRICT_VIOLATION
    return exit_code
