"""Sphinx configuration for the nunatak documentation site."""

import nunatak

project = "nunatak"
author = "the nunatak authors"
copyright = "2026, the nunatak authors"
release = nunatak.__version__

extensions = ["myst_parser", "sphinx.ext.autodoc"]

# spec/ and adr/ are French design documents, not part of the site.
exclude_patterns = ["_build", "spec", "adr", "brand"]

html_theme = "furo"
html_title = "nunatak"

autodoc_member_order = "bysource"
