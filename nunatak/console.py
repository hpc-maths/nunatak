"""Terminal output - a first-class output that detects its medium.

On a cluster, the output of `run` lands in a job log file, not in a
terminal: no color, no line rewriting, no progress bar there, but
timestamped lines that stay readable in a `tail -f` as well as in a file
reread three weeks later.
"""

from __future__ import annotations

import datetime
import os
import sys

from nunatak.pivot import Degradation

_RESET = "\033[0m"
_YELLOW = "\033[33m"
_RED = "\033[31m"
_DIM = "\033[2m"


class Console:
    """nunatak's own messages, written to stderr.

    stderr keeps stdout clean: the profiled application's output and the
    `--json` summaries are the only things nunatak writes on stdout.
    """

    def __init__(self, stream=None):
        self.stream = stream if stream is not None else sys.stderr
        isatty = getattr(self.stream, "isatty", lambda: False)
        self.is_terminal = isatty() and os.environ.get("TERM", "") != "dumb"
        self.use_color = self.is_terminal and "NO_COLOR" not in os.environ

    def _write(self, message: str, color: str = "") -> None:
        """Emit one line: colored on a terminal, timestamped outside one."""
        if self.is_terminal:
            if color and self.use_color:
                message = f"{color}{message}{_RESET}"
        else:
            stamp = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
            message = f"{stamp} {message}"
        print(message, file=self.stream)

    def info(self, message: str) -> None:
        """Neutral progress line."""
        self._write(message)

    def warning(self, message: str) -> None:
        """Something worth knowing that does not stop the run."""
        self._write(f"warning: {message}", _YELLOW)

    def error(self, message: str) -> None:
        """A failure, red on a terminal."""
        self._write(f"error: {message}", _RED)

    def degradation(self, degradation: Degradation) -> None:
        """Announce a named degradation before the run, with the way forward."""
        message = f"degraded [{degradation.name}]: {degradation.message}"
        if degradation.remedy:
            message += f" - {degradation.remedy}"
        self._write(message, _YELLOW)
