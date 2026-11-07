/* The allocation benchmark of bench/alloc.obx as plain C: 20 million records
   allocated, read and freed. The calls go through volatile pointers so that
   gcc -O2 cannot fold the allocation away; the point of the row is the
   allocator, not the arithmetic. Same record, same loop. */
#include <stdio.h>
#include <stdlib.h>

typedef struct {
    long long v, w;
} Cell;

static void *(*volatile alloc_fn)(size_t) = malloc;
static void (*volatile free_fn)(void *) = free;

int main(void) {
    long long n = 80000000;
    long long total = 0;
    for (long long i = 0; i < n; i++) {
        Cell *c = alloc_fn(sizeof *c);
        if (!c) return 1;
        c->v = i;
        c->w = 2;
        total = total + c->v + c->w;
        free_fn(c);
    }
    printf("%lld\n", total);
    return 0;
}
