/* The tokeniser benchmark of bench/tokens.obx as plain C: scan a source file
   into token records (identifiers keep their text, numbers and symbols do
   not), then intern every identifier in a 1,024-bucket hash table, ten
   rounds. Same scanner rules and the same djb2-style hash (& 0xFFFFFF), so
   the counts must match the obx program's. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
    int kind;
    char *text;
    int line;
} Token;

typedef struct {
    Token *items;
    size_t len, cap;
} Tokens;

static void push(Tokens *t, Token tok) {
    if (t->len == t->cap) {
        t->cap = t->cap ? t->cap * 2 : 256;
        t->items = realloc(t->items, t->cap * sizeof *t->items);
        if (!t->items) exit(1);
    }
    t->items[t->len++] = tok;
}

static int isLetter(int c) {
    return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || c == '_';
}

static int isDigit(int c) { return c >= '0' && c <= '9'; }

static void scan(const char *src, size_t len, Tokens *toks) {
    size_t i = 0;
    int line = 1;
    while (i < len) {
        int c = (unsigned char)src[i];
        if (c == '\n') {
            line++;
            i++;
        } else if (isLetter(c)) {
            size_t start = i;
            while (i < len && (isLetter((unsigned char)src[i]) || isDigit((unsigned char)src[i]))) i++;
            size_t n = i - start;
            char *text = malloc(n + 1);
            if (!text) exit(1);
            memcpy(text, src + start, n);
            text[n] = 0;
            push(toks, (Token){1, text, line});
        } else if (isDigit(c)) {
            while (i < len && isDigit((unsigned char)src[i])) i++;
            push(toks, (Token){2, NULL, line});
        } else if (c == ' ' || c == '\t') {
            i++;
        } else {
            push(toks, (Token){3, NULL, line});
            i++;
        }
    }
}

static int hash(const char *s) {
    unsigned h = 5381;
    for (const unsigned char *p = (const unsigned char *)s; *p; p++) h = (h * 33 + *p) & 0xFFFFFF;
    return (int)h;
}

typedef struct {
    char **items;
    size_t len, cap;
} Bucket;

static int intern(Bucket *table, char *s) {
    Bucket *b = &table[hash(s) % 1024];
    for (size_t i = 0; i < b->len; i++)
        if (strcmp(b->items[i], s) == 0) return 0;
    if (b->len == b->cap) {
        b->cap = b->cap ? b->cap * 2 : 8;
        b->items = realloc(b->items, b->cap * sizeof *b->items);
        if (!b->items) exit(1);
    }
    b->items[b->len++] = s;
    return 1;
}

int main(int argc, char **argv) {
    if (argc < 2) return 1;
    FILE *f = fopen(argv[1], "rb");
    if (!f) return 1;
    fseek(f, 0, SEEK_END);
    long n = ftell(f);
    fseek(f, 0, SEEK_SET);
    char *src = malloc(n ? (size_t)n : 1);
    if (!src) return 1;
    if (n && fread(src, 1, (size_t)n, f) != (size_t)n) return 1;
    fclose(f);

    long long tokens = 0, unique = 0;
    for (int round = 0; round < 200; round++) {
        Tokens toks = {0};
        scan(src, (size_t)n, &toks);
        Bucket table[1024] = {0};
        for (size_t i = 0; i < toks.len; i++) {
            if (toks.items[i].kind == 1 && intern(table, toks.items[i].text)) unique++;
        }
        tokens += (long long)toks.len;
        for (size_t i = 0; i < toks.len; i++) free(toks.items[i].text);
        free(toks.items);
        for (int b = 0; b < 1024; b++) free(table[b].items);
    }
    printf("%lld %lld\n", tokens, unique);
    free(src);
    return 0;
}
