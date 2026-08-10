"""Shared test doubles."""

import collections
import os

from nunatak.collect.execution import Executor, Invocation


class ScriptedExecutor(Executor):
    """Deterministic stand-in for the subprocess executor."""

    def __init__(self, system="Linux", blocked=None):
        self._system = system
        self._blocked = blocked
        self.calls = []
        self._responses = collections.defaultdict(collections.deque)

    @property
    def system(self):
        return self._system

    def sampling_blocked(self):
        return self._blocked

    def on(self, program, stdout="", stderr="", exit_code=0):
        """Queue a canned response for the next invocation of `program`."""
        self._responses[program].append((exit_code, stdout, stderr))
        return self

    def run(self, argv, capture=True, env=None, cwd=None):
        """Record the call and serve the next canned response."""
        self.calls.append(list(argv))
        queue = self._responses.get(os.path.basename(argv[0]))
        exit_code, stdout, stderr = queue.popleft() if queue else (0, "", "")
        return Invocation(
            argv=tuple(argv),
            exit_code=exit_code,
            stdout=stdout if capture else None,
            stderr=stderr if capture else None,
        )
