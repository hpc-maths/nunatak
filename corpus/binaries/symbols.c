/* Source of the frozen-binaries corpus: three functions whose symbols,
 * extents, line tables and inlining the attribution chain must read the
 * same way under every LLVM version.
 *
 * `poly` is noinline by default so the symbol table offers several
 * distinct extents, and always_inline under FORCE_INLINE so the
 * `symbols-inlined` variant carries a guaranteed inline chain. The
 * first `axpy` loop is a plain triad that vectorizes up to zmm width
 * when the build asks for it.
 */
#include <stdio.h>
#include <stdlib.h>

#ifdef FORCE_INLINE
#define POLY_LINKAGE static inline __attribute__((always_inline))
#else
#define POLY_LINKAGE static __attribute__((noinline))
#endif

POLY_LINKAGE double poly(double x)
{
    return (x * x + 3.0) * x + 1.0;
}

__attribute__((noinline)) double axpy(double a, const double *x, double *y, int n)
{
    double acc = 0.0;
    for (int i = 0; i < n; i++) {
        y[i] = a * x[i] + y[i];
    }
    for (int i = 0; i < n; i++) {
        acc += poly(y[i]);
    }
    return acc;
}

int main(void)
{
    enum { n = 4096 };
    double *x = malloc(n * sizeof *x);
    double *y = malloc(n * sizeof *y);
    for (int i = 0; i < n; i++) {
        x[i] = i * 0.5;
        y[i] = 1.0;
    }
    double acc = 0.0;
    for (int repetition = 0; repetition < 64; repetition++) {
        acc += axpy(1.000001, x, y, n);
    }
    printf("acc %.17g\n", acc);
    free(x);
    free(y);
    return 0;
}
