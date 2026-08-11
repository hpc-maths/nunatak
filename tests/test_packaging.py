"""The wheel ships the compiled report bundle, built by the packaging hook.

These tests drive the real hatchling wheel builder over a miniature
project wearing this repo's layout, with a fake `npm` on PATH: what is
under test is the hook - the build at the right moment, inclusion
despite .gitignore, the degraded paths without npm - never the
mini-app's own toolchain, which stays a Node concern.
"""

import importlib.util
import os
import shutil
import zipfile
from pathlib import Path

import pytest
from hatchling.builders.wheel import WheelBuilder

REPO_ROOT = Path(__file__).resolve().parents[1]

PYPROJECT = """\
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "mini"
version = "0"

[tool.hatch.build.targets.wheel]
packages = ["nunatak"]

[tool.hatch.build.targets.wheel.hooks.custom]
path = "hatch_build.py"
"""

FAKE_NPM = """\
#!/bin/sh
echo "$@" >> "$NPM_LOG"
if [ "$1" = run ]; then
  mkdir -p ../nunatak/report/assets
  printf 'bundle' > ../nunatak/report/assets/report.js
  printf 'style' > ../nunatak/report/assets/report.css
fi
"""


@pytest.fixture
def project(tmp_path):
    """A miniature project with the repo's layout and the real hook."""
    root = tmp_path / "proj"
    (root / "nunatak").mkdir(parents=True)
    (root / "nunatak" / "__init__.py").write_text("")
    (root / "report-app").mkdir()
    (root / "pyproject.toml").write_text(PYPROJECT)
    (root / ".gitignore").write_text("nunatak/report/assets/\n")
    shutil.copy(REPO_ROOT / "hatch_build.py", root / "hatch_build.py")
    return root


@pytest.fixture
def fake_npm(tmp_path, monkeypatch):
    """An `npm` stand-in on PATH; returns the file logging its calls."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "npm").write_text(FAKE_NPM)
    (bin_dir / "npm").chmod(0o755)
    log = tmp_path / "npm.log"
    monkeypatch.setenv("NPM_LOG", str(log))
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    return log


@pytest.fixture
def no_npm(tmp_path, monkeypatch):
    """A PATH guaranteed to hold no npm at all."""
    empty = tmp_path / "empty-path"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))


def build_wheel(root, dist):
    """Build `root`'s wheel into `dist` and return the archive's names."""
    builder = WheelBuilder(str(root))
    wheel = next(builder.build(directory=str(dist), versions=["standard"]))
    return zipfile.ZipFile(wheel).namelist()


def load_hook():
    """Import the repo's hatch_build.py the way hatchling does: by path."""
    spec = importlib.util.spec_from_file_location(
        "hatch_build", REPO_ROOT / "hatch_build.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestReportAssetHook:
    """The packaging hook, exercised through real wheel builds."""

    def test_bundle_is_built_from_the_lockfile_and_shipped(
        self, project, fake_npm, tmp_path
    ):
        """With npm present, `npm ci` then the build, and the wheel
        carries both asset files despite their .gitignore entry."""
        names = build_wheel(project, tmp_path / "dist")
        assert "nunatak/report/assets/report.js" in names
        assert "nunatak/report/assets/report.css" in names
        assert fake_npm.read_text().splitlines() == ["ci", "run build"]

    def test_without_npm_the_wheel_still_builds(
        self, project, no_npm, tmp_path
    ):
        """No npm anywhere: the wheel builds and simply lacks the bundle -
        the installed copy will announce report-unavailable."""
        names = build_wheel(project, tmp_path / "dist")
        assert not any("report/assets" in name for name in names)

    def test_without_npm_an_existing_bundle_still_ships(
        self, project, no_npm, tmp_path
    ):
        """A bundle built earlier ships as-is when npm is missing."""
        assets = project / "nunatak" / "report" / "assets"
        assets.mkdir(parents=True)
        (assets / "report.js").write_text("earlier bundle")
        (assets / "report.css").write_text("earlier style")
        names = build_wheel(project, tmp_path / "dist")
        assert "nunatak/report/assets/report.js" in names
        assert "nunatak/report/assets/report.css" in names

    def test_editable_build_never_touches_npm(
        self, project, fake_npm, tmp_path
    ):
        """Editable installs point at the source tree, where the developer
        builds the bundle - or the test suite stubs it. No npm call."""
        hook_class = load_hook().ReportAssetHook
        hook = hook_class(str(project), {}, None, None, str(tmp_path), "wheel")
        build_data = {"artifacts": []}
        hook.initialize("editable", build_data)
        assert build_data == {"artifacts": []}
        assert not fake_npm.exists()
