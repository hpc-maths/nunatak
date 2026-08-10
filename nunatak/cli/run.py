"""run: measure the application, write the Run, propagate its exit code.

Order of operations: the light doctor announces degradations before any
compute time is spent; `--strict` stops there with code 121; the command is
checked (127/126) before the Run directory is created; the application then
executes with its output untouched, and the pivot is written whatever its
exit code - a failing application still deserves its measurements.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import shutil
from pathlib import Path

from nunatak import machine, provenance
from nunatak.cli import doctor
from nunatak.collect.execution import Executor, SubprocessExecutor
from nunatak.config import Config, load
from nunatak.console import Console
from nunatak.exit_codes import (
    COMMAND_NOT_EXECUTABLE,
    COMMAND_NOT_FOUND,
    FAILURE_BEFORE_LAUNCH,
    STRICT_VIOLATION,
)
from nunatak.pivot import Pass, Run, write_run
from nunatak.target import real_target


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


def project_name(
    executor: Executor, config: Config, command: list[str], cwd: Path
) -> str:
    """Naming cascade: `--name` and `nunatak.toml` (already merged into the
    config), else the git repository name, else the base name of the real
    target binary - `solver`, not `mpirun`."""
    if config.project_name:
        name = config.project_name
    else:
        toplevel = executor.run(["git", "-C", str(cwd), "rev-parse", "--show-toplevel"])
        if toplevel.exit_code == 0 and toplevel.stdout and toplevel.stdout.strip():
            name = Path(toplevel.stdout.strip()).name
        else:
            name = Path(real_target(command) or command[0]).name
    return re.sub(r"[^A-Za-z0-9._-]+", "-", name) or "run"


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
    executor = SubprocessExecutor()

    checks = doctor.light_checks(executor, config, command)
    degradations = doctor.degradations(checks)
    for degradation in degradations:
        console.degradation(degradation)
    if args.strict and degradations:
        console.error(
            f"--strict: {len(degradations)} degradation(s) turned into an error"
        )
        return STRICT_VIOLATION

    status = executable_status(command[0])
    if status is not None:
        code, message = status
        console.error(message)
        return code

    name = project_name(executor, config, command, cwd)
    directory = run_directory(args.output, config, name, cwd)

    started = _now()
    console.info(f"launching: {' '.join(command)}")
    invocation = executor.run(command, capture=False)
    ended = _now()
    exit_code = invocation.exit_code

    run = Run(
        name=directory.name,
        created=started,
        command=list(command),
        exit_code=exit_code,
        machine=machine.snapshot(executor),
        provenance=provenance.collect(executor, cwd, effective),
        passes=[Pass(index=0, exit_code=exit_code, start=started, end=ended)],
        degradations=list(degradations),
    )
    write_run(directory, run)

    if args.json:
        print(
            json.dumps(
                {
                    "run": str(directory),
                    "name": run.name,
                    "exit_code": exit_code,
                    "measurements": len(run.measurements),
                    "degradations": [
                        {"name": d.name, "message": d.message, "remedy": d.remedy}
                        for d in degradations
                    ],
                }
            )
        )
    console.info(f"Run: {directory}")
    return exit_code
