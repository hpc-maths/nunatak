# Call stacks

A Hotspot says which function burns the time. A call stack says which of
your calls put it there - and that is what turns a hot `dgemm` inside
OpenBLAS into a line of your own solver.

Stacks are not free and not always available, so nunatak settles what a
binary can afford before spending compute on it. The recipe asks that
question and acts on the answer; the page after it says why the answer is
a rate rather than a yes, and what the stacks become once recorded.

```{toctree}
:maxdepth: 1

get-call-stacks
the-call-stack-ladder
```
