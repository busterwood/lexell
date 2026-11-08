/* bench/c/sieve.c, hand-vectorised where it can be (design/simd.md): the final counting loop
   sums 32 flag bytes per AVX2 vector with sad_epu8. The marking loop stays
   scalar: its stores are strided by the prime and AVX2 has no scatter. */
#include <immintrin.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(void) {
    long n = 10000000;
    long count = 0;
    for (int round = 0; round < 10; round++) {
        bool *prime = malloc(n + 1);
        if (!prime) return 1;
        memset(prime, true, n + 1);
        prime[0] = false;
        prime[1] = false;
        for (long i = 2; i * i <= n; i++) {
            if (prime[i]) {
                for (long j = i * i; j <= n; j += i) prime[j] = false;
            }
        }
        __m256i ones = _mm256_set1_epi8(1);
        __m256i zero = _mm256_setzero_si256();
        __m256i sums = zero;
        long k = 0;
        for (; k + 32 <= n + 1; k += 32) {
            __m256i v = _mm256_loadu_si256((const __m256i *)(prime + k));
            sums = _mm256_add_epi64(sums, _mm256_sad_epu8(_mm256_and_si256(v, ones), zero));
        }
        long long lanes[4];
        _mm256_storeu_si256((__m256i *)lanes, sums);
        count = lanes[0] + lanes[1] + lanes[2] + lanes[3];
        for (; k <= n; k++)
            if (prime[k]) count++;
        free(prime);
    }
    printf("%ld\n", count);
    return 0;
}
