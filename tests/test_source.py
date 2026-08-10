"""Source resolution and extraction, and their journey into the Run.

The replay tests re-create the workload source next to the replayed
corpus entry: resolution must find it by basename, and the extract must
land in the persisted Run with its exact line range.
"""

import json
from pathlib import Path

import pytest

from nunatak.attribution import source
from tests.support import WORKLOAD_C
from nunatak.cli import principal
from nunatak.pivot import (
    AddressDetail,
    Hotspot,
    InlineFrame,
    LogicalIdentity,
    PhysicalIdentity,
    ResolutionLevel,
    SourceExtract,
    read_run,
)

CORPUS = (
    Path(__file__).resolve().parent.parent
    / "corpus"
    / "recordings"
    / "perf"
    / "6.14.11"
    / "linux-x86_64"
    / "workload-c-debug"
)



def hotspot(name="main", file="/build/app/solver.c"):
    return Hotspot(
        logical_identity=LogicalIdentity(
            module="/opt/app/solver", name=name, source_file=file
        ),
        resolution_level=ResolutionLevel.LINE,
        physical_identity=PhysicalIdentity(module_id="deadbeef", offset=0x1000),
    )


def detail(hotspot, frames, offset=0x1010, counter="cycles", value=100.0):
    return AddressDetail(
        hotspot=hotspot,
        offset=offset,
        counter=counter,
        value=value,
        frames=frames,
    )


def frame(function="main", file="/build/app/solver.c", line=20, declaration_line=15):
    return InlineFrame(
        function=function, file=file, line=line, declaration_line=declaration_line
    )


class TestResolution:
    def test_the_dwarf_path_wins_when_it_exists(self, tmp_path):
        recorded = tmp_path / "solver.c"
        recorded.write_text("int main(void) { return 0; }\n")
        spot = hotspot(file=str(recorded))
        (extract,) = source.extract(
            [detail(spot, (frame(file=str(recorded), line=1, declaration_line=1),))],
            {},
            tmp_path,
        )
        assert extract.resolved_path == str(recorded)
        assert extract.text is not None

    def test_the_longest_source_map_prefix_rewrites_the_path(self, tmp_path):
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "solver.c").write_text("double a;\n" * 30)
        mapping = {
            "/build/app": str(tmp_path / "elsewhere"),
            "/build/app/sub": str(tmp_path / "sub"),
        }
        spot = hotspot(file="/build/app/sub/solver.c")
        (extract,) = source.extract(
            [detail(spot, (frame(file="/build/app/sub/solver.c", line=20),))],
            mapping,
            tmp_path / "empty",
        )
        assert extract.resolved_path == str(tmp_path / "sub" / "solver.c")

    def test_a_unique_basename_under_the_root_is_found(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "solver.c").write_text("double a;\n" * 30)
        (extract,) = source.extract(
            [detail(hotspot(), (frame(),))],
            {},
            tmp_path,
        )
        assert extract.resolved_path == str(tmp_path / "src" / "solver.c")

    def test_ambiguous_matches_are_refused_with_the_reason(self, tmp_path):
        for sub in ("a", "b"):
            (tmp_path / sub).mkdir()
            (tmp_path / sub / "solver.c").write_text("double a;\n")
        (extract,) = source.extract([detail(hotspot(), (frame(),))], {}, tmp_path)
        assert extract.text is None
        assert "ambiguous: 2 files named 'solver.c'" in extract.reason

    def test_a_missing_file_carries_its_reason(self, tmp_path):
        (extract,) = source.extract([detail(hotspot(), (frame(),))], {}, tmp_path)
        assert extract.text is None
        assert extract.reason == "source file not found on this machine"

    def test_hidden_trees_and_runs_are_never_searched(self, tmp_path):
        for sub in (".git", ".nunatak"):
            (tmp_path / sub).mkdir()
            (tmp_path / sub / "solver.c").write_text("double a;\n")
        (extract,) = source.extract([detail(hotspot(), (frame(),))], {}, tmp_path)
        assert extract.reason == "source file not found on this machine"


class TestExtraction:
    def test_the_range_runs_from_declaration_to_last_line_with_context(self, tmp_path):
        recorded = tmp_path / "solver.c"
        recorded.write_text("".join(f"line {n}\n" for n in range(1, 41)))
        spot = hotspot(file=str(recorded))
        frames = (
            frame(function="axpy", file=str(recorded), line=12, declaration_line=10),
            frame(function="main", file=str(recorded), line=25, declaration_line=20),
        )
        (extract,) = source.extract([detail(spot, frames)], {}, tmp_path)
        assert (extract.start_line, extract.end_line) == (7, 28)
        assert extract.text.splitlines()[0] == "line 7"
        assert extract.text.splitlines()[-1] == "line 28"
        assert not extract.truncated

    def test_bounds_are_clamped_to_the_file(self, tmp_path):
        recorded = tmp_path / "solver.c"
        recorded.write_text("one\ntwo\nthree\n")
        spot = hotspot(file=str(recorded))
        (extract,) = source.extract(
            [detail(spot, (frame(file=str(recorded), line=2, declaration_line=1),))],
            {},
            tmp_path,
        )
        assert (extract.start_line, extract.end_line) == (1, 3)

    def test_never_a_whole_file_the_cap_is_marked(self, tmp_path):
        recorded = tmp_path / "solver.c"
        recorded.write_text("".join(f"line {n}\n" for n in range(1, 501)))
        spot = hotspot(file=str(recorded))
        (extract,) = source.extract(
            [detail(spot, (frame(file=str(recorded), line=400, declaration_line=2),))],
            {},
            tmp_path,
        )
        assert extract.truncated
        assert extract.end_line - extract.start_line + 1 == source.MAX_EXTRACT_LINES

    def test_a_frame_inlined_from_a_header_yields_its_own_extract(self, tmp_path):
        for name in ("solver.c", "axpy.h"):
            (tmp_path / name).write_text("code\n" * 30)
        spot = hotspot(file=str(tmp_path / "solver.c"))
        frames = (
            frame(
                function="axpy",
                file=str(tmp_path / "axpy.h"),
                line=5,
                declaration_line=3,
            ),
            frame(file=str(tmp_path / "solver.c")),
        )
        extracts = source.extract([detail(spot, frames)], {}, tmp_path)
        assert [Path(e.file).name for e in extracts] == ["axpy.h", "solver.c"]
        assert all(e.text is not None for e in extracts)


class TestModel:
    def test_an_absent_extract_always_says_why(self):
        with pytest.raises(ValueError, match="reason"):
            SourceExtract(hotspot=hotspot(), file="x.c")
        with pytest.raises(ValueError, match="no absence reason"):
            SourceExtract(hotspot=hotspot(), file="x.c", text="code", reason="gone")


class TestReplayedExtraction:
    """The whole pipeline against the recorded corpus entry, the workload
    source re-created next to the replay so resolution can find it."""

    @pytest.fixture(autouse=True)
    def in_tmp_cwd(self, tmp_path, monkeypatch):
        (tmp_path / "nunatak.toml").write_text(
            '[tools]\nllvm-symbolizer = "/usr/lib/llvm-19/bin/llvm-symbolizer"\n'
        )
        (tmp_path / "workload.c").write_text(WORKLOAD_C)
        monkeypatch.chdir(tmp_path)

    def test_the_extract_lands_in_the_run_with_its_exact_range(self, capsys):
        assert principal(["run", "--replay", str(CORPUS), "--json", "--", "./workload"]) == 0
        summary = json.loads(capsys.readouterr().out)
        run = read_run(summary["run"])

        (extract,) = [
            e for e in run.source_extracts if e.hotspot.display_name == "main"
        ]
        assert extract.file == "/tmp/nunatak-capture-debug/workload.c"
        # Declarations at lines 8 (reduce) and 15 (main), last sampled
        # line 20, three context lines on each side.
        assert (extract.start_line, extract.end_line) == (5, 23)
        assert "static double reduce" in extract.text
        assert "int main(void)" in extract.text
        assert not extract.truncated

    def test_unresolvable_system_sources_carry_their_reason(self, capsys):
        assert principal(["run", "--replay", str(CORPUS), "--json", "--", "./workload"]) == 0
        summary = json.loads(capsys.readouterr().out)
        run = read_run(summary["run"])
        # ld.so was built from ./elf/... paths that exist nowhere here.
        reasons = [e.reason for e in run.source_extracts if e.text is None]
        assert reasons
        assert all(reason is not None for reason in reasons)

    def test_no_source_embeds_nothing(self, capsys):
        assert (
            principal(
                ["run", "--replay", str(CORPUS), "--no-source", "--json", "--", "./workload"]
            )
            == 0
        )
        summary = json.loads(capsys.readouterr().out)
        run = read_run(summary["run"])
        assert run.source_extracts == []
        assert run.address_details != []

    def test_a_malformed_source_map_fails_before_launch(self, capsys):
        assert (
            principal(
                ["run", "--replay", str(CORPUS), "--source-map", "no-separator", "--json", "--", "./x"]
            )
            == 125
        )


CLANG_CORPUS = CORPUS.parent / "workload-c-clang"
WORKLOAD_MD5 = "15145baf1577721b3db763dad1ac80af"


def recorded_dwarfdump(entry, module_suffix):
    for record in sorted((entry / "invocations").glob("*.json")):
        argv = json.loads(record.read_text())["argv"]
        if "--debug-line" in argv and argv[-1].endswith(module_suffix):
            return record.with_suffix(".stdout").read_text()
    raise AssertionError(f"no dwarfdump of {module_suffix} in the corpus entry")


class TestLineTableChecksums:
    """Fingerprint parsing against genuine llvm-dwarfdump output, read
    from the recorded workload-c-clang corpus entry."""

    def test_the_clang_line_table_yields_per_file_fingerprints(self):
        from nunatak.attribution import staleness
        from tests.support import ScriptedExecutor

        executor = ScriptedExecutor().on(
            "llvm-dwarfdump", stdout=recorded_dwarfdump(CLANG_CORPUS, "workload")
        )
        checksums = staleness.line_table_checksums(
            executor, "/usr/lib/llvm-19/bin/llvm-dwarfdump", "workload"
        )
        assert checksums["/tmp/nunatak-capture-clang/workload.c"] == WORKLOAD_MD5
        assert all(len(md5) == 32 for md5 in checksums.values())

    def test_a_gcc_line_table_without_checksums_verifies_nothing(self):
        from nunatak.attribution import staleness
        from tests.support import ScriptedExecutor

        # gcc emits no md5_checksum entries: same prologue, no fingerprints.
        executor = ScriptedExecutor().on(
            "llvm-dwarfdump",
            stdout='include_directories[  0] = "/tmp"\nfile_names[  0]:\n'
            '           name: "workload.c"\n      dir_index: 0\n',
        )
        assert (
            staleness.line_table_checksums(executor, "llvm-dwarfdump", "workload")
            == {}
        )

    def test_a_missing_tool_verifies_nothing(self):
        from nunatak.attribution import staleness
        from tests.support import ScriptedExecutor

        executor = ScriptedExecutor().on(
            "llvm-dwarfdump", stderr="not found", exit_code=127
        )
        assert (
            staleness.line_table_checksums(executor, "llvm-dwarfdump", "workload")
            == {}
        )

    def test_dwarfdump_sits_next_to_the_located_symbolizer(self):
        from nunatak.attribution import staleness

        assert (
            staleness.dwarfdump_path("/usr/lib/llvm-19/bin/llvm-symbolizer")
            == "/usr/lib/llvm-19/bin/llvm-dwarfdump"
        )
        assert staleness.dwarfdump_path("/usr/bin/llvm-symbolizer-19") == (
            "/usr/bin/llvm-dwarfdump-19"
        )


class TestStaleness:
    def test_an_edited_file_is_neither_shown_nor_embedded(self, tmp_path):
        edited = tmp_path / "solver.c"
        edited.write_text("// edited since the build\n" + "code\n" * 30)
        spot = hotspot(file=str(edited))
        (extract,) = source.extract(
            [detail(spot, (frame(file=str(edited), line=10, declaration_line=5),))],
            {},
            tmp_path,
            checksums={str(edited): "0" * 32},
        )
        assert extract.text is None
        assert "changed since the profiled binary was built" in extract.reason
        assert extract.resolved_path == str(edited)

    def test_a_matching_fingerprint_lets_the_extract_through(self, tmp_path):
        import hashlib

        pristine = tmp_path / "solver.c"
        pristine.write_text("code\n" * 30)
        fingerprint = hashlib.md5(
            pristine.read_bytes(), usedforsecurity=False
        ).hexdigest()
        spot = hotspot(file=str(pristine))
        (extract,) = source.extract(
            [detail(spot, (frame(file=str(pristine), line=10, declaration_line=5),))],
            {},
            tmp_path,
            checksums={str(pristine): fingerprint},
        )
        assert extract.text is not None

    def test_without_a_fingerprint_the_extract_is_accepted_as_is(self, tmp_path):
        unverifiable = tmp_path / "solver.c"
        unverifiable.write_text("code\n" * 30)
        spot = hotspot(file=str(unverifiable))
        (extract,) = source.extract(
            [detail(spot, (frame(file=str(unverifiable), line=10, declaration_line=5),))],
            {},
            tmp_path,
        )
        assert extract.text is not None


class TestReplayedStaleness:
    """The clang-built corpus entry end to end: the line table carries
    real fingerprints, and the re-created source matches them."""

    @pytest.fixture(autouse=True)
    def in_tmp_cwd(self, tmp_path, monkeypatch):
        (tmp_path / "nunatak.toml").write_text(
            '[tools]\nllvm-symbolizer = "/usr/lib/llvm-19/bin/llvm-symbolizer"\n'
        )
        (tmp_path / "workload.c").write_text(WORKLOAD_C)
        monkeypatch.chdir(tmp_path)

    def test_a_verified_extract_lands_in_the_run(self, capsys):
        import hashlib

        assert hashlib.md5(WORKLOAD_C.encode(), usedforsecurity=False).hexdigest() == WORKLOAD_MD5

        assert (
            principal(["run", "--replay", str(CLANG_CORPUS), "--json", "--", "./workload"])
            == 0
        )
        summary = json.loads(capsys.readouterr().out)
        run = read_run(summary["run"])
        (extract,) = [
            e for e in run.source_extracts if e.hotspot.display_name == "main"
        ]
        assert extract.file == "/tmp/nunatak-capture-clang/workload.c"
        assert extract.text is not None
        assert "axpy_element" in extract.text
