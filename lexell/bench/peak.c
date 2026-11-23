/* peak CMD ARGS...: runs CMD and prints its peak resident memory in KB to stderr ("peak N", the
   child's ru_maxrss). bench.py builds it static: the kernel counts a child's peak from the
   process it was forked from, and a forked Python would add its own ~10 MB to every figure. */
#include <stdio.h>
#include <sys/resource.h>
#include <sys/wait.h>
#include <unistd.h>
int main(int argc, char** argv) {
    pid_t p = fork();
    if (p == 0) { execvp(argv[1], argv + 1); _exit(127); }
    int st; struct rusage ru;
    wait4(p, &st, 0, &ru);
    fprintf(stderr, "peak %ld\n", ru.ru_maxrss);
    return WIFEXITED(st) ? WEXITSTATUS(st) : 1;
}
