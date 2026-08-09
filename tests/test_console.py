"""Output-medium detection: timestamped plain lines outside a terminal."""

import io
import re

from nunatak.console import Console
from nunatak.pivot import Degradation


def test_outside_a_terminal_lines_are_timestamped_and_colorless():
    stream = io.StringIO()
    console = Console(stream=stream)
    console.warning("counters multiplexed")
    line = stream.getvalue()
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", line)
    assert "\033[" not in line
    assert "warning: counters multiplexed" in line


def test_a_degradation_is_announced_with_name_and_remedy():
    stream = io.StringIO()
    Console(stream=stream).degradation(
        Degradation(
            name="cpu-collection-unavailable",
            message="perf not usable",
            remedy="install linux-tools",
        )
    )
    line = stream.getvalue()
    assert "[cpu-collection-unavailable]" in line
    assert "install linux-tools" in line
