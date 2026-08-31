/* Dense matrix multiplication, C = A * B, in double precision.
 *
 * This example exists to check nunatak against a result that is known
 * analytically. The kernel performs exactly 2*n^3 floating-point
 * operations, so the program computes its own GFLOP/s from a wall clock.
 * nunatak measures the same quantity independently, from the hardware
 * counters, and the two numbers must agree.
 *
 * A disagreement is not a bad profile: it means the counter path is
 * wrong for this microarchitecture, and that is what this example is
 * for.
 */
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

#include "gemm.h"

int main(int argc, char **argv)
{
    int n = argc > 1 ? atoi(argv[1]) : 2048;

    double *a = malloc((size_t)n * n * sizeof(double));
    double *b = malloc((size_t)n * n * sizeof(double));
    double *c = calloc((size_t)n * n, sizeof(double));
    for (int k = 0; k < n * n; k++) {
        a[k] = (k % 13) / 13.0;
        b[k] = (k % 7) / 7.0;
    }

    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);
    gemm(n, a, b, c);
    clock_gettime(CLOCK_MONOTONIC, &t1);

    double seconds = (t1.tv_sec - t0.tv_sec) + 1e-9 * (t1.tv_nsec - t0.tv_nsec);
    double flop = 2.0 * n * n * n;
    printf("n = %d, %.3f s, %.2f GFLOP/s analytic, %.0f flop, checksum %.6f\n",
           n, seconds, 1e-9 * flop / seconds, flop, c[(n / 2) * n + n / 2]);
    return 0;
}
