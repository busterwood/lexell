/* The float dot product, hand-vectorised: 4 doubles per vector, 4 accumulators
   and 4x unrolling, FMA (design/simd.md, bench/simd/dot.lxl is the lxl source). */
#include <immintrin.h>
#include <stdio.h>
#include <stdlib.h>

int main(void) {
    const long n = 65536;
    double *a = malloc((size_t)n * sizeof *a);
    double *b = malloc((size_t)n * sizeof *b);
    if (!a || !b) return 1;
    for (long i = 0; i < n; i++) {
        a[i] = (double)i * 0.5;
        b[i] = (double)i * 0.25 + 1.0;
    }
    double total = 0.0;
    for (int r = 0; r < 4000; r++) {
        __m256d s0 = _mm256_setzero_pd(), s1 = s0, s2 = s0, s3 = s0;
        long i = 0;
        for (; i + 16 <= n; i += 16) {
            s0 = _mm256_fmadd_pd(_mm256_loadu_pd(a + i + 0), _mm256_loadu_pd(b + i + 0), s0);
            s1 = _mm256_fmadd_pd(_mm256_loadu_pd(a + i + 4), _mm256_loadu_pd(b + i + 4), s1);
            s2 = _mm256_fmadd_pd(_mm256_loadu_pd(a + i + 8), _mm256_loadu_pd(b + i + 8), s2);
            s3 = _mm256_fmadd_pd(_mm256_loadu_pd(a + i + 12), _mm256_loadu_pd(b + i + 12), s3);
        }
        __m256d s = _mm256_add_pd(_mm256_add_pd(s0, s1), _mm256_add_pd(s2, s3));
        for (; i < n; i++) s = _mm256_add_pd(s, _mm256_set1_pd(a[i] * b[i]));
        double lanes[4];
        _mm256_storeu_pd(lanes, s);
        total = total + lanes[0] + lanes[1] + lanes[2] + lanes[3];
    }
    printf("%.17g\n", total);
    free(a);
    free(b);
    return 0;
}
