#ifndef KERNELS_H
#define KERNELS_H

void laplacian(const double *u, double *lap, int n);
void reaction(const double *u, double *f, int n);
void update(double *u, const double *lap, const double *f, double dt, int n);

#endif
