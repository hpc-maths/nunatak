"""Wheel build hook: compile the report mini-app into the package.

An installed wheel must render reports without Node on the user's
machine, so the bundle is compiled where the wheel is built and shipped
inside it. Node is a build-time dependency only, and an optional one:
without npm the wheel still builds - possibly without the bundle - and
the installed copy announces the `report-unavailable` degradation
instead of failing the install. Release artifacts get the opposite
guarantee from CI, which asserts the asset is present in the wheel it
publishes.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

ASSETS_DIR = Path("nunatak") / "report" / "assets"
ASSETS = ("report.js", "report.css")


def build_bundle(root: Path) -> bool:
    """Compile the mini-app under `root`; False when npm is unavailable.

    `npm ci` rather than `npm install`: the build must follow the
    lockfile exactly, wherever the wheel is built. A failure with npm
    present is a real error and propagates - only the absence of npm is
    a supported, degraded path.
    """
    if shutil.which("npm") is None:
        return False
    app_dir = root / "report-app"
    subprocess.run(["npm", "ci"], cwd=app_dir, check=True)
    subprocess.run(["npm", "run", "build"], cwd=app_dir, check=True)
    return True


class ReportAssetHook(BuildHookInterface):
    """Ship the compiled report bundle inside the wheel."""

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        """Build the bundle and mark it for inclusion in the wheel.

        Editable installs are skipped: they point at the source tree,
        where the developer builds the bundle - or the test suite stubs
        it. The `artifacts` patterns are required because the bundle is
        gitignored, and file selection follows the VCS by default.
        """
        if version != "standard":
            return
        root = Path(self.root)
        if not build_bundle(root):
            shipped = all((root / ASSETS_DIR / name).is_file() for name in ASSETS)
            self.app.display_warning(
                "npm not found; shipping the report bundle already present"
                if shipped
                else "npm not found and no report bundle built: installed"
                " copies will announce the report-unavailable degradation"
            )
        build_data["artifacts"] += [f"/{ASSETS_DIR / name}" for name in ASSETS]
