# Frozen-binaries corpus

Small ELF binaries built once from the sources sitting next to them,
committed, and never rebuilt implicitly. They are the fixed input of the
`-m llvm` test lane (`tests/test_llvm_corpus.py`) and of the LLVM
version watch: with the binaries frozen, the only variable in those runs
is the LLVM under test, so a changed verdict can only mean the tools
changed.

The variants cover what the attribution chain must keep reading the
same way: DWARF present, absent, stripped, a guaranteed inline chain,
clang's line-table MD5 fingerprints, AVX-512 encodings, and an aarch64
SVE binary the x86 tools must still symbolize - LLVM's readers are
cross-architecture by construction.

| Binary | Build | Exercises |
|---|---|---|
| `symbols-debug` | `gcc -O2 -g` | line-level chains, extents, gcc's fingerprint-less line table |
| `symbols-nodebug` | `gcc -O2` | function level from `.symtab` alone |
| `symbols-stripped` | `gcc -O2` + `strip` | `.dynsym`-only section inventory |
| `symbols-inlined` | `gcc -O3 -g -DFORCE_INLINE` | inline chains, innermost first |
| `symbols-avx512` | `gcc -O3 -g -march=x86-64-v4 -mprefer-vector-width=512` | zmm encodings; source of `listings/axpy-avx512.s` |
| `symbols-clang` | `clang -O2 -g` | DWARF 5 line-table MD5 fingerprints |
| `symbols-sve` | `aarch64-linux-gnu-gcc -O3 -g -march=armv8.2-a+sve` | cross-architecture symbolization, SVE encodings |
| `gather-avx2` | `gcc -O2 -g -mavx2` | `vgatherdpd` from intrinsics; source of `listings/gather-avx2.s` |

Frozen 2026-08-22 on Ubuntu 25.04 x86_64 (AMD EPYC 7702) with
gcc 14.2.0, clang 20.1.2, GNU binutils 2.44 and
aarch64-linux-gnu-gcc 14.2.0.

**Refreshing is a deliberate act**, not maintenance: run
`capture.sh` on such a machine, then `python corpus/listings/extract.py`
to regenerate the llvm-mca listings from the new binaries, and update
the paragraph above. The tests anchor on each binary's own symbol table,
never on hard-coded addresses, so a refresh does not touch them - but
every frozen expectation (which build inlines, which vectorizes at what
width) must be re-verified against the new compilers.
