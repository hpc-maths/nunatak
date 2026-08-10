"""Command-line interface.

The surface has six verbs - run, doctor, explain, report, compare and
calibrate; `run` and `doctor` exist today, the others arrive with their
features. Usage errors exit with 125,
the code reserved for a nunatak failure before launch.
"""

from __future__ import annotations

import argparse
import sys

import nunatak
from nunatak.console import Console
from nunatak.exit_codes import FAILURE_BEFORE_LAUNCH


class _Parser(argparse.ArgumentParser):
    """Parser whose usage errors exit with 125 instead of argparse's 2."""

    def error(self, message):
        """Exit with the reserved code instead of argparse's default 2."""
        self.print_usage(sys.stderr)
        self.exit(FAILURE_BEFORE_LAUNCH, f"{self.prog}: error: {message}\n")


def build_parser() -> argparse.ArgumentParser:
    """Declare the verbs and flags of the command line."""
    parser = _Parser(
        prog="nunatak",
        description="Zero-instrumentation profiler for high-performance computing.",
    )
    parser.add_argument(
        "--version", action="version", version=f"nunatak {nunatak.__version__}"
    )
    verbs = parser.add_subparsers(dest="verb", required=True, parser_class=_Parser)

    run = verbs.add_parser(
        "run",
        usage="nunatak run [options] -- <command>",
        help="measure the command, then analyze and report",
    )
    run.add_argument("--name", help="force the project name used to name the Run")
    run.add_argument("-o", "--output", help="exact directory of the Run")
    run.add_argument(
        "--strict",
        action="store_true",
        help="turn every named degradation into an error (exit code 121)",
    )
    run.add_argument("--json", action="store_true", help="machine-readable summary on stdout")
    # Corpus surface, for test campaigns on real hardware: record every
    # invocation crossing the execution boundary, or replay a recorded entry
    # instead of running the tools.
    run.add_argument("--record", metavar="ENTRY", help=argparse.SUPPRESS)
    run.add_argument("--replay", metavar="ENTRY", help=argparse.SUPPRESS)

    doctor = verbs.add_parser(
        "doctor",
        usage="nunatak doctor [options] [-- <command>]",
        help="diagnose the environment, and the target binary when given",
    )
    doctor.add_argument("--json", action="store_true", help="machine-readable report on stdout")

    return parser


def principal(argv: list[str] | None = None) -> int:
    """Entry point. Returns the exit code; the application's own code is
    propagated by `run` (nunatak observes, it never masks)."""
    raw = list(sys.argv[1:]) if argv is None else list(argv)
    command: list[str] = []
    if "--" in raw:
        separator = raw.index("--")
        command = raw[separator + 1 :]
        raw = raw[:separator]

    try:
        args = build_parser().parse_args(raw)
    except SystemExit as exit_:
        return int(exit_.code or 0)

    console = Console()
    if args.verb == "run":
        from nunatak.cli import run

        return run.execute(args, command, console)
    from nunatak.cli import doctor

    return doctor.execute(args, command, console)
