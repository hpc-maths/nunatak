"""The LLM explanation layer.

The model explains and suggests from facts the deterministic analysis
already established; it never diagnoses, measures or classifies. Access
goes through pi, an external tool orchestrated like perf or nsys:
"exec + parse" extended to the language model. pi's own configuration
is the single source of providers and models - nunatak reads it, never
duplicates it, never overrides it.
"""

from nunatak.explain.pi import Identity, Pi, identity, locate, readiness

__all__ = ["Identity", "Pi", "identity", "locate", "readiness"]
