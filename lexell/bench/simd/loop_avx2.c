/* bench/c/loop.c, hand-vectorised: 4 int64 lanes accumulate 2*i for four i at
   a time (design/simd.md); the empty asm keeps the accumulator in a ymm register across the
   iteration, as loop.c keeps s in a GPR, so gcc cannot use a closed form. */
#include <immintrin.h>
#include <stdio.h>
#include <stdlib.h>

int main(int argc, char **argv) {
    long long n = argc > 1 ? atoll(argv[1]) : 1000000000LL;
    __m256i acc = _mm256_setzero_si256();
    __m256i step = _mm256_set_epi64x(6, 4, 2, 0);   /* 2*i for i = 0..3 */
    __m256i bump = _mm256_set1_epi64x(8);           /* next four i, times 2 */
    long long i = 0;
    for (; i + 4 <= n; i += 4) {
        acc = _mm256_add_epi64(acc, step);
        step = _mm256_add_epi64(step, bump);
        __asm__ __volatile__("" : "+x"(acc));
    }
    long long lanes[4];
    _mm256_storeu_si256((__m256i *)lanes, acc);
    long long s = lanes[0] + lanes[1] + lanes[2] + lanes[3];
    for (; i < n; i++) {
        s = s + i * 2;
        __asm__ __volatile__("" : "+r"(s));
    }
    printf("%lld\n", s);
    return 0;
}
