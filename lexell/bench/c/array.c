/* The array benchmark of bench/array.lxl as plain C: a growing array filled
   with 0..n-1, then 800 rounds of a[i] = a[i] + r and total += a[i], with no
   bounds checks. Same work, same loop order. */
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
    for (long long r = 0; r < 800; r++) {
        for (long long i = 0; i < n; i++) {
            a[i] = a[i] + r;
            total = total + a[i];
        }
    }
    printf("%lld\n", total);
    free(a);
    return 0;
}
