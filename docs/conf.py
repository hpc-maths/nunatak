"""Sphinx configuration for the nunatak documentation site."""

import nunatak

project = "nunatak"
author = "the nunatak authors"
copyright = "2026, the nunatak authors"
release = nunatak.__version__

extensions = ["myst_parser", "sphinx.ext.autodoc", "sphinxarg.ext"]

# spec/ is what remains of the French design document: the work that is
# not built yet. It is not part of the site.
exclude_patterns = ["_build", "spec", "brand"]

# Two real artifacts are published with the site and the reader opens
# them: a Run's report and a comparison, both self-contained by product
# invariant, so publishing one is a file copy.
html_static_path = ["_static"]

html_theme = "furo"
html_title = "nunatak"

autodoc_member_order = "bysource"
