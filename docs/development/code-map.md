# The code, module by module

A map of the package, generated from its own docstrings and grouped the
way [the architecture](architecture.md) cuts it.

**No module here is a public contract.** `nunatak` exports nothing but
`__version__`; what follows is for whoever changes the code, not for
whoever imports it. Names, signatures and the split itself move without
notice.

## Upstream of the pivot

Everything here writes into the pivot and never reads an analysis back. Addresses stop being absolute at `ingestion`.

```{eval-rst}
.. automodule:: nunatak.launch
   :members:

.. automodule:: nunatak.rank
   :members:

.. automodule:: nunatak.collect
   :members:

.. automodule:: nunatak.collect.execution
   :members:

.. automodule:: nunatak.collect.perf
   :members:

.. automodule:: nunatak.collect.events
   :members:

.. automodule:: nunatak.collect.stacks
   :members:

.. automodule:: nunatak.collect.interpreter
   :members:

.. automodule:: nunatak.collect.pyspy
   :members:

.. automodule:: nunatak.collect.mpip
   :members:

.. automodule:: nunatak.collect.xctrace
   :members:

.. automodule:: nunatak.collect.sample
   :members:

.. automodule:: nunatak.collect.powermetrics
   :members:

.. automodule:: nunatak.ingestion
   :members:

.. automodule:: nunatak.ingestion.samples
   :members:

.. automodule:: nunatak.ingestion.perf_script
   :members:

.. automodule:: nunatak.ingestion.perf_stat
   :members:

.. automodule:: nunatak.ingestion.rank_counting
   :members:

.. automodule:: nunatak.ingestion.mpip_report
   :members:

.. automodule:: nunatak.ingestion.pyspy_raw
   :members:

.. automodule:: nunatak.ingestion.xctrace_profile
   :members:

.. automodule:: nunatak.ingestion.sample_report
   :members:

.. automodule:: nunatak.ingestion.powermetrics_plist
   :members:

.. automodule:: nunatak.attribution
   :members:

.. automodule:: nunatak.attribution.symbolizer
   :members:

.. automodule:: nunatak.attribution.addr2line
   :members:

.. automodule:: nunatak.attribution.atos
   :members:

.. automodule:: nunatak.attribution.debuginfod
   :members:

.. automodule:: nunatak.attribution.inspection
   :members:

.. automodule:: nunatak.attribution.loops
   :members:

.. automodule:: nunatak.attribution.source
   :members:

.. automodule:: nunatak.attribution.staleness
   :members:

.. automodule:: nunatak.probe
   :members:

.. automodule:: nunatak.calibration
   :members:

.. automodule:: nunatak.calibration.theory
   :members:

.. automodule:: nunatak.calibration.kernel
   :members:

```

## The pivot

The boundary itself: the domain classes, and the directory they are written to and read from.

```{eval-rst}
.. automodule:: nunatak.pivot
   :members:

.. automodule:: nunatak.pivot.model
   :members:

.. automodule:: nunatak.pivot.persistence
   :members:

```

## Downstream of the pivot

Everything here reads the pivot and never modifies it. None of it persists what it computes.

```{eval-rst}
.. automodule:: nunatak.analysis
   :members:

.. automodule:: nunatak.explain
   :members:

.. automodule:: nunatak.explain.pi
   :members:

.. automodule:: nunatak.explain.prompt
   :members:

.. automodule:: nunatak.explain.generate
   :members:

.. automodule:: nunatak.explain.consent
   :members:

.. automodule:: nunatak.explain.store
   :members:

.. automodule:: nunatak.compare
   :members:

.. automodule:: nunatak.summary
   :members:

.. automodule:: nunatak.report
   :members:

.. automodule:: nunatak.report.payload
   :members:

.. automodule:: nunatak.report.html
   :members:

```

## The command line

One module per verb, and a parser that holds no decision of its own.

```{eval-rst}
.. automodule:: nunatak.cli
   :members:

.. automodule:: nunatak.cli.run
   :members:

.. automodule:: nunatak.cli.doctor
   :members:

.. automodule:: nunatak.cli.explain
   :members:

.. automodule:: nunatak.cli.report
   :members:

.. automodule:: nunatak.cli.compare
   :members:

.. automodule:: nunatak.cli.calibrate
   :members:

```

## Serving both sides

The Machine and its snapshot, the configuration cascade, the terminal, the recording corpus, and the reserved exit codes.

```{eval-rst}
.. automodule:: nunatak.machine
   :members:

.. automodule:: nunatak.provenance
   :members:

.. automodule:: nunatak.config
   :members:

.. automodule:: nunatak.console
   :members:

.. automodule:: nunatak.corpus
   :members:

.. automodule:: nunatak.exit_codes
   :members:

.. automodule:: nunatak.powerfilter
   :members:

```
