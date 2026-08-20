"""The execution boundary for external processes: exec + parse, never link.

Everything nunatak consumes from collectors crosses this boundary, which is
why adapters are substitutable by a source of recordings: the corpus
wraps or replaces the executor, never the adapters.
"""

from __future__ import annotations

import os
import platform
import subprocess
from dataclasses import dataclass
from pathlib import Path

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

    @property
    def system(self) -> str:
        """The platform tools run on; a replay reports the recorded one."""
        return platform.system()

    def sampling_blocked(self) -> str | None:
        """Why event sampling cannot work in this environment, or None.

        Every executor answers for its own environment: the real one
        reads the kernel setting, a recording keeps its inner verdict,
        and a replay reports the verdict the recording preserved."""
        return None

    def cpu_model(self) -> str | None:
        """Marketing name of the CPU the tools run on, None when unknown.

        An executor verdict, like `sampling_blocked`: decisions keyed on
        the processor - the call-stack ladder's lbr rung - must replay
        identically on every machine, so the value crosses the execution
        boundary instead of being read live at decision time.
        """
        return None

    def cpuinfo(self) -> str | None:
        """The processor identification block, None when unknown.

        One /proc/cpuinfo record - the fields repeat per logical CPU -
        crossing the boundary for the same reason as `cpu_model`: the
        structure of a multi-pass run is keyed on the microarchitecture,
        and a replay must build the same passes the recording ran.
        """
        return None

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

    def sampling_blocked(self):
        """Report the kernel setting that denies sampling, if any.

        Ubuntu ships kernel.perf_event_paranoid=4: perf_event_open is
        denied to unprivileged users even on their own processes.
        """
        if platform.system() != "Linux" or os.geteuid() == 0:
            return None
        try:
            level = int(
                Path("/proc/sys/kernel/perf_event_paranoid").read_text().strip()
            )
        except (OSError, ValueError):
            return None
        if level >= 3:
            return f"kernel.perf_event_paranoid={level} forbids unprivileged profiling"
        return None

    def cpuinfo(self):
        """Read the first /proc/cpuinfo record, None off Linux."""
        try:
            text = Path("/proc/cpuinfo").read_text()
        except OSError:
            return None
        return text.split("\n\n", 1)[0]

    def cpu_model(self):
        """Read the CPU's marketing name, best-effort per platform."""
        if platform.system() == "Darwin":
            invocation = self.run(["sysctl", "-n", "machdep.cpu.brand_string"])
            if invocation.exit_code == 0 and invocation.stdout:
                return invocation.stdout.strip()
            return None
        cpuinfo = Path("/proc/cpuinfo")
        try:
            for line in cpuinfo.read_text().splitlines():
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
        except OSError:
            return None
        return None

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
