/* The float dot product through the hand-written x64gen instruction sequence
   (dot_kernels.s), same data and rounds as dot.c. */
#include <stdio.h>
#include <stdlib.h>

double dot_obx_check1(const double *a, const double *b, long n);
double dot_obx_check4(const double *a, const double *b, long n);
double dot_obx_check8(const double *a, const double *b, long n);

int main(int argc, char **argv) {
    const long n = 65536;
    const int which = argc > 1 ? atoi(argv[1]) : 4;
    double *a = malloc((size_t)n * sizeof *a);
    double *b = malloc((size_t)n * sizeof *b);
    if (!a || !b) return 1;
    for (long i = 0; i < n; i++) {
        a[i] = (double)i * 0.5;
        b[i] = (double)i * 0.25 + 1.0;
    }
    double total = 0.0;
    for (int r = 0; r < 4000; r++) {
        double s = which == 1 ? dot_obx_check1(a, b, n)
                 : which == 8 ? dot_obx_check8(a, b, n)
                              : dot_obx_check4(a, b, n);
        total = total + s;
    }
    printf("%.17g\n", total);
    free(a);
    free(b);
    return 0;
}
