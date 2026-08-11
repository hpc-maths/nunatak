"""The HTML report: what the user reads, built from what was measured.

The report is a self-contained page rendered by a compiled TypeScript
mini-app; everything the app shows crosses one boundary, the payload -
plain JSON recomputed on demand from the Run and its Diagnostics.
"""

from nunatak.report.payload import build

__all__ = ["build"]
