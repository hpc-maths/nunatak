/* Source of the gather variant: compilers never auto-emit vgatherdpd on
 * the microarchitectures we test, so intrinsics are the only honest way
 * to freeze one. Its hot loop feeds llvm-mca's dependency-chain
 * showcase: the port bound says almost nothing, the simulated steady
 * state says everything.
 */
#include <immintrin.h>
#include <stdio.h>
#include <stdlib.h>

__attribute__((noinline)) double gather_sum(const double *values,
                                            const int *index, int n)
{
    __m256d acc = _mm256_setzero_pd();
    for (int i = 0; i < n; i += 4) {
        __m128i lanes = _mm_loadu_si128((const __m128i *)&index[i]);
        acc = _mm256_add_pd(acc, _mm256_i32gather_pd(values, lanes, 8));
    }
    double out[4];
    _mm256_storeu_pd(out, acc);
    return out[0] + out[1] + out[2] + out[3];
}

int main(void)
{
    enum { n = 4096 };
    double *values = malloc(n * sizeof *values);
    int *index = malloc(n * sizeof *index);
    for (int i = 0; i < n; i++) {
        values[i] = i * 0.25;
        index[i] = (i * 7) % n;
    }
    double acc = 0.0;
    for (int repetition = 0; repetition < 64; repetition++) {
        acc += gather_sum(values, index, n);
    }
    printf("acc %.17g\n", acc);
    free(values);
    free(index);
    return 0;
}
