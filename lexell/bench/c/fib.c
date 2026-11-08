/* Naive recursive fibonacci as plain C, for bench/fib.lxl: the same algorithm
   (no memoisation, two recursive calls per node) and the same call tree.
   n comes from the command line so that gcc cannot constant-fold the call
   tree, and the empty asm keeps the two calls from being turned into a loop;
   the row is about calls, not about gcc removing them. The Lexell program
   passes the same 42.

   Built by bench.py with gcc -O2 -fno-optimize-sibling-calls as the
   "plain C" column. */
#include <stdio.h>
#include <stdlib.h>

__attribute__((noinline)) static long long fib(long long n) {
    if (n < 2) return n;
    long long a = fib(n - 1);
    __asm__ __volatile__("" : "+r"(a) : : "memory");
    long long b = fib(n - 2);
    return a + b;
}

int main(int argc, char **argv) {
    long long n = argc > 1 ? atoll(argv[1]) : 42;
    printf("%lld\n", fib(n));
    return 0;
}
