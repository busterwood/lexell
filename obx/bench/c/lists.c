/* The linked-list benchmark of bench/lists.obx as plain C: build a list by
   pushing on the front, sum it by recursion, free it when the variable is
   reassigned. Same 1,000-node list kept, 2000 rounds of 10,000 nodes. */
#include <stdio.h>
#include <stdlib.h>

typedef struct Node {
    long long value;
    struct Node *next;
} Node;

static Node *push(Node *list, long long v) {
    Node *n = malloc(sizeof *n);
    if (!n) exit(1);
    n->value = v;
    n->next = list;
    return n;
}

static long long sum(const Node *n) {
    if (!n) return 0;
    return n->value + sum(n->next);
}

static void drop(Node *n) {
    while (n) {
        Node *next = n->next;
        free(n);
        n = next;
    }
}

int main(void) {
    Node *keep = NULL;
    for (long long i = 0; i < 1000; i++) keep = push(keep, i);
    long long total = 0;
    for (long long round = 0; round < 2000; round++) {
        Node *l = NULL;
        for (long long i = 0; i < 10000; i++) l = push(l, i);
        total += sum(l) % 7;
        drop(l);
    }
    printf("%lld\n", total + sum(keep));
    drop(keep);
    return 0;
}
