"""debuginfod controls: used if configured, never required, never slow.

Both symbolization paths consult debuginfod on their own when
`DEBUGINFOD_URLS` is in their environment - llvm-symbolizer and GNU
addr2line alike link the client library on the distributions that
matter. Its gain is real but narrow: sources and debug information for
`libc`, `libmpi` and the distribution's libraries, never for the user's
own code. What nunatak adds is control, not the client: the lookup runs
only at analysis time by construction (symbolization happens after the
application exited), it can be disabled, and the client's 90-second
default timeout is shortened so an unreachable server degrades the names
of distribution libraries instead of hanging the analysis.

Nothing here changes a tool's command line: the control rides the
environment, so a recorded corpus entry replays identically whatever the
replaying machine's debuginfod situation.
"""

from __future__ import annotations

import os
from typing import Mapping

from nunatak.config import Config

URLS = "DEBUGINFOD_URLS"
TIMEOUT = "DEBUGINFOD_TIMEOUT"


def environment(
    config: Config, base: Mapping[str, str] | None = None
) -> dict[str, str] | None:
    """The environment symbolizer invocations run under, None to inherit.

    Without `DEBUGINFOD_URLS` there is nothing to control. With it,
    a disabled configuration strips the variable - the client never
    fires - and an enabled one bounds the wait: the configured timeout
    is written unless the user already set their own, an explicit
    environment being an explicit choice.
    """
    if base is None:
        base = os.environ
    if not base.get(URLS):
        return None
    composed = dict(base)
    if not config.debuginfod_enabled:
        del composed[URLS]
        return composed
    composed.setdefault(TIMEOUT, str(config.debuginfod_timeout))
    return composed


def status(config: Config, base: Mapping[str, str] | None = None) -> str | None:
    """One doctor-ready sentence about this environment's debuginfod,
    None when no server is configured - absence is the normal case,
    not a finding."""
    if base is None:
        base = os.environ
    urls = [url for url in base.get(URLS, "").replace(",", " ").split() if url]
    if not urls:
        return None
    if not config.debuginfod_enabled:
        return f"{len(urls)} server(s) configured, disabled by nunatak.toml"
    timeout = base.get(TIMEOUT, str(config.debuginfod_timeout))
    return (
        f"{len(urls)} server(s), timeout {timeout}s: distribution-library "
        "debug info may be fetched at analysis time"
    )
