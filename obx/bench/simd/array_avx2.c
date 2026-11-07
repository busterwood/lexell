/* bench/c/array.c, hand-vectorised: 4 x int64 per AVX2 vector. The integer
   sum is exact, so the output is identical. design/simd.md ceiling table. */
#include <immintrin.h>
#include <stdio.h>
#include <stdlib.h>

int main(void) {
    long long n = 1000000;
    long long *a = NULL;
    size_t len = 0, cap = 0;
    for (long long i = 0; i < n; i++) {
        if (len == cap) {
            cap = cap ? cap * 2 : 16;
            a = realloc(a, cap * sizeof *a);
            if (!a) return 1;
        }
        a[len++] = i;
    }
    long long total = 0;
    for (long long r = 0; r < 200; r++) {
        __m256i vr = _mm256_set1_epi64x(r);
        __m256i vs = _mm256_setzero_si256();
        long long i = 0;
        for (; i + 4 <= n; i += 4) {
            __m256i x = _mm256_loadu_si256((const __m256i *)(a + i));
            x = _mm256_add_epi64(x, vr);
            _mm256_storeu_si256((__m256i *)(a + i), x);
            vs = _mm256_add_epi64(vs, x);
        }
        long long lanes[4];
        _mm256_storeu_si256((__m256i *)lanes, vs);
        total += lanes[0] + lanes[1] + lanes[2] + lanes[3];
        for (; i < n; i++) {
            a[i] = a[i] + r;
            total = total + a[i];
        }
    }
    printf("%lld\n", total);
    free(a);
    return 0;
}
