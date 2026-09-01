/* The kernels of the reaction-diffusion step.
 *
 * They live in their own translation unit, as they would in a real code:
 * the compiler cannot inline them into the driver, so each one is a
 * function with a symbol, an extent and an address - which is what a
 * profiler attributes samples to.
 */
#include "kernels.h"

void laplacian(const double *u, double *lap, int n)
{
    for (int j = 1; j < n - 1; j++)
        for (int i = 1; i < n - 1; i++)
            lap[j * n + i] = u[(j - 1) * n + i] + u[(j + 1) * n + i]
                           + u[j * n + i - 1] + u[j * n + i + 1]
                           - 4.0 * u[j * n + i];
}

void reaction(const double *u, double *f, int n)
{
    for (int j = 1; j < n - 1; j++)
        for (int i = 1; i < n - 1; i++) {
            double x = u[j * n + i];
            double p = 1.0;
            for (int k = 0; k < 4; k++)
                p = p * x + 0.5;
            f[j * n + i] = x * (1.0 - x) * p;
        }
}

void update(double *u, const double *lap, const double *f, double dt, int n)
{
    for (int j = 1; j < n - 1; j++)
        for (int i = 1; i < n - 1; i++)
            u[j * n + i] += dt * (lap[j * n + i] + f[j * n + i]);
}
