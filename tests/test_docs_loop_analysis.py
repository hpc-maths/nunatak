"""The Static loop analysis page quotes two real loops and one reason.

The table's numbers were read from Runs of the shipped examples on the
corpus machine, so they cannot be recomputed here. What is held is the
shape of the claim: the invariant that nothing derived from a static
count is `measured`, the scheduling-model name the page shows, and the
sentence an installation without llvm-mca produces.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

from nunatak.attribution import loops
from nunatak.pivot import LoopAnalysis

ROOT = Path(__file__).resolve().parents[1]
PAGE = (ROOT / "docs" / "guide" / "static-loop-analysis.md").read_text()


def flowed(text):
    """The page's prose with its line wrapping removed."""
    return " ".join(text.split())


def test_the_quoted_model_name_is_one_llvm_is_asked_for():
    """The table names the model its bounds were computed against."""
    assert "znver2" in loops._MCPU.values()
    assert "`znver2`" in PAGE


def test_the_quoted_upgrade_reason_is_the_written_one():
    source = inspect.getsource(loops)
    assert "install LLVM 19 or newer" in source
    assert "install LLVM 19 or newer" in PAGE


def test_absent_bounds_always_carry_a_reason():
    """The page states this as a rule; the model enforces it."""
    try:
        LoopAnalysis(
            hotspot=None,
            start_offset=0,
            end_offset=8,
            instructions=1,
            flops_per_iteration=0.0,
            vector_fp=0,
            scalar_fp=0,
            vector_width_bits=None,
            loaded_bytes=0,
            stored_bytes=0,
            gathers=0,
        )
    except ValueError as error:
        assert "reason" in str(error)
    else:
        raise AssertionError("absent cycle bounds were accepted without a reason")
    assert "`unavailable`" in PAGE


def test_the_degradation_the_page_names_is_the_only_one_declared():
    """Everything else the analysis cannot do is an absent fact with a
    reason, never a declaration - which is what the page claims."""
    declared = set(re.findall(r'name="([a-z-]+)"', inspect.getsource(loops)))
    assert declared == {"loop-analysis-unavailable"}
    assert declared.pop() in PAGE


def test_the_page_is_reachable_and_replaces_the_old_section():
    guide = (ROOT / "docs" / "guide" / "index.md").read_text()
    assert "static-loop-analysis" in guide
    old = (ROOT / "docs" / "guide" / "getting-started.md").read_text()
    assert "## Static loop analysis" not in old
