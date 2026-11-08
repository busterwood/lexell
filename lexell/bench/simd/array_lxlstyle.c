/* The int64 array loop through the instruction sequence the proposed extension
   would emit for

       while i + 4 <= n { let v = vload(&a, i); vstore(mut &a, i, v +% vr); acc = acc +% v; i += 4 }

   one vmovdqu load, one vpaddq with the broadcast r, one store, one accumulating
   vpaddq and (in the checked variant) one bounds check per four elements. The
   scalar tail and the outer 200 rounds are the same as bench/c/array.c.
   argv[1] selects "check" or "nocheck". */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

long array_round_check(long *a, long n, long r);
long array_round_nocheck(long *a, long n, long r);

int main(int argc, char **argv) {
    long n = 1000000;
    int check = argc > 1 && strcmp(argv[1], "nocheck") != 0;
    long *a = NULL;
    size_t len = 0, cap = 0;
    for (long i = 0; i < n; i++) {
        if (len == cap) {
            cap = cap ? cap * 2 : 16;
            a = realloc(a, cap * sizeof *a);
            if (!a) return 1;
        }
        a[len++] = i;
    }
    long long total = 0;
    for (long r = 0; r < 200; r++)
        total += check ? array_round_check(a, n, r) : array_round_nocheck(a, n, r);
    printf("%lld\n", total);
    free(a);
    return 0;
}
