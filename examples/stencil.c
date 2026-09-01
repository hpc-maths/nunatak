/* Reaction-diffusion on a 2D grid: one explicit time step per iteration.
 *
 * Two kernels of different character. `laplacian` and `update` move far
 * more memory than they compute; `reaction` evaluates a polynomial per
 * cell and computes far more than it moves. A profiler should say so.
 */
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

#include "kernels.h"

int main(int argc, char **argv)
{
    int n = argc > 1 ? atoi(argv[1]) : 4096;
    int steps = argc > 2 ? atoi(argv[2]) : 60;

    double *u = malloc((size_t)n * n * sizeof(double));
    double *lap = calloc((size_t)n * n, sizeof(double));
    double *f = calloc((size_t)n * n, sizeof(double));
    for (int k = 0; k < n * n; k++)
        u[k] = 0.5 + 0.1 * ((k % 97) / 97.0);

    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);
    for (int s = 0; s < steps; s++) {
        laplacian(u, lap, n);
        reaction(u, f, n);
        update(u, lap, f, 1e-4, n);
    }
    clock_gettime(CLOCK_MONOTONIC, &t1);

    double seconds = (t1.tv_sec - t0.tv_sec) + 1e-9 * (t1.tv_nsec - t0.tv_nsec);
    printf("grid %d x %d, %d steps, %.2f s (%.1f Mcell/s), checksum %.6f\n",
           n, n, steps, seconds, 1e-6 * steps * (double)n * n / seconds,
           u[(n / 2) * n + n / 2]);
    return 0;
}
