# -mcpu baselines

The scheduling-model inventory (`llvm-mca --mcpu=help`) of each LLVM
major the project validated, one name per line, captured by `dump.py`.

The version watch (`.github/workflows/llvm-watch.yml`) diffs a candidate
major's inventory against the newest baseline here and opens an issue
listing the microarchitectures the new LLVM learned - the signal that
feeds the theory table, the counter event sets and the test bench.

Validating a new major refreshes this directory: run `dump.py` against
it, commit the output as `llvm-<major>.txt`, and bump `TESTED_LLVM`
(`nunatak/attribution/symbolizer.py`) in the same change.
