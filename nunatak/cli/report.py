"""report: regenerate the report of a Run from its pivot.

Regenerating is a real operation, not a doublon of `run`: the Diagnostic
is never persisted, so the report is recomputed - after an upgrade, or
on a machine that only received the Run directory. Without an argument,
the most recent Run of `runs_dir` is taken: "most recent" reads on the
directory names, there is no index to repair.
"""

from __future__ import annotations

import json
from pathlib import Path

from nunatak import analysis
from nunatak.config import load
from nunatak.console import Console
from nunatak.exit_codes import FAILURE_BEFORE_LAUNCH
from nunatak.pivot import MANIFEST, read_run
from nunatak.report import html


def most_recent_run(runs_dir: Path) -> Path | None:
    """The latest Run directory under `runs_dir`, by name - the names
    carry their timestamp - or None when there is none."""
    if not runs_dir.is_dir():
        return None
    candidates = sorted(
        (child for child in runs_dir.iterdir() if (child / MANIFEST).is_file()),
        key=lambda child: child.name,
    )
    return candidates[-1] if candidates else None


def execute(args, console: Console) -> int:
    """`nunatak report [<run>] [--json]`. Returns 0 on a written report,
    125 when there is no Run or no compiled app to render it with."""
    cwd = Path.cwd()
    config, _ = load(cwd)
    if args.run:
        directory = Path(args.run)
    else:
        runs_dir = Path(config.runs_dir)
        if not runs_dir.is_absolute():
            runs_dir = cwd / runs_dir
        found = most_recent_run(runs_dir)
        if found is None:
            console.error(f"no Run under {runs_dir}; run `nunatak run` first")
            return FAILURE_BEFORE_LAUNCH
        directory = found

    try:
        run = read_run(directory)
    except (ValueError, OSError) as error:
        console.error(str(error))
        return FAILURE_BEFORE_LAUNCH

    if not html.assets_available():
        console.error(
            "the compiled report app is missing from this installation - "
            "reinstall nunatak from a built wheel; on a development checkout, "
            "run `npm install && npm run build` in report-app/"
        )
        return FAILURE_BEFORE_LAUNCH

    path = html.write_report(directory, run, analysis.diagnose(run))
    if args.json:
        print(json.dumps({"run": str(directory), "report": str(path)}))
    console.info(f"Report: {path}")
    return 0
