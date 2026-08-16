"""mpiP: the MPI collector, preloaded into every rank.

mpiP wraps the PMPI interface through `LD_PRELOAD` - the application is
never recompiled - and writes one aggregated report at `MPI_Finalize`:
per-rank MPI time and sent volumes, the counting layer's view of the
network. The library must be built against the site's MPI stack:
`locate` finds an existing copy (configuration, module, or our own
cache), and `build` compiles the pinned source with the site's own
compilers into the stack's cache entry, next to the network probe -
during `doctor`, on a login node, never during a run.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import tarfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Mapping

from nunatak import probe
from nunatak.collect.execution import Executor
from nunatak.config import Config

LIBRARY = "libmpiP.so"

# After the configuration and the loader path, the prefixes a hand-built
# mpiP usually lands in.
SEARCH_DIRS = ("/usr/local/lib", "/usr/lib")

# The pinned source: one commit, one checksum. GitHub generates these
# archives on the fly, so the checksum is the only real pin - a refused
# download degrades with the manual remedy, it never builds a surprise.
# This commit rather than release 3.5, whose configure predates
# python-is-python3 systems.
MPIP_COMMIT = "8ff38c37777111543307fa40274caa96be8a916b"
SOURCE_URL = f"https://github.com/LLNL/mpiP/archive/{MPIP_COMMIT}.tar.gz"
SOURCE_SHA256 = "9532986c11ed1fea05abbde07bf76b9fc6aad5b691554d0ff647c11606f0c2d2"


def locate(
    config: Config,
    environment: Mapping[str, str] = os.environ,
    mpi_stack: probe.MpiStack | None = None,
) -> str | None:
    """The path of `libmpiP.so`, or None when no copy is found.

    `tools.mpip` in the configuration wins and is trusted only if the
    file exists; then each directory of `LD_LIBRARY_PATH` - which is how
    an environment module exposes the site's build - then the usual
    prefixes, then the copy `build` cached for this exact MPI stack.
    Located here on the login node, used on the compute nodes: the path
    must hold there too, which a shared filesystem gives for free.
    """
    configured = config.tools.get("mpip")
    if configured:
        return configured if Path(configured).is_file() else None
    directories = environment.get("LD_LIBRARY_PATH", "").split(os.pathsep)
    for directory in (*directories, *SEARCH_DIRS):
        candidate = Path(directory) / LIBRARY if directory else None
        if candidate is not None and candidate.is_file():
            return str(candidate)
    if mpi_stack is not None:
        cached = probe.cache_directory() / probe.stack_key(mpi_stack) / LIBRARY
        if cached.is_file():
            return str(cached)
    return None


def fortran_wrapper(executor: Executor, config: Config) -> str | None:
    """The usable Fortran MPI wrapper, None when nothing answers.

    mpiP's build unconditionally compiles one Fortran object, so a
    wrapper is a hard prerequisite of building - not of using a copy
    built elsewhere. `tools.mpifort` wins, then the conventional names.
    """
    candidates = []
    if "mpifort" in config.tools:
        candidates.append(config.tools["mpifort"])
    candidates += ["mpifort", "mpif77"]
    for candidate in candidates:
        if executor.run([candidate, "--version"]).exit_code == 0:
            return candidate
    return None


def _sha256(path: Path) -> str:
    """The checksum that decides whether a downloaded archive is ours."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def download(destination: Path, url: str = SOURCE_URL, digest: str = SOURCE_SHA256) -> bool:
    """Fetch the pinned source archive into `destination`.

    A file already there with the right checksum short-circuits - once
    fetched, the build works offline forever. A wrong checksum removes
    the file and refuses: building unverified source is worse than
    building nothing.
    """
    if destination.is_file() and _sha256(destination) == digest:
        return True
    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            destination.write_bytes(response.read())
    except (urllib.error.URLError, OSError, TimeoutError):
        return False
    if _sha256(destination) != digest:
        destination.unlink(missing_ok=True)
        return False
    return True


def _extracted(tarball: Path, workspace: Path) -> Path | None:
    """Extract `tarball` into `workspace` and return its top directory.

    Members are validated before extraction: the archive is checksummed,
    but a path that escapes the workspace is refused on principle. The
    `data` filter does the same job on interpreters that have it; the
    early 3.10 patch levels that lack it fall back on the validation.
    """
    with tarfile.open(tarball) as archive:
        members = archive.getmembers()
        if any(
            member.name.startswith("/") or ".." in Path(member.name).parts
            for member in members
        ):
            return None
        try:
            archive.extractall(workspace, filter="data")
        except TypeError:
            archive.extractall(workspace)
    directories = [entry for entry in workspace.iterdir() if entry.is_dir()]
    return directories[0] if len(directories) == 1 else None


def build(
    executor: Executor,
    mpi_stack: probe.MpiStack,
    fortran: str,
    directory: Path | None = None,
    url: str = SOURCE_URL,
    digest: str = SOURCE_SHA256,
) -> Path | None:
    """Compile the pinned mpiP against `mpi_stack` and cache the library.

    The library lands in the stack's cache entry, next to the network
    probe: same key, same lifetime, same explanation. Returns None on
    any failure - a refused download, configure, make - and the caller
    names the degradation; the fetched archive is kept, so a transient
    build problem never re-downloads.
    """
    directory = probe.cache_directory() if directory is None else directory
    entry = directory / probe.stack_key(mpi_stack)
    library = entry / LIBRARY
    if library.is_file():
        return library
    entry.mkdir(parents=True, exist_ok=True)
    tarball = entry / "mpip-source.tar.gz"
    if not download(tarball, url, digest):
        return None
    workspace = entry / "build"
    shutil.rmtree(workspace, ignore_errors=True)
    workspace.mkdir()
    source = _extracted(tarball, workspace)
    if source is None:
        return None
    configured = executor.run(
        ["./configure", f"CC={mpi_stack.mpicc}", f"F77={fortran}"], cwd=str(source)
    )
    if configured.exit_code != 0:
        return None
    made = executor.run(["make", "shared"], cwd=str(source))
    if made.exit_code != 0 or not (source / LIBRARY).is_file():
        return None
    shutil.copy2(source / LIBRARY, library)
    shutil.rmtree(workspace, ignore_errors=True)
    return library
