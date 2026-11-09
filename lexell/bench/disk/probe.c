// Flush and 4 KB random-read latency of the filesystem under <dir>: the numbers
// behind lexell/design/lexdb.md section 3. It writes and deletes two files in <dir>
// (the second is <MiB> large; make it larger than the host's cache).
//
//   gcc -O2 -o /tmp/disk_probe lexell/bench/disk/probe.c -lpthread
//   /tmp/disk_probe <dir> 4096
#define _GNU_SOURCE
#include <fcntl.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

static double now_us(void) {
    struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec * 1e6 + t.tv_nsec / 1e3;
}
static int cmp(const void* a, const void* b) {
    double x = *(const double*)a, y = *(const double*)b; return x < y ? -1 : x > y;
}
#define CHECK(x) do { if ((x) < 0) { perror(#x); exit(1); } } while (0)

static void report(const char* name, double* v, int n) {
    qsort(v, n, sizeof *v, cmp);
    double s = 0; for (int i = 0; i < n; i++) s += v[i];
    printf("%-44s n=%5d  mean %8.1f  p50 %8.1f  p99 %8.1f  max %9.1f us\n",
           name, n, s / n, v[n / 2], v[n * 99 / 100], v[n - 1]);
}

static char path[4096];
static long nblocks;
static int nthreads_iops;
static volatile int stop;
static long counts[64];

static void* reader(void* arg) {
    long id = (long)arg;
    int fd = open(path, O_RDONLY | O_DIRECT);
    void* buf; if (posix_memalign(&buf, 4096, 4096)) exit(1);
    unsigned s = 12345 + id * 7919;
    long c = 0;
    while (!stop) {
        s = s * 1103515245u + 12345u;
        long b = (long)(((unsigned long)s * 2654435761ul) % (unsigned long)nblocks);
        if (pread(fd, buf, 4096, b * 4096) != 4096) { perror("pread"); exit(1); }
        c++;
    }
    counts[id] = c; close(fd); free(buf); return NULL;
}

int main(int argc, char** argv) {
    if (argc < 3) { fprintf(stderr, "usage: %s dir MiB\n", argv[0]); return 2; }
    long mib = atol(argv[2]);
    nblocks = mib * 256;
    void* buf; if (posix_memalign(&buf, 4096, 1 << 20)) return 1;
    memset(buf, 0xA5, 1 << 20);
    enum { N = 2000 };
    static double v[N];

    // 1. buffered 4 KB append + fdatasync (WAL commit, file grows)
    snprintf(path, sizeof path, "%s/wal_append.dat", argv[1]);
    int fd = open(path, O_CREAT | O_TRUNC | O_WRONLY, 0644);
    for (int i = 0; i < N; i++) {
        double t = now_us();
        CHECK(write(fd, buf, 4096)); CHECK(fdatasync(fd));
        v[i] = now_us() - t;
    }
    report("append 4K + fdatasync (growing file)", v, N);
    close(fd);

    // 2. overwrite in a preallocated file + fdatasync (reused WAL segment)
    fd = open(path, O_WRONLY);
    for (int i = 0; i < N; i++) {
        double t = now_us();
        CHECK(pwrite(fd, buf, 4096, (off_t)i * 4096)); CHECK(fdatasync(fd));
        v[i] = now_us() - t;
    }
    report("pwrite 4K preallocated + fdatasync", v, N);

    // 3. 64 KB group + fdatasync
    for (int i = 0; i < N / 4; i++) {
        double t = now_us();
        CHECK(pwrite(fd, buf, 65536, (off_t)(i % 100) * 65536)); CHECK(fdatasync(fd));
        v[i] = now_us() - t;
    }
    report("pwrite 64K preallocated + fdatasync", v, N / 4);
    close(fd);

    // 4. O_DIRECT | O_DSYNC 4 KB writes, preallocated
    fd = open(path, O_WRONLY | O_DIRECT | O_DSYNC);
    for (int i = 0; i < N; i++) {
        double t = now_us();
        if (pwrite(fd, buf, 4096, (off_t)i * 4096) != 4096) { perror("odirect"); break; }
        v[i] = now_us() - t;
    }
    report("O_DIRECT|O_DSYNC pwrite 4K", v, N);
    close(fd);
    unlink(path);

    // 5. random 4 KB O_DIRECT reads, QD1 and parallel
    snprintf(path, sizeof path, "%s/pages.dat", argv[1]);
    fd = open(path, O_CREAT | O_TRUNC | O_WRONLY, 0644);
    for (long i = 0; i < mib; i++) {
        for (int j = 0; j < (1 << 20); j += 8) *(uint64_t*)((char*)buf + j) = i * 1315423911u + j;
        CHECK(write(fd, buf, 1 << 20));
    }
    fsync(fd); close(fd);
    fd = open(path, O_RDONLY | O_DIRECT);
    unsigned s = 1;
    for (int i = 0; i < N; i++) {
        s = s * 1103515245u + 12345u;
        long b = (long)(((unsigned long)s * 2654435761ul) % (unsigned long)nblocks);
        double t = now_us();
        CHECK(pread(fd, buf, 4096, b * 4096));
        v[i] = now_us() - t;
    }
    report("O_DIRECT random read 4K, QD1", v, N);
    close(fd);
    int qds[] = {4, 16, 32};
    for (int q = 0; q < 3; q++) {
        nthreads_iops = qds[q]; stop = 0;
        pthread_t th[64];
        for (long i = 0; i < nthreads_iops; i++) pthread_create(&th[i], NULL, reader, (void*)i);
        usleep(2000000); stop = 1;
        long tot = 0;
        for (int i = 0; i < nthreads_iops; i++) { pthread_join(th[i], NULL); tot += counts[i]; }
        printf("O_DIRECT random read 4K, %2d threads: %8.0f IOPS\n", nthreads_iops, tot / 2.0);
    }
    unlink(path);
    return 0;
}
