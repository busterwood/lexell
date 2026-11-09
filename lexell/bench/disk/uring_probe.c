// io_uring against a thread pool for lexdb's file I/O: 4 KiB O_DIRECT
// random reads (IOPS, latency, CPU per read), and 4 KiB write + fdatasync.
// No liburing: the three system calls and the rings by hand.
// usage: uring_probe <file> <MiB> <seconds per test>
#define _GNU_SOURCE
#include <fcntl.h>
#include <linux/io_uring.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/resource.h>
#include <sys/syscall.h>
#include <time.h>
#include <unistd.h>

static double now_us(void) {
    struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec * 1e6 + t.tv_nsec / 1e3;
}
static double cpu_us(void) {
    struct rusage r; getrusage(RUSAGE_SELF, &r);
    return r.ru_utime.tv_sec * 1e6 + r.ru_utime.tv_usec + r.ru_stime.tv_sec * 1e6 + r.ru_stime.tv_usec;
}
static int cmpd(const void* a, const void* b) { double x = *(const double*)a, y = *(const double*)b; return x < y ? -1 : x > y; }

static char* path; static long nblocks; static double secs;
static unsigned long rnd(unsigned long* s) { *s = *s * 6364136223846793005UL + 1442695040888963407UL; return *s >> 17; }

static void report(const char* name, long ops, double wall, double cpu, double* lat, long nlat) {
    qsort(lat, nlat, sizeof *lat, cmpd);
    printf("%-34s %8.0f IOPS  p50 %7.1f  p99 %7.1f us  CPU %5.1f us/op\n", name, ops / (wall / 1e6),
           lat[nlat / 2], lat[nlat * 99 / 100], cpu / ops);
}

// ---- the thread pool: n threads, each pread one at a time
static volatile int stop; static long tcount[64]; static double* tlat[64]; static long tnlat[64];
static void* reader(void* a) {
    long id = (long)a; int fd = open(path, O_RDONLY | O_DIRECT);
    void* buf; if (posix_memalign(&buf, 4096, 4096)) exit(1);
    unsigned long s = 99 + id * 7919; long c = 0;
    while (!stop) {
        double t0 = now_us();
        if (pread(fd, buf, 4096, (long)(rnd(&s) % nblocks) * 4096) != 4096) { perror("pread"); exit(1); }
        if (tnlat[id] < 2000000) tlat[id][tnlat[id]++] = now_us() - t0;
        c++;
    }
    tcount[id] = c; close(fd); free(buf); return 0;
}
static void pool(int n) {
    pthread_t th[64]; stop = 0;
    for (int i = 0; i < n; i++) { tlat[i] = malloc(sizeof(double) * 2000000); tnlat[i] = 0; }
    double c0 = cpu_us(), w0 = now_us();
    for (long i = 0; i < n; i++) pthread_create(&th[i], 0, reader, (void*)i);
    usleep((useconds_t)(secs * 1e6)); stop = 1;
    long ops = 0, nl = 0;
    for (int i = 0; i < n; i++) { pthread_join(th[i], 0); ops += tcount[i]; nl += tnlat[i]; }
    double w = now_us() - w0, c = cpu_us() - c0;
    double* all = malloc(sizeof(double) * nl); long k = 0;
    for (int i = 0; i < n; i++) { memcpy(all + k, tlat[i], sizeof(double) * tnlat[i]); k += tnlat[i]; free(tlat[i]); }
    char name[64]; snprintf(name, sizeof name, "pool, %d threads", n);
    report(name, ops, w, c, all, nl); free(all);
}

// ---- io_uring by hand
struct ring {
    int fd; unsigned *sq_head, *sq_tail, *sq_mask, *sq_array, *cq_head, *cq_tail, *cq_mask;
    struct io_uring_sqe* sqes; struct io_uring_cqe* cqes;
};
static int ring_init(struct ring* r, unsigned entries) {
    struct io_uring_params p; memset(&p, 0, sizeof p);
    r->fd = (int)syscall(__NR_io_uring_setup, entries, &p);
    if (r->fd < 0) { perror("io_uring_setup"); return -1; }
    size_t sqsz = p.sq_off.array + p.sq_entries * sizeof(unsigned);
    size_t cqsz = p.cq_off.cqes + p.cq_entries * sizeof(struct io_uring_cqe);
    char* sq = mmap(0, sqsz, PROT_READ | PROT_WRITE, MAP_SHARED | MAP_POPULATE, r->fd, IORING_OFF_SQ_RING);
    char* cq = (p.features & IORING_FEAT_SINGLE_MMAP) ? sq :
               mmap(0, cqsz, PROT_READ | PROT_WRITE, MAP_SHARED | MAP_POPULATE, r->fd, IORING_OFF_CQ_RING);
    if (p.features & IORING_FEAT_SINGLE_MMAP && cqsz > sqsz) {
        munmap(sq, sqsz);
        sq = cq = mmap(0, cqsz, PROT_READ | PROT_WRITE, MAP_SHARED | MAP_POPULATE, r->fd, IORING_OFF_SQ_RING);
    }
    r->sqes = mmap(0, p.sq_entries * sizeof(struct io_uring_sqe), PROT_READ | PROT_WRITE, MAP_SHARED | MAP_POPULATE, r->fd, IORING_OFF_SQES);
    r->sq_head = (unsigned*)(sq + p.sq_off.head); r->sq_tail = (unsigned*)(sq + p.sq_off.tail);
    r->sq_mask = (unsigned*)(sq + p.sq_off.ring_mask); r->sq_array = (unsigned*)(sq + p.sq_off.array);
    r->cq_head = (unsigned*)(cq + p.cq_off.head); r->cq_tail = (unsigned*)(cq + p.cq_off.tail);
    r->cq_mask = (unsigned*)(cq + p.cq_off.ring_mask); r->cqes = (struct io_uring_cqe*)(cq + p.cq_off.cqes);
    return 0;
}
static struct io_uring_sqe* sqe_get(struct ring* r) {
    unsigned tail = *r->sq_tail, i = tail & *r->sq_mask;
    r->sq_array[i] = i; struct io_uring_sqe* e = &r->sqes[i]; memset(e, 0, sizeof *e);
    __atomic_store_n(r->sq_tail, tail + 1, __ATOMIC_RELEASE);
    return e;
}
static int enter(struct ring* r, unsigned submit, unsigned wait) {
    return (int)syscall(__NR_io_uring_enter, r->fd, submit, wait, wait ? IORING_ENTER_GETEVENTS : 0, 0, 0);
}

static void uring_reads(int qd) {
    struct ring r; if (ring_init(&r, 256)) return;
    int fd = open(path, O_RDONLY | O_DIRECT);
    void* bufs[256]; double start[256];
    for (int i = 0; i < qd; i++) if (posix_memalign(&bufs[i], 4096, 4096)) exit(1);
    unsigned long s = 4242; long ops = 0, nl = 0; double* lat = malloc(sizeof(double) * 4000000);
    double c0 = cpu_us(), w0 = now_us(), end = w0 + secs * 1e6;
    for (int i = 0; i < qd; i++) {
        struct io_uring_sqe* e = sqe_get(&r);
        e->opcode = IORING_OP_READ; e->fd = fd; e->addr = (unsigned long)bufs[i]; e->len = 4096;
        e->off = (rnd(&s) % nblocks) * 4096; e->user_data = i; start[i] = now_us();
    }
    unsigned pending = qd;
    while (1) {
        enter(&r, pending, 1); pending = 0;
        unsigned head = *r.cq_head, tail = __atomic_load_n(r.cq_tail, __ATOMIC_ACQUIRE);
        double t = now_us(); int more = t < end;
        while (head != tail) {
            struct io_uring_cqe* c = &r.cqes[head & *r.cq_mask];
            if (c->res != 4096) { fprintf(stderr, "read: %d\n", c->res); exit(1); }
            int i = (int)c->user_data; if (nl < 4000000) lat[nl++] = t - start[i]; ops++; head++;
            if (more) {
                struct io_uring_sqe* e = sqe_get(&r);
                e->opcode = IORING_OP_READ; e->fd = fd; e->addr = (unsigned long)bufs[i]; e->len = 4096;
                e->off = (rnd(&s) % nblocks) * 4096; e->user_data = i; start[i] = now_us(); pending++;
            }
        }
        __atomic_store_n(r.cq_head, head, __ATOMIC_RELEASE);
        if (!more && pending == 0) {
            // drain what is still in flight
            unsigned inflight = *r.sq_tail - *r.cq_head;
            if (inflight == 0) break;
            enter(&r, 0, inflight);
            __atomic_store_n(r.cq_head, __atomic_load_n(r.cq_tail, __ATOMIC_ACQUIRE), __ATOMIC_RELEASE);
            break;
        }
    }
    double w = now_us() - w0, c = cpu_us() - c0;
    char name[64]; snprintf(name, sizeof name, "io_uring, one thread, depth %d", qd);
    report(name, ops, w, c, lat, nl); free(lat); close(fd); close(r.fd);
}

// 4 KiB writes into a preallocated file, each then flushed: pwrite +
// fdatasync, and io_uring write linked to fsync(DATASYNC)
static void flushes(void) {
    char wpath[4200]; snprintf(wpath, sizeof wpath, "%s.log", path);
    int fd = open(wpath, O_RDWR | O_CREAT | O_DIRECT, 0644);
    if (fallocate(fd, 0, 0, 64L << 20)) perror("fallocate");
    void* buf; if (posix_memalign(&buf, 4096, 4096)) exit(1); memset(buf, 7, 4096);
    for (long o = 0; o < (64L << 20); o += 4096) if (pwrite(fd, buf, 4096, o) != 4096) exit(1);
    fdatasync(fd);
    int n = 500; double* lat = malloc(sizeof(double) * n);
    double c0 = cpu_us(), w0 = now_us();
    for (int i = 0; i < n; i++) {
        double t0 = now_us();
        if (pwrite(fd, buf, 4096, (long)i * 4096) != 4096 || fdatasync(fd)) { perror("w"); exit(1); }
        lat[i] = now_us() - t0;
    }
    report("pwrite + fdatasync", n, now_us() - w0, cpu_us() - c0, lat, n);
    struct ring r; if (ring_init(&r, 8)) return;
    c0 = cpu_us(); w0 = now_us();
    for (int i = 0; i < n; i++) {
        double t0 = now_us();
        struct io_uring_sqe* e = sqe_get(&r);
        e->opcode = IORING_OP_WRITE; e->fd = fd; e->addr = (unsigned long)buf; e->len = 4096; e->off = (long)i * 4096;
        e->flags = IOSQE_IO_LINK;
        e = sqe_get(&r); e->opcode = IORING_OP_FSYNC; e->fd = fd; e->fsync_flags = IORING_FSYNC_DATASYNC;
        enter(&r, 2, 2);
        unsigned head = *r.cq_head, tail = __atomic_load_n(r.cq_tail, __ATOMIC_ACQUIRE);
        while (head != tail) { if (r.cqes[head & *r.cq_mask].res < 0) { fprintf(stderr, "uring w/fsync %d\n", r.cqes[head & *r.cq_mask].res); exit(1); } head++; }
        __atomic_store_n(r.cq_head, head, __ATOMIC_RELEASE);
        lat[i] = now_us() - t0;
    }
    report("io_uring write -> fsync(datasync)", n, now_us() - w0, cpu_us() - c0, lat, n);
    close(r.fd); close(fd); unlink(wpath); free(lat);
}

int main(int argc, char** argv) {
    if (argc < 4) { fprintf(stderr, "usage: uring_probe <file> <MiB> <seconds>\n"); return 2; }
    path = argv[1]; long mib = atol(argv[2]); secs = atof(argv[3]); nblocks = mib * 256;
    if (access(path, F_OK) != 0) {
        int fd = open(path, O_WRONLY | O_CREAT | O_DIRECT, 0644);
        void* buf; if (posix_memalign(&buf, 4096, 1 << 20)) return 1;
        unsigned long s = 1; for (int i = 0; i < (1 << 20) / 8; i++) ((unsigned long*)buf)[i] = rnd(&s);
        for (long i = 0; i < mib; i++) if (write(fd, buf, 1 << 20) != 1 << 20) { perror("write"); return 1; }
        fsync(fd); close(fd); free(buf);
        printf("wrote %ld MiB\n", mib);
    }
    pool(1); pool(8); pool(32);
    uring_reads(1); uring_reads(8); uring_reads(32); uring_reads(64);
    flushes();
    return 0;
}
