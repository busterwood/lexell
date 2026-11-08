/* The binary-tree benchmark of bench/trees.lxl as plain C: build a tree of
   depth 16, then 400 trees of depth 14, walk each and free it. Same recursive
   build/check shape. */
#include <stdio.h>
#include <stdlib.h>

typedef struct Tree {
    struct Tree *left, *right;
} Tree;

static Tree *build(int d) {
    Tree *t = malloc(sizeof *t);
    if (!t) exit(1);
    if (d == 0) {
        t->left = t->right = NULL;
    } else {
        t->left = build(d - 1);
        t->right = build(d - 1);
    }
    return t;
}

static long long check(const Tree *t) {
    long long n = 1;
    if (t->left) n += check(t->left);
    if (t->right) n += check(t->right);
    return n;
}

static void drop(Tree *t) {
    if (!t) return;
    drop(t->left);
    drop(t->right);
    free(t);
}

int main(void) {
    Tree *long_tree = build(16);
    long long total = 0;
    for (long long i = 0; i < 400; i++) {
        Tree *t = build(14);
        total += check(t);
        drop(t);
    }
    printf("%lld\n", total + check(long_tree));
    drop(long_tree);
    return 0;
}
