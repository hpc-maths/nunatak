"""Self-contained HTML: the payload and the compiled mini-app in one file.

The page makes no external request - no CDN, no font, no telemetry - so
it opens on a cluster without a server and still reads in ten years from
an archived file. The compiled bundle is built from `report-app/` into
this package's `assets/` directory; a checkout that never built it - or
a wheel packaged without it - loses the report as a named degradation,
never as a crash.
"""

from __future__ import annotations

import json
from html import escape
from pathlib import Path

from nunatak.analysis import Diagnostic
from nunatak.pivot import Run
from nunatak.report import payload as report_payload

ASSETS = Path(__file__).parent / "assets"
SCRIPT = "report.js"
STYLE = "report.css"
REPORT = "report.html"


def assets_available(assets_dir: Path | None = None) -> bool:
    """Whether the compiled mini-app is present in this installation."""
    assets_dir = ASSETS if assets_dir is None else assets_dir
    return (assets_dir / SCRIPT).is_file() and (assets_dir / STYLE).is_file()


def render(payload: dict, assets_dir: Path | None = None) -> str:
    """The complete report page for one payload.

    The payload is embedded as a JSON island the app reads at load time;
    `</` is escaped so no payload content can close the script element.
    Assembled by concatenation: a format string would trip on the braces
    of the inlined CSS and JavaScript.
    """
    assets_dir = ASSETS if assets_dir is None else assets_dir
    data = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    title = escape(f"nunatak - {payload['run']['name']}")
    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{title}</title>\n"
        f"<style>{(assets_dir / STYLE).read_text(encoding='utf-8')}</style>\n"
        "</head>\n"
        "<body>\n"
        f'<script type="application/json" id="nunatak-payload">{data}</script>\n'
        '<div id="nunatak-report"></div>\n'
        f"<script>{(assets_dir / SCRIPT).read_text(encoding='utf-8')}</script>\n"
        "</body>\n"
        "</html>\n"
    )


def write_report(
    directory: Path,
    run: Run,
    diagnostics: list[Diagnostic],
    assets_dir: Path | None = None,
) -> Path:
    """Render the report of `run` into its directory and return its path.

    The report is a product of the Run, regenerable at will: writing it
    next to the pivot keeps the directory self-sufficient without ever
    making the pivot depend on it.
    """
    path = Path(directory) / REPORT
    path.write_text(
        render(report_payload.build(run, diagnostics), assets_dir), encoding="utf-8"
    )
    return path
