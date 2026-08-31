#ifndef GEMM_H
#define GEMM_H

void gemm(int n, const double *restrict a, const double *restrict b,
          double *restrict c);

#endif
