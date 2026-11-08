/* Float dot product: s = sum a[i]*b[i], n = 65536, 4000 rounds.
   The same program as dot.lxl (bench/simd). Built -fno-tree-vectorize
   for the scalar row and -O2 -march=x86-64-v3 for the auto-vectorised row. */
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
        double s = 0.0;
        for (long i = 0; i < n; i++) s = s + a[i] * b[i];
        total = total + s;
    }
    printf("%.17g\n", total);
    free(a);
    free(b);
    return 0;
}
