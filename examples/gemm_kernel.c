/* Tiled C = A * B in double precision, in its own translation unit so
 * that it stays a function a profiler can name.
 *
 * `restrict` tells the compiler the three matrices do not overlap, which
 * is what lets it vectorize the inner loop. Without it the kernel runs
 * several times slower and the roofline says so.
 */
#include "gemm.h"

#define TILE 128

void gemm(int n, const double *restrict a, const double *restrict b,
          double *restrict c)
{
    for (int ii = 0; ii < n; ii += TILE)
        for (int kk = 0; kk < n; kk += TILE)
            for (int jj = 0; jj < n; jj += TILE) {
                int imax = ii + TILE < n ? ii + TILE : n;
                int kmax = kk + TILE < n ? kk + TILE : n;
                int jmax = jj + TILE < n ? jj + TILE : n;
                for (int i = ii; i < imax; i++)
                    for (int k = kk; k < kmax; k++) {
                        double aik = a[i * n + k];
                        for (int j = jj; j < jmax; j++)
                            c[i * n + j] += aik * b[k * n + j];
                    }
            }
}
