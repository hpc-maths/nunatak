# Reading a report

Every measuring run writes `report.html` into the Run directory. Rather
than describe it, this subject publishes one:

<!-- Written as HTML on purpose: a markdown link to a file rather than
     to a page becomes a download link, and these two are meant to be
     opened. -->

- <a href="../../_static/example-report.html">the report of a real Run</a> -
  the `examples/stencil` program profiled on an EPYC 7702;
- <a href="../../_static/example-compare.html">the comparison of two Runs</a> -
  the same program before and after the fix its own report points at.

Open the first one and read the page below beside it. The recipe comes
after: a report is regenerated, shared without its source, and completed
with advice long after the run.

```{toctree}
:maxdepth: 1

the-three-reading-levels
regenerate-and-share-a-report
```
