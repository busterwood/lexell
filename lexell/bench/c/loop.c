/* The tight integer loop of bench/loop.lxl as plain C: s = s + i * 2 for
   i < n, with no overflow checks. Lexell's source has an overflow check on both
   operations; the native backend proves both cannot fail. This is the same
   loop gcc compiles without checks ("plain C", the lower bound).

   n comes from the command line, and the empty asm keeps s in a register
   across the iteration, so that gcc cannot replace the loop with its closed
   form or vectorise it: the row is about the cost of the iteration, and the
   lxl source executes it. */
#include <stdio.h>
#include <stdlib.h>

int main(int argc, char **argv) {
    long long n = argc > 1 ? atoll(argv[1]) : 2000000000LL;
    long long s = 0;
    for (long long i = 0; i < n; i++) {
        s = s + i * 2;
        __asm__ __volatile__("" : "+r"(s));
    }
    printf("%lld\n", s);
    return 0;
}
