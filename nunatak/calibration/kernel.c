/* Calibration microbenchmarks: what this Machine can actually reach.
 *
 * Runs as an autonomous process: measuring an upper bound from inside a
 * resident interpreter, its allocator and its garbage collector would
 * pollute exactly the quantity being measured. Three kernels:
 *
 *   triad    a[i] = b[i] + s * c[i] over arrays far larger than the
 *            last-level cache: sustained memory bandwidth in byte/s.
 *   fma_dp   independent FMA chains on the widest SIMD registers the
 *            build knows: double-precision peak in flop/s.
 *   fma_sp   the same in single precision.
 *
 * The FMA kernels are written in intrinsics because a portable C peak is
 * at the mercy of the compiler's choices; the build reports the ISA it
 * was compiled for, and a scalar build is announced as such rather than
 * passed off as a peak. The load average travels in the output for the
 * same reason: pollution signals must reach the caller through the same
 * channel as the values, so a replayed calibration stays deterministic.
 *
 * Usage: kernel <triad|fma_dp|fma_sp> <threads> <repetitions> <ms/rep>
 * Output, one datum per line:
 *   kernel <name> / isa <isa> / threads <n> / load <loadavg|-1>
 *   rep <i> <rate in unit/s>
 */

#define _GNU_SOURCE
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#if defined(__x86_64__)
#include <immintrin.h>
#elif defined(__aarch64__)
#include <arm_neon.h>
#endif

static double now(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + (double)ts.tv_nsec * 1e-9;
}

/* ---- FMA chains: eight independent accumulators keep every FMA port
 * busy past the instruction latency. Returns FLOPs done. ---- */

#if defined(__AVX512F__)
#define ISA "avx512"
static double fma_dp_chunk(uint64_t inner) {
    __m512d a0, a1, a2, a3, a4, a5, a6, a7;
    a0 = a1 = a2 = a3 = a4 = a5 = a6 = a7 = _mm512_set1_pd(1.0);
    const __m512d m = _mm512_set1_pd(1.0 + 1e-9), c = _mm512_set1_pd(1e-9);
    for (uint64_t i = 0; i < inner; i++) {
        a0 = _mm512_fmadd_pd(a0, m, c); a1 = _mm512_fmadd_pd(a1, m, c);
        a2 = _mm512_fmadd_pd(a2, m, c); a3 = _mm512_fmadd_pd(a3, m, c);
        a4 = _mm512_fmadd_pd(a4, m, c); a5 = _mm512_fmadd_pd(a5, m, c);
        a6 = _mm512_fmadd_pd(a6, m, c); a7 = _mm512_fmadd_pd(a7, m, c);
    }
    double sink[8];
    _mm512_storeu_pd(sink, _mm512_add_pd(_mm512_add_pd(a0, a1),
        _mm512_add_pd(_mm512_add_pd(a2, a3),
        _mm512_add_pd(_mm512_add_pd(a4, a5), _mm512_add_pd(a6, a7)))));
    volatile double keep = sink[0]; (void)keep;
    return (double)inner * 8 * 8 * 2;
}
static double fma_sp_chunk(uint64_t inner) {
    __m512 a0, a1, a2, a3, a4, a5, a6, a7;
    a0 = a1 = a2 = a3 = a4 = a5 = a6 = a7 = _mm512_set1_ps(1.0f);
    const __m512 m = _mm512_set1_ps(1.0f + 1e-7f), c = _mm512_set1_ps(1e-7f);
    for (uint64_t i = 0; i < inner; i++) {
        a0 = _mm512_fmadd_ps(a0, m, c); a1 = _mm512_fmadd_ps(a1, m, c);
        a2 = _mm512_fmadd_ps(a2, m, c); a3 = _mm512_fmadd_ps(a3, m, c);
        a4 = _mm512_fmadd_ps(a4, m, c); a5 = _mm512_fmadd_ps(a5, m, c);
        a6 = _mm512_fmadd_ps(a6, m, c); a7 = _mm512_fmadd_ps(a7, m, c);
    }
    float sink[16];
    _mm512_storeu_ps(sink, _mm512_add_ps(_mm512_add_ps(a0, a1),
        _mm512_add_ps(_mm512_add_ps(a2, a3),
        _mm512_add_ps(_mm512_add_ps(a4, a5), _mm512_add_ps(a6, a7)))));
    volatile float keep = sink[0]; (void)keep;
    return (double)inner * 8 * 16 * 2;
}
#elif defined(__AVX2__) && defined(__FMA__)
#define ISA "avx2"
static double fma_dp_chunk(uint64_t inner) {
    __m256d a0, a1, a2, a3, a4, a5, a6, a7;
    a0 = a1 = a2 = a3 = a4 = a5 = a6 = a7 = _mm256_set1_pd(1.0);
    const __m256d m = _mm256_set1_pd(1.0 + 1e-9), c = _mm256_set1_pd(1e-9);
    for (uint64_t i = 0; i < inner; i++) {
        a0 = _mm256_fmadd_pd(a0, m, c); a1 = _mm256_fmadd_pd(a1, m, c);
        a2 = _mm256_fmadd_pd(a2, m, c); a3 = _mm256_fmadd_pd(a3, m, c);
        a4 = _mm256_fmadd_pd(a4, m, c); a5 = _mm256_fmadd_pd(a5, m, c);
        a6 = _mm256_fmadd_pd(a6, m, c); a7 = _mm256_fmadd_pd(a7, m, c);
    }
    double sink[4];
    _mm256_storeu_pd(sink, _mm256_add_pd(_mm256_add_pd(a0, a1),
        _mm256_add_pd(_mm256_add_pd(a2, a3),
        _mm256_add_pd(_mm256_add_pd(a4, a5), _mm256_add_pd(a6, a7)))));
    volatile double keep = sink[0]; (void)keep;
    return (double)inner * 8 * 4 * 2;
}
static double fma_sp_chunk(uint64_t inner) {
    __m256 a0, a1, a2, a3, a4, a5, a6, a7;
    a0 = a1 = a2 = a3 = a4 = a5 = a6 = a7 = _mm256_set1_ps(1.0f);
    const __m256 m = _mm256_set1_ps(1.0f + 1e-7f), c = _mm256_set1_ps(1e-7f);
    for (uint64_t i = 0; i < inner; i++) {
        a0 = _mm256_fmadd_ps(a0, m, c); a1 = _mm256_fmadd_ps(a1, m, c);
        a2 = _mm256_fmadd_ps(a2, m, c); a3 = _mm256_fmadd_ps(a3, m, c);
        a4 = _mm256_fmadd_ps(a4, m, c); a5 = _mm256_fmadd_ps(a5, m, c);
        a6 = _mm256_fmadd_ps(a6, m, c); a7 = _mm256_fmadd_ps(a7, m, c);
    }
    float sink[8];
    _mm256_storeu_ps(sink, _mm256_add_ps(_mm256_add_ps(a0, a1),
        _mm256_add_ps(_mm256_add_ps(a2, a3),
        _mm256_add_ps(_mm256_add_ps(a4, a5), _mm256_add_ps(a6, a7)))));
    volatile float keep = sink[0]; (void)keep;
    return (double)inner * 8 * 8 * 2;
}
#elif defined(__aarch64__)
#define ISA "neon"
static double fma_dp_chunk(uint64_t inner) {
    float64x2_t a0, a1, a2, a3, a4, a5, a6, a7;
    a0 = a1 = a2 = a3 = a4 = a5 = a6 = a7 = vdupq_n_f64(1.0);
    const float64x2_t m = vdupq_n_f64(1.0 + 1e-9), c = vdupq_n_f64(1e-9);
    for (uint64_t i = 0; i < inner; i++) {
        a0 = vfmaq_f64(c, a0, m); a1 = vfmaq_f64(c, a1, m);
        a2 = vfmaq_f64(c, a2, m); a3 = vfmaq_f64(c, a3, m);
        a4 = vfmaq_f64(c, a4, m); a5 = vfmaq_f64(c, a5, m);
        a6 = vfmaq_f64(c, a6, m); a7 = vfmaq_f64(c, a7, m);
    }
    volatile double keep = vgetq_lane_f64(
        vaddq_f64(vaddq_f64(vaddq_f64(a0, a1), vaddq_f64(a2, a3)),
                  vaddq_f64(vaddq_f64(a4, a5), vaddq_f64(a6, a7))), 0);
    (void)keep;
    return (double)inner * 8 * 2 * 2;
}
static double fma_sp_chunk(uint64_t inner) {
    float32x4_t a0, a1, a2, a3, a4, a5, a6, a7;
    a0 = a1 = a2 = a3 = a4 = a5 = a6 = a7 = vdupq_n_f32(1.0f);
    const float32x4_t m = vdupq_n_f32(1.0f + 1e-7f), c = vdupq_n_f32(1e-7f);
    for (uint64_t i = 0; i < inner; i++) {
        a0 = vfmaq_f32(c, a0, m); a1 = vfmaq_f32(c, a1, m);
        a2 = vfmaq_f32(c, a2, m); a3 = vfmaq_f32(c, a3, m);
        a4 = vfmaq_f32(c, a4, m); a5 = vfmaq_f32(c, a5, m);
        a6 = vfmaq_f32(c, a6, m); a7 = vfmaq_f32(c, a7, m);
    }
    volatile float keep = vgetq_lane_f32(
        vaddq_f32(vaddq_f32(vaddq_f32(a0, a1), vaddq_f32(a2, a3)),
                  vaddq_f32(vaddq_f32(a4, a5), vaddq_f32(a6, a7))), 0);
    (void)keep;
    return (double)inner * 8 * 4 * 2;
}
#else
#define ISA "scalar"
static double fma_dp_chunk(uint64_t inner) {
    double a0 = 1, a1 = 1, a2 = 1, a3 = 1;
    const double m = 1.0 + 1e-9, c = 1e-9;
    for (uint64_t i = 0; i < inner; i++) {
        a0 = a0 * m + c; a1 = a1 * m + c; a2 = a2 * m + c; a3 = a3 * m + c;
    }
    volatile double keep = a0 + a1 + a2 + a3; (void)keep;
    return (double)inner * 4 * 2;
}
static double fma_sp_chunk(uint64_t inner) {
    float a0 = 1, a1 = 1, a2 = 1, a3 = 1;
    const float m = 1.0f + 1e-7f, c = 1e-7f;
    for (uint64_t i = 0; i < inner; i++) {
        a0 = a0 * m + c; a1 = a1 * m + c; a2 = a2 * m + c; a3 = a3 * m + c;
    }
    volatile float keep = a0 + a1 + a2 + a3; (void)keep;
    return (double)inner * 4 * 2;
}
#endif

/* ---- triad: sustained bandwidth over arrays sized to dwarf any
 * last-level cache - an EPYC carries up to hundreds of MiB of L3, and a
 * triad fitting in it would measure cache, not DRAM. An eighth of the
 * physical memory, clamped to [768 MiB, 6 GiB] in total. ---- */

static size_t triad_elements;
static double *triad_a, *triad_b, *triad_c;

static size_t sized_from_memory(void) {
    long pages = sysconf(_SC_PHYS_PAGES), page = sysconf(_SC_PAGE_SIZE);
    double bytes = pages > 0 && page > 0 ? (double)pages * (double)page / 8.0
                                         : 0.0;
    const double floor_ = 768.0 * 1048576.0, cap = 6144.0 * 1048576.0;
    if (bytes < floor_)
        bytes = floor_;
    if (bytes > cap)
        bytes = cap;
    return (size_t)(bytes / 3.0 / sizeof(double));
}

static double triad_chunk(size_t begin, size_t end) {
    const double s = 3.0;
    for (size_t i = begin; i < end; i++)
        triad_a[i] = triad_b[i] + s * triad_c[i];
    /* 3 x 8 bytes actually move per element (STREAM's accounting). */
    return (double)(end - begin) * 24.0;
}

/* ---- threading: each worker loops chunks until the deadline; the rate
 * is total work over the wall time of the slowest worker. ---- */

struct worker {
    pthread_t thread;
    const char *kernel;
    int index, threads;
    double deadline, work;
};

static void *worker_main(void *argument) {
    struct worker *w = (struct worker *)argument;
    double work = 0.0;
    if (strcmp(w->kernel, "triad") == 0) {
        size_t slice = triad_elements / (size_t)w->threads;
        size_t begin = slice * (size_t)w->index;
        size_t end = w->index == w->threads - 1 ? triad_elements : begin + slice;
        while (now() < w->deadline)
            work += triad_chunk(begin, end);
    } else {
        double (*chunk)(uint64_t) =
            strcmp(w->kernel, "fma_sp") == 0 ? fma_sp_chunk : fma_dp_chunk;
        while (now() < w->deadline)
            work += chunk(200000);
    }
    w->work = work;
    return NULL;
}

static double repetition(const char *kernel, int threads, double seconds) {
    struct worker *workers = calloc((size_t)threads, sizeof(*workers));
    double start = now();
    for (int i = 0; i < threads; i++) {
        workers[i] = (struct worker){.kernel = kernel, .index = i,
                                     .threads = threads,
                                     .deadline = start + seconds};
        pthread_create(&workers[i].thread, NULL, worker_main, &workers[i]);
    }
    double work = 0.0;
    for (int i = 0; i < threads; i++) {
        pthread_join(workers[i].thread, NULL);
        work += workers[i].work;
    }
    double elapsed = now() - start;
    free(workers);
    return work / elapsed;
}

static double load_average(void) {
    double load[1];
    if (getloadavg(load, 1) != 1)
        return -1.0;
    return load[0];
}

int main(int argc, char **argv) {
    if (argc != 5) {
        fprintf(stderr,
                "usage: kernel <triad|fma_dp|fma_sp> <threads> <reps> <ms>\n");
        return 2;
    }
    const char *kernel = argv[1];
    int threads = atoi(argv[2]);
    int repetitions = atoi(argv[3]);
    double seconds = atof(argv[4]) / 1000.0;
    if (threads < 1 || repetitions < 1 || seconds <= 0 ||
        (strcmp(kernel, "triad") != 0 && strcmp(kernel, "fma_dp") != 0 &&
         strcmp(kernel, "fma_sp") != 0)) {
        fprintf(stderr, "kernel: invalid arguments\n");
        return 2;
    }
    if (strcmp(kernel, "triad") == 0) {
        triad_elements = sized_from_memory();
        triad_a = malloc(triad_elements * sizeof(double));
        triad_b = malloc(triad_elements * sizeof(double));
        triad_c = malloc(triad_elements * sizeof(double));
        if (triad_a == NULL || triad_b == NULL || triad_c == NULL) {
            fprintf(stderr, "kernel: triad arrays do not fit in memory\n");
            return 3;
        }
        for (size_t i = 0; i < triad_elements; i++) {
            triad_a[i] = 0.0;
            triad_b[i] = 1.0;
            triad_c[i] = 2.0;
        }
    }
    printf("kernel %s\n", kernel);
    printf("isa %s\n", ISA);
    printf("threads %d\n", threads);
    printf("load %.2f\n", load_average());
    if (strcmp(kernel, "triad") == 0)
        printf("bytes %zu\n", triad_elements * 3 * sizeof(double));
    for (int i = 0; i < repetitions; i++)
        printf("rep %d %.6e\n", i, repetition(kernel, threads, seconds));
    return 0;
}
