# debuginfod

debuginfod fetches debug information for the distribution's own
libraries, so that a stripped `libc` or `libmpi` gets its function names
instead of staying `unresolved`. It never helps with the user's own code,
which is where a profile usually spends its time, so the gain is real and
narrow.

nunatak does not implement a client. Both symbolization paths consult
debuginfod on their own when `DEBUGINFOD_URLS` is in the environment,
`llvm-symbolizer` and GNU `addr2line` alike. What nunatak adds is
control.

## What nunatak guarantees about it

It never runs while the application does. Symbolization happens after
the application has exited, so a lookup cannot slow a measurement or
touch its overhead budget. That is a property of the pipeline, not a
setting.

It cannot hang an analysis. The client's own default timeout is 90
seconds per lookup. nunatak writes 10 instead, so an unreachable server
costs the names of a few distribution libraries rather than the analysis.

```toml
[debuginfod]
enabled = true    # false strips DEBUGINFOD_URLS from symbolizer invocations
timeout = 10      # seconds
```

A `DEBUGINFOD_TIMEOUT` already set in the environment wins: an explicit
choice by a user or a site stands.

## Turning it off

`enabled = false` in the site file removes the variable from every
symbolizer invocation, which is what a machine with no outbound network
wants: the client then never fires, rather than trying and waiting.

`doctor` reports the configured servers when there are any. Their absence
is the normal case and not a finding.
