"""The frozen-binaries corpus against a real LLVM: the version watch's teeth.

Hermetic tests replay recorded tool outputs, so they can never notice a
new LLVM changing what those tools print. This lane runs the real
llvm-symbolizer, llvm-readelf, llvm-dwarfdump and llvm-mca against the
binaries and listings frozen in corpus/ - the only variable left is the
LLVM under test. NUNATAK_LLVM names the bin directory of a candidate
install; without it the host's located LLVM is tested. The lane opts in
with `-m llvm` and fails, never skips, when no LLVM answers: a watch
run that skipped would look green while validating nothing.

Every assertion is an invariant of a frozen artifact, not of a tool's
exact text: the corpus never changes, so what these tests accept must
hold under every LLVM version that is correct about it.
"""

import hashlib
import os
import re
from pathlib import Path

import pytest

from nunatak.attribution import staleness
from nunatak.attribution.inspection import inspect
from nunatak.attribution.loops import _known_cpus, _mca_path, parse_mca
from nunatak.attribution.symbolizer import MINIMUM_LLVM, locate
from nunatak.collect.execution import SubprocessExecutor
from nunatak.config import Config
from nunatak.pivot import ResolutionLevel

pytestmark = pytest.mark.llvm

CORPUS = Path(__file__).resolve().parents[1] / "corpus"
BINARIES = CORPUS / "binaries"
LISTINGS = CORPUS / "listings"

# One FUNC row of llvm-readelf --symbols, GNU style: number, value,
# size, type, binding, visibility, section index, name.
_FUNC = re.compile(
    r"^\s*\d+:\s+(?P<value>[0-9a-f]+)\s+(?P<size>\d+)\s+FUNC"
    r"\s+\S+\s+\S+\s+\S+\s+(?P<name>\S+)$",
    re.M,
)


@pytest.fixture(scope="module")
def executor():
    """A real executor: this lane exists to invoke the actual tools."""
    return SubprocessExecutor()


@pytest.fixture(scope="module")
def symbolizer(executor):
    """The LLVM under test, and proof that it is the one that answered:
    a broken NUNATAK_LLVM must fail here, not silently hand the lane to
    whatever the host offers."""
    override = os.environ.get("NUNATAK_LLVM")
    config = (
        Config(tools={"llvm-symbolizer": os.path.join(override, "llvm-symbolizer")})
        if override
        else Config()
    )
    located = locate(executor, config)
    assert located is not None, "the llvm lane needs a usable llvm-symbolizer"
    if override:
        assert located.path.startswith(override), (
            f"NUNATAK_LLVM={override} did not answer; "
            f"{located.path} would have been tested instead"
        )
    return located


def extents(executor, symbolizer, module: Path) -> dict[str, tuple[int, int]]:
    """{function: (st_value, st_size)} from llvm-readelf --symbols.

    The sweep anchors on the frozen binary's own symbol table instead of
    hard-coded addresses, so a corpus refresh never touches the tests.
    """
    invocation = executor.run([symbolizer.readelf, "--symbols", str(module)])
    assert invocation.exit_code == 0 and invocation.stdout
    return {
        match.group("name"): (int(match.group("value"), 16), int(match.group("size")))
        for match in _FUNC.finditer(invocation.stdout)
    }


def sweep(executor, symbolizer, module: Path, function: str):
    """The attribution chains of every 4th offset across `function`."""
    start, size = extents(executor, symbolizer, module)[function]
    offsets = list(range(start, start + size, 4))
    outcome = symbolizer.symbolize(executor, str(module), offsets)
    assert outcome.error is None
    return start, [outcome.chains[offset] for offset in offsets]


class TestLocatedInstall:
    def test_the_version_parses_and_clears_the_minimum(self, symbolizer):
        assert symbolizer.major >= MINIMUM_LLVM

    def test_the_siblings_answer_from_the_same_install(self, executor, symbolizer):
        for tool in (symbolizer.readelf, symbolizer.dwarfdump):
            invocation = executor.run([tool, "--version"])
            assert invocation.exit_code == 0
            assert f"LLVM version {symbolizer.major}." in (
                f"{invocation.stdout or ''}{invocation.stderr or ''}"
            )


class TestSymbolization:
    def test_the_debug_build_reaches_line_level_across_axpy(
        self, executor, symbolizer
    ):
        start, chains = sweep(
            executor, symbolizer, BINARIES / "symbols-debug", "axpy"
        )
        assert all(c.physical and c.physical.function == "axpy" for c in chains)
        assert any(c.resolution_level is ResolutionLevel.LINE for c in chains)
        files = {c.physical.file for c in chains if c.physical.file}
        assert files and all(f.endswith("symbols.c") for f in files)
        assert chains[0].physical.start_address == start

    def test_the_nodebug_build_still_names_from_the_symbol_table(
        self, executor, symbolizer
    ):
        _, chains = sweep(
            executor, symbolizer, BINARIES / "symbols-nodebug", "axpy"
        )
        assert all(c.resolution_level is ResolutionLevel.FUNCTION for c in chains)
        assert all(c.physical.function == "axpy" for c in chains)
        assert all(c.physical.file is None for c in chains)

    def test_the_inlined_build_carries_an_inline_chain(self, executor, symbolizer):
        _, chains = sweep(
            executor, symbolizer, BINARIES / "symbols-inlined", "axpy"
        )
        assert all(c.physical.function == "axpy" for c in chains)
        inlined = [c for c in chains if len(c.frames) >= 2]
        assert inlined and all(
            c.frames[0].function == "poly" for c in inlined
        )

    def test_the_sve_binary_symbolizes_cross_architecture(
        self, executor, symbolizer
    ):
        _, chains = sweep(executor, symbolizer, BINARIES / "symbols-sve", "axpy")
        assert all(c.physical and c.physical.function == "axpy" for c in chains)
        assert any(c.resolution_level is ResolutionLevel.LINE for c in chains)


class TestInspection:
    def test_the_debug_build_offers_symtab_and_dwarf(self, executor, symbolizer):
        sections = inspect(
            executor, symbolizer.readelf, str(BINARIES / "symbols-debug")
        )
        assert sections is not None
        assert sections.symtab and sections.debug_info

    def test_the_nodebug_build_offers_symtab_only(self, executor, symbolizer):
        sections = inspect(
            executor, symbolizer.readelf, str(BINARIES / "symbols-nodebug")
        )
        assert sections.symtab and not sections.debug_info

    def test_the_stripped_build_keeps_only_dynamic_symbols(
        self, executor, symbolizer
    ):
        sections = inspect(
            executor, symbolizer.readelf, str(BINARIES / "symbols-stripped")
        )
        assert sections.dynsym and not sections.symtab


class TestStaleness:
    def test_clang_fingerprints_are_the_md5_of_the_frozen_source(
        self, executor, symbolizer
    ):
        checksums = staleness.line_table_checksums(
            executor, symbolizer.dwarfdump, str(BINARIES / "symbols-clang")
        )
        ours = [
            value
            for path, value in checksums.items()
            if path.endswith("symbols.c")
        ]
        truth = hashlib.md5((BINARIES / "symbols.c").read_bytes()).hexdigest()
        assert ours == [truth]

    def test_gcc_emits_no_fingerprint_and_none_is_invented(
        self, executor, symbolizer
    ):
        checksums = staleness.line_table_checksums(
            executor, symbolizer.dwarfdump, str(BINARIES / "symbols-debug")
        )
        assert checksums == {}


@pytest.fixture(scope="module")
def mca(symbolizer):
    """The llvm-mca sibling of the install under test."""
    path = _mca_path(symbolizer)
    assert path is not None
    return path


class TestSchedulingModels:
    def test_the_model_list_still_names_our_microarchitectures(
        self, executor, mca
    ):
        assert {"znver2", "znver4", "skylake-avx512"} <= _known_cpus(executor, mca)

    def test_the_avx512_listing_still_models(self, executor, mca):
        invocation = executor.run(
            [mca, "--mcpu=znver4", str(LISTINGS / "axpy-avx512.s")]
        )
        assert invocation.exit_code == 0
        parsed = parse_mca(invocation.stdout)
        assert parsed is not None
        ports, steady = parsed
        # The steady state can approach the port bound, never truly beat
        # it; the slack absorbs simulator rounding, not a real inversion.
        assert 0 < ports <= steady * 1.05

    def test_the_gather_listing_shows_its_dependency_chain(self, executor, mca):
        invocation = executor.run(
            [mca, "--mcpu=znver2", str(LISTINGS / "gather-avx2.s")]
        )
        assert invocation.exit_code == 0
        ports, steady = parse_mca(invocation.stdout)
        assert steady > 3 * ports
