/* The string benchmark of bench/strings.obx as plain C: the same
   left-to-right concatenations, allocating the intermediate string at every
   + ("word" + i, + "-", + round), and measuring the final strings. No
   StrBuf and no sharing: one allocation per concatenation, as in the obx
   source. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static char *concat(const char *a, const char *b) {
    size_t la = strlen(a), lb = strlen(b);
    char *r = malloc(la + lb + 1);
    if (!r) exit(1);
    memcpy(r, a, la);
    memcpy(r + la, b, lb + 1);
    return r;
}

static char *intToStr(long long v) {
    char buf[32];
    snprintf(buf, sizeof buf, "%lld", v);
    size_t n = strlen(buf) + 1;
    char *r = malloc(n);
    if (!r) exit(1);
    memcpy(r, buf, n);
    return r;
}

int main(void) {
    char *keep[1000];
    for (long long i = 0; i < 1000; i++) {
        char *n = intToStr(i);
        keep[i] = concat("k", n);
        free(n);
    }
    long long total = 0;
    for (long long round = 0; round < 1000; round++) {
        char *words[5000];
        char *rs = intToStr(round);
        for (long long i = 0; i < 5000; i++) {
            char *n = intToStr(i);
            char *w = concat("word", n);
            free(n);
            char *w2 = concat(w, "-");
            free(w);
            words[i] = concat(w2, rs);
            free(w2);
        }
        for (long long i = 0; i < 5000; i++) {
            total += (long long)strlen(words[i]);
            free(words[i]);
        }
        free(rs);
    }
    for (long long i = 0; i < 1000; i++) free(keep[i]);
    printf("%lld\n", total);
    return 0;
}
