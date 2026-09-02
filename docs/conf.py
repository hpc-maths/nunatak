"""Sphinx configuration for the nunatak documentation site."""

import nunatak

project = "nunatak"
author = "the nunatak authors"
copyright = "2026, the nunatak authors"
release = nunatak.__version__

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinxarg.ext",
    "sphinx_design",  # the landing page's five cards
]

# spec/ is what remains of the French design document: the work that is
# not built yet. It is not part of the site.
exclude_patterns = ["_build", "spec", "brand"]

# Two real artifacts are published with the site and the reader opens
# them: a Run's report and a comparison, both self-contained by product
# invariant, so publishing one is a file copy.
html_static_path = ["_static"]

html_theme = "furo"
html_title = "nunatak"

# One published version, built from main. The banner says so on every
# page, because a reader who lands here from a search engine has no
# other way to know what they are reading.
html_theme_options = {
    "announcement": (
        "You are reading the documentation of the development version. "
        "nunatak has no release yet."
    ),
}

# `:::{grid}` blocks: sphinx-design's own recommended syntax, and the
# only MyST extension the site needs.
myst_enable_extensions = ["colon_fence"]

autodoc_member_order = "bysource"
