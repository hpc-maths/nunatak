"""The Source subject quotes the sentences a report shows in place of
code. Each one comes from `attribution.source` or `staleness`, and a
reader who searches the sentence they see has to land on the page that
explains it.
"""

from __future__ import annotations

import re
from pathlib import Path

from nunatak.attribution import source
from tests.test_source import detail, frame, hotspot

ROOT = Path(__file__).resolve().parents[1]
SUBJECT = ROOT / "docs" / "guide" / "source"
HOW_TO = (SUBJECT / "get-the-source-into-your-run.md").read_text()
EXPLANATION = (SUBJECT / "what-the-run-keeps-of-your-code.md").read_text()


def _detail(file: str, line: int = 12):
    """One sampled address of `sweep`, declared two lines above `line`."""
    return detail(
        hotspot(name="sweep", file=file),
        (frame(function="sweep", file=file, line=line, declaration_line=line - 2),),
    )


def _reason(details, source_map=None, root=None, checksums=None):
    extracts = source.extract(
        details, source_map or {}, Path(root or "/nonexistent"), checksums
    )
    assert len(extracts) == 1
    return extracts[0]


def test_the_documented_not_found_reason_is_the_real_one(tmp_path):
    extract = _reason([_detail("/build/solver/kernels.c")], root=tmp_path)
    assert extract.reason in HOW_TO, extract.reason


def test_the_documented_stale_reason_is_the_real_one(tmp_path):
    file = tmp_path / "kernels.c"
    file.write_text("\n".join(f"line {n}" for n in range(1, 40)) + "\n")
    extract = _reason(
        [_detail(str(file))], root=tmp_path, checksums={str(file): "0" * 32}
    )
    assert extract.reason in HOW_TO, extract.reason
    assert "MD5" in EXPLANATION


def test_the_documented_ambiguity_reason_is_the_real_one(tmp_path):
    for directory in ("a", "b"):
        (tmp_path / directory).mkdir()
        (tmp_path / directory / "solver.c").write_text("int main(void) { return 0; }\n")
    extract = _reason([_detail("/build/solver.c")], root=tmp_path)
    assert extract.reason is not None
    quoted = re.search(r"^ambiguous: .+$", HOW_TO, re.MULTILINE)
    assert quoted is not None, "the page shows no ambiguity message"
    shape = re.escape(quoted.group(0)).replace(r"2", r"\d+").replace(
        re.escape("/home/me/project"), ".+"
    )
    assert re.fullmatch(shape, extract.reason), extract.reason


def test_a_resolved_extract_carries_the_documented_context(tmp_path):
    file = tmp_path / "kernels.c"
    file.write_text("\n".join(f"line {n}" for n in range(1, 40)) + "\n")
    extract = _reason([_detail(str(file), line=20)], root=tmp_path)
    assert extract.reason is None
    assert extract.start_line == 20 - 2 - source.CONTEXT_LINES
    assert extract.end_line == 20 + source.CONTEXT_LINES
    # Prose spells small numbers; the constant is still what is checked.
    words = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five"}
    assert f"{words[source.CONTEXT_LINES]} lines of context" in EXPLANATION
    assert f"{source.MAX_EXTRACT_LINES} lines" in EXPLANATION


def test_the_documented_search_order_is_the_real_one(tmp_path):
    """The map wins over a recorded path that no longer exists, and the
    longest prefix wins over a shorter one - both stated on the page."""
    mapped = tmp_path / "elsewhere"
    mapped.mkdir()
    (mapped / "kernels.c").write_text("int sweep(void) { return 0; }\n")
    extract = _reason(
        [_detail("/build/solver/kernels.c")],
        source_map={"/build": str(tmp_path / "wrong"), "/build/solver": str(mapped)},
        root=tmp_path,
    )
    assert extract.resolved_path == str(mapped / "kernels.c")
    assert "longest prefix first" in EXPLANATION
    assert "longest matching prefix wins" in HOW_TO
