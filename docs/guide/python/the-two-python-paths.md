# The two Python paths

The function an interpreted application spends its time in has no
symbol, no address and no extent: it exists in the interpreter's data
structures, not in the machine code perf samples. Which of the two paths
around that a Run takes is decided by the interpreter's own version.

Both of them are Linux's: they are built on perf and on `ptrace`. A
macOS Run samples through the platform's own collectors, which attribute
native frames.

## From 3.12, the interpreter publishes its frames

CPython 3.12 can compile a small trampoline per Python function and
publish it in a perf map, which makes Python frames visible inside
native call stacks. `PYTHONPERFSUPPORT=1` in the launch environment is
the whole mechanism, and nunatak sets it when the command names the
interpreter - no line of the application is touched, and no argument
selects it.

That door is not CPython's alone. Anything else that writes a perf map,
Numba and other JITs included, arrives through it with no code of its
own in nunatak.

## The maps are artifacts of the Run, or they are lost

A perf map is written to the node's own `/tmp/perf-<pid>.map`, and its
addresses mean nothing once that process is gone. Every map the
samples reference is therefore copied next to the recording as the
collection ends - inside each sampling MPI rank too, on the rank's own
node, which is exactly the retrieval a multi-node job needs before its
epilogue reclaims the nodes.

The names travel the same way. A trampoline symbol reads
`py::<function>:<file>`, and the parser keeps the pair at parse time
rather than resolving an address later: the map's addresses belong to a
JIT, and no symbolizer can be asked about them afterwards.

## Interpreter time belongs to the function it interprets

A sample landing in CPython's own frames - the evaluation loop, the
allocator - is folded onto the innermost Python frame above it. Time
spent interpreting `sweep` is time spent in `sweep`, which is the exact
sense of the measurement, and a hit inside a trampoline is that function
directly.

The fold stops at the interpreter's edge. A leaf in a native extension -
numpy, pybind11, Cython - stays a native Hotspot with its Python caller
visible in the recorded stack: interpreter frames are never Hotspots,
and extension Hotspots never stop being native.

A Python Hotspot is therefore identified by `(file, function)` at
function-level resolution, with no physical identity. Only native code
has one: an address attached to a Python function would name a
trampoline that exists in one process and nowhere else.

## Below 3.12, py-spy stands in and says what it costs

py-spy reads the interpreter's frames from outside at wall intervals. It
yields the same `(file, function)` Hotspots at the same resolution, and
it carries a named loss, `python-counters-unavailable`: no hardware
counter rides a temporal sampler, so the Run has time and no FLOPs, no
cache traffic, no placement on the roofline. CPython 3.12 restores the
counter path, and the remedy says so.

Two measured facts shape how it is invoked. py-spy exits 0 even when the
application failed, so the application's own exit code is witnessed by a
shell wrapper and propagated from there. And py-spy stays the parent of
everything it samples, which is what keeps the `ptrace` lawful under
yama's default scope: a profiler may always read its descendants, while
attaching to a sibling is refused on a stock kernel.

**The two flows are never fused into one stack.** Two clocks, two
triggers: merging a temporal sample with an event-triggered one would be
double counting dressed as measurement.
