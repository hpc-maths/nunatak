#!/bin/sh
# Builds the frozen-binaries corpus from the sources sitting next to it.
#
# Run on Linux x86_64 with gcc, clang, binutils and the aarch64 cross
# compiler; the products are committed and never rebuilt implicitly -
# freezing them is the point, so that a version-watch run varies the
# LLVM under test and nothing else. Rerunning this script is a corpus
# refresh: record the compiler versions in the README when you do.
#
# The avx512 variant asks for 512-bit vectors explicitly: gcc prefers
# 256-bit ones on every -march it associates with downclocking, and a
# corpus entry named avx512 that carries ymm code would test nothing.
set -eu
cd "$(dirname "$0")"

gcc -O2 -g -o symbols-debug symbols.c
gcc -O2 -o symbols-nodebug symbols.c
gcc -O2 -o symbols-stripped symbols.c
strip symbols-stripped
gcc -O3 -g -DFORCE_INLINE -o symbols-inlined symbols.c
gcc -O3 -g -march=x86-64-v4 -mprefer-vector-width=512 -o symbols-avx512 symbols.c
clang -O2 -g -o symbols-clang symbols.c
aarch64-linux-gnu-gcc -O3 -g -march=armv8.2-a+sve -o symbols-sve symbols.c
gcc -O2 -g -mavx2 -o gather-avx2 gather.c
