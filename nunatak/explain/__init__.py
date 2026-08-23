"""The LLM explanation layer.

The model explains and suggests from facts the deterministic analysis
already established; it never diagnoses, measures or classifies. Access
goes through pi, an external tool orchestrated like perf or nsys:
"exec + parse" extended to the language model. pi's own configuration
is the single source of providers and models - nunatak reads it, never
duplicates it, never overrides it.
"""

# The generate function itself is not re-exported: the name would
# shadow its own submodule at the package level - Python binds the
# attribute, not the module - and Sphinx would document it twice.
from nunatak.explain.generate import Explanation, Failure
from nunatak.explain.pi import Identity, Pi, identity, locate, readiness
from nunatak.explain.prompt import SYSTEM_PROMPT, Request, Withheld, requests

__all__ = [
    "SYSTEM_PROMPT",
    "Explanation",
    "Failure",
    "Identity",
    "Pi",
    "Request",
    "Withheld",
    "identity",
    "locate",
    "readiness",
    "requests",
]
