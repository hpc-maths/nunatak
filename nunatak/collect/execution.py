"""The execution boundary for external processes: exec + parse, never link.

Everything nunatak consumes from collectors crosses this boundary, which is
why adapters are substitutable by a source of recordings: the corpus
wraps or replaces the executor, never the adapters.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass

from nunatak.exit_codes import COMMAND_NOT_EXECUTABLE, COMMAND_NOT_FOUND


@dataclass(frozen=True)
class Invocation:
    """The observable outcome of one external process."""

    argv: tuple[str, ...]
    exit_code: int
    stdout: str | None = None
    stderr: str | None = None


class Executor:
    """Interface: run an external process and report what happened.

    `capture=False` leaves stdout/stderr connected to the caller's - the
    profiled application's output is never swallowed.
    """

    def run(
        self,
        argv: list[str],
        capture: bool = True,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
    ) -> Invocation:
        """Run `argv` and report what happened.

        `capture=True` collects stdout/stderr; False leaves them attached
        to the caller's streams.
        """
        raise NotImplementedError


class SubprocessExecutor(Executor):
    """The real thing. A missing or non-executable program is reported with
    the reserved exit codes rather than an exception: an absent tool is an
    expected situation, not an error of nunatak."""

    def run(self, argv, capture=True, env=None, cwd=None):
        """Execute `argv` as a subprocess."""
        try:
            completed = subprocess.run(
                argv,
                capture_output=capture,
                text=True,
                errors="replace",
                env=env,
                cwd=cwd,
            )
        except FileNotFoundError:
            return Invocation(
                argv=tuple(argv),
                exit_code=COMMAND_NOT_FOUND,
                stderr=f"{argv[0]}: command not found",
            )
        except (PermissionError, OSError) as error:
            return Invocation(
                argv=tuple(argv),
                exit_code=COMMAND_NOT_EXECUTABLE,
                stderr=f"{argv[0]}: {error}",
            )
        return Invocation(
            argv=tuple(argv),
            exit_code=completed.returncode,
            stdout=completed.stdout if capture else None,
            stderr=completed.stderr if capture else None,
        )
