// sockbench: one server thread answering small requests (60 B in, 80 B out),
// the shape of a prepared point select, to compare epoll with io_uring.
// Design note lexdb.md 9.55 and 9.56.
//
//   gcc -O2 -Wall -o sockbench sockbench.c
//   sockbench MODE CLIENTS WORK_US SECONDS [WAITN]
//
// MODE:
//   epoll     edge-triggered, read until EAGAIN, write (as the Lexell runtime)
//   uring     recv + send SQEs; a turn's sends and re-armed recvs for every
//             connection go in the one io_uring_enter that also waits;
//             SINGLE_ISSUER | DEFER_TASKRUN
//   uring_pf  the same, recv with IORING_RECVSEND_POLL_FIRST
//   sqpoll    an SQPOLL kernel thread submits; the server waits with GETEVENTS
//   sqpoll_pf the same with POLL_FIRST
// WORK_US: user time spun per message (lexdb's SQL work is ~13 us).
// WAITN:   io_uring waits for this many completions (50 us timeout if > 1).
//
// Environment:
//   TCP=1    loopback TCP (TCP_NODELAY) instead of Unix stream socketpairs
//   POLLC=1  clients wait in poll(POLLIN) before read, as libpq does
//   SPIN=1   clients poll with MSG_DONTWAIT and never sleep
//   SSPIN=us the server polls (timeout 0) this long before blocking
//   PIN=1    server on CPU 0, client i on CPU 2+i
//   NOTS=1   no timeout on the io_uring wait
//
// Output: messages/s; CPU per message of the whole server process (its
// thread plus any SQPOLL kernel thread), split user/sys; IPIs per message
// from /proc/interrupts (CAL: function-call IPIs, which wake tasks on other
// CPUs; HYP/HVS: Hyper-V callbacks and timer).
#define _GNU_SOURCE
#include <arpa/inet.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <linux/io_uring.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <poll.h>
#include <sched.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/epoll.h>
#include <sys/mman.h>
#include <sys/resource.h>
#include <sys/socket.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#define REQ 60
#define REP 80
#define MAXC 256

static double now(void) {
	struct timespec t;
	clock_gettime(CLOCK_MONOTONIC, &t);
	return t.tv_sec + t.tv_nsec * 1e-9;
}
static void spin(double us) {
	if (us <= 0) return;
	double end = now() + us * 1e-6;
	while (now() < end) {}
}
static void pin(int cpu) {
	if (!getenv("PIN")) return;
	cpu_set_t m;
	CPU_ZERO(&m);
	CPU_SET(cpu % sysconf(_SC_NPROCESSORS_ONLN), &m);
	sched_setaffinity(0, sizeof m, &m);
}

static int spinc, pollc;
static void client(int fd) {
	char q[REQ], r[REP];
	memset(q, 'q', REQ);
	for (;;) {
		if (write(fd, q, REQ) != REQ) _exit(0);
		int got = 0;
		while (got < REP) {
			if (pollc) {
				struct pollfd pf = {fd, POLLIN, 0};
				poll(&pf, 1, -1);
			}
			int n = spinc ? recv(fd, r + got, REP - got, MSG_DONTWAIT) : read(fd, r + got, REP - got);
			if (n < 0 && spinc && errno == EAGAIN) continue;
			if (n <= 0) _exit(0);
			got += n;
		}
	}
}

// ---- measurement ----
static long long nmsg;
struct cpu { double self_u, self_s, other; };
static double tick;
static struct cpu sample(void) {
	struct cpu c = {0};
	struct rusage ru;
	getrusage(RUSAGE_THREAD, &ru);
	c.self_u = ru.ru_utime.tv_sec + ru.ru_utime.tv_usec * 1e-6;
	c.self_s = ru.ru_stime.tv_sec + ru.ru_stime.tv_usec * 1e-6;
	pid_t me = syscall(SYS_gettid);
	DIR *d = opendir("/proc/self/task");
	struct dirent *e;
	while ((e = readdir(d))) {
		if (e->d_name[0] == '.' || atoi(e->d_name) == me) continue;
		char p[300], b[1024];
		snprintf(p, sizeof p, "/proc/self/task/%s/stat", e->d_name);
		FILE *f = fopen(p, "r");
		if (!f) continue;
		if (fgets(b, sizeof b, f)) {
			char *s = strrchr(b, ')') + 2;
			unsigned long ut = 0, st = 0;
			sscanf(s, "%*c %*d %*d %*d %*d %*d %*u %*u %*u %*u %*u %lu %lu", &ut, &st);
			c.other += (ut + st) * tick;
		}
		fclose(f);
	}
	closedir(d);
	return c;
}

#define NIRQ 4
static const char *irqname[NIRQ] = {"RES", "CAL", "HYP", "HVS"};
static void irqs(long long *v) {
	FILE *f = fopen("/proc/interrupts", "r");
	char line[8192];
	memset(v, 0, NIRQ * sizeof *v);
	while (fgets(line, sizeof line, f)) {
		char *p = line;
		while (*p == ' ') p++;
		for (int k = 0; k < NIRQ; k++) {
			size_t l = strlen(irqname[k]);
			if (!strncmp(p, irqname[k], l) && p[l] == ':') {
				char *q = p + l + 1, *end;
				for (;;) {
					long long x = strtoll(q, &end, 10);
					if (end == q) break;
					v[k] += x;
					q = end;
				}
			}
		}
	}
	fclose(f);
}

static int phase; // 0 warmup, 1 measuring, 2 done
static double t0, tend, twarm;
static struct cpu c0;
static long long m0, irq0[NIRQ];
static void check_time(void) {
	double t = now();
	if (phase == 0 && t >= twarm) { phase = 1; c0 = sample(); irqs(irq0); m0 = nmsg; t0 = t; }
	else if (phase == 1 && t >= tend) phase = 2;
}

static int fds[MAXC];
static int nc;
static double work, sspin;
static char rep[REP];

// ---- epoll ----
static void run_epoll(void) {
	int ep = epoll_create1(0);
	for (int i = 0; i < nc; i++) {
		struct epoll_event ev = {.events = EPOLLIN | EPOLLET, .data.fd = fds[i]};
		epoll_ctl(ep, EPOLL_CTL_ADD, fds[i], &ev);
	}
	struct epoll_event evs[64];
	char buf[4096];
	while (phase < 2) {
		int n = epoll_wait(ep, evs, 64, 0);
		if (n == 0 && sspin > 0) {
			double end = now() + sspin * 1e-6;
			while (n == 0 && now() < end) n = epoll_wait(ep, evs, 64, 0);
		}
		if (n == 0) n = epoll_wait(ep, evs, 64, 100);
		for (int i = 0; i < n; i++) {
			int fd = evs[i].data.fd;
			for (;;) {
				int r = read(fd, buf, sizeof buf);
				if (r <= 0) break;
				for (int k = 0; k < r / REQ; k++) {
					spin(work);
					if (write(fd, rep, REP) != REP) exit(1);
					nmsg++;
				}
			}
		}
		check_time();
	}
}

// ---- io_uring, raw syscalls (no liburing) ----
static int ring;
static unsigned *sq_tail, *sq_mask, *sq_array, *sq_flags;
static unsigned *cq_head, *cq_tail, *cq_mask;
static struct io_uring_sqe *sqes;
static struct io_uring_cqe *cqes;
static unsigned sq_local_tail, to_submit;
static int sqpoll, pollfirst;
static unsigned waitn = 1;
static long long nenter, nbatch;

static void setup_ring(unsigned flags) {
	struct io_uring_params p = {0};
	p.flags = flags;
	if (flags & IORING_SETUP_SQPOLL) p.sq_thread_idle = 2000;
	ring = syscall(SYS_io_uring_setup, 1024, &p);
	if (ring < 0) { perror("io_uring_setup"); exit(1); }
	size_t sl = p.sq_off.array + p.sq_entries * sizeof(unsigned);
	size_t cl = p.cq_off.cqes + p.cq_entries * sizeof(struct io_uring_cqe);
	if (cl > sl) sl = cl;
	char *sq = mmap(0, sl, PROT_READ | PROT_WRITE, MAP_SHARED | MAP_POPULATE, ring, IORING_OFF_SQ_RING);
	char *cq = sq; // IORING_FEAT_SINGLE_MMAP
	sqes = mmap(0, p.sq_entries * sizeof(struct io_uring_sqe), PROT_READ | PROT_WRITE, MAP_SHARED | MAP_POPULATE, ring, IORING_OFF_SQES);
	sq_tail = (unsigned *)(sq + p.sq_off.tail);
	sq_mask = (unsigned *)(sq + p.sq_off.ring_mask);
	sq_array = (unsigned *)(sq + p.sq_off.array);
	sq_flags = (unsigned *)(sq + p.sq_off.flags);
	cq_head = (unsigned *)(cq + p.cq_off.head);
	cq_tail = (unsigned *)(cq + p.cq_off.tail);
	cq_mask = (unsigned *)(cq + p.cq_off.ring_mask);
	cqes = (struct io_uring_cqe *)(cq + p.cq_off.cqes);
	for (unsigned i = 0; i < p.sq_entries; i++) sq_array[i] = i;
	sq_local_tail = *sq_tail;
}
static struct io_uring_sqe *get_sqe(void) {
	struct io_uring_sqe *s = &sqes[sq_local_tail & *sq_mask];
	sq_local_tail++;
	to_submit++;
	memset(s, 0, sizeof *s);
	return s;
}
static char rbuf[MAXC][4096];
static void prep_recv(int i) {
	struct io_uring_sqe *s = get_sqe();
	s->opcode = IORING_OP_RECV;
	s->fd = fds[i];
	s->addr = (uintptr_t)rbuf[i];
	s->len = sizeof rbuf[i];
	if (pollfirst) s->ioprio = IORING_RECVSEND_POLL_FIRST;
	s->user_data = (uint64_t)i << 1;
}
static void prep_send(int i) {
	struct io_uring_sqe *s = get_sqe();
	s->opcode = IORING_OP_SEND;
	s->fd = fds[i];
	s->addr = (uintptr_t)rep;
	s->len = REP;
	s->user_data = ((uint64_t)i << 1) | 1;
}
static void enter(unsigned min_complete) {
	__atomic_store_n(sq_tail, sq_local_tail, __ATOMIC_RELEASE);
	unsigned flags = 0, sub = to_submit;
	if (sqpoll) {
		sub = 0;
		if (__atomic_load_n(sq_flags, __ATOMIC_ACQUIRE) & IORING_SQ_NEED_WAKEUP) flags |= IORING_ENTER_SQ_WAKEUP;
		if (!min_complete && !flags) { to_submit = 0; return; }
	}
	if (min_complete) flags |= IORING_ENTER_GETEVENTS;
	struct __kernel_timespec ts = {0, waitn > 1 ? 50000 : 100000000};
	struct io_uring_getevents_arg ga = {.ts = (uintptr_t)&ts};
	int ext = min_complete && !getenv("NOTS");
	if (ext) flags |= IORING_ENTER_EXT_ARG;
	nenter++;
	nbatch += to_submit;
	int r = syscall(SYS_io_uring_enter, ring, sub, min_complete, flags, ext ? &ga : NULL, ext ? sizeof ga : 0);
	if (r < 0 && errno != ETIME && errno != EINTR && errno != EBUSY) { perror("io_uring_enter"); exit(1); }
	to_submit = 0;
}
static void run_uring(unsigned flags) {
	setup_ring(flags);
	for (int i = 0; i < nc; i++) prep_recv(i);
	while (phase < 2) {
		unsigned h = *cq_head, t = __atomic_load_n(cq_tail, __ATOMIC_ACQUIRE);
		if (h == t && sspin > 0 && !sqpoll) {
			// submit and reap without sleeping until work shows up or time is up
			double end = now() + sspin * 1e-6;
			do {
				__atomic_store_n(sq_tail, sq_local_tail, __ATOMIC_RELEASE);
				nenter++;
				nbatch += to_submit;
				syscall(SYS_io_uring_enter, ring, to_submit, 0, IORING_ENTER_GETEVENTS, NULL, 0);
				to_submit = 0;
				t = __atomic_load_n(cq_tail, __ATOMIC_ACQUIRE);
			} while (h == t && now() < end);
		}
		if (h == t) {
			enter(waitn); // submits this turn's whole batch and waits, one call
			check_time();
			continue;
		}
		for (; h != t; h++) {
			struct io_uring_cqe *c = &cqes[h & *cq_mask];
			int i = c->user_data >> 1;
			if (c->user_data & 1) continue; // send done
			if (c->res <= 0) {
				if (c->res != -EAGAIN && c->res != -ENOBUFS) { fprintf(stderr, "recv %d\n", c->res); exit(1); }
				prep_recv(i);
				continue;
			}
			for (int k = 0; k < c->res / REQ; k++) {
				spin(work);
				prep_send(i);
				nmsg++;
			}
			prep_recv(i);
		}
		__atomic_store_n(cq_head, h, __ATOMIC_RELEASE);
		if (sqpoll) enter(0); // only wakes the SQ thread if it sleeps
		check_time();
	}
}

int main(int argc, char **argv) {
	if (argc < 5) { fprintf(stderr, "usage: sockbench MODE CLIENTS WORK_US SECONDS [WAITN]\n"); return 2; }
	const char *mode = argv[1];
	nc = atoi(argv[2]);
	if (nc < 1 || nc > MAXC) { fprintf(stderr, "clients 1..%d\n", MAXC); return 2; }
	work = atof(argv[3]);
	double secs = atof(argv[4]);
	if (argc > 5) waitn = atoi(argv[5]);
	tick = 1.0 / sysconf(_SC_CLK_TCK);
	spinc = getenv("SPIN") != 0;
	pollc = getenv("POLLC") != 0;
	if (getenv("SSPIN")) sspin = atof(getenv("SSPIN"));
	int tcp = getenv("TCP") != 0, lfd = -1;
	struct sockaddr_in sa = {.sin_family = AF_INET, .sin_addr.s_addr = htonl(INADDR_LOOPBACK)};
	if (tcp) {
		lfd = socket(AF_INET, SOCK_STREAM, 0);
		bind(lfd, (struct sockaddr *)&sa, sizeof sa);
		socklen_t sl = sizeof sa;
		getsockname(lfd, (struct sockaddr *)&sa, &sl);
		listen(lfd, 512);
	}
	memset(rep, 'r', REP);
	pid_t kids[MAXC];
	for (int i = 0; i < nc; i++) {
		int sv[2], one = 1;
		if (tcp) {
			sv[1] = socket(AF_INET, SOCK_STREAM, 0);
			if (connect(sv[1], (struct sockaddr *)&sa, sizeof sa)) { perror("connect"); exit(1); }
			sv[0] = accept4(lfd, 0, 0, SOCK_NONBLOCK);
			setsockopt(sv[0], IPPROTO_TCP, TCP_NODELAY, &one, sizeof one);
			setsockopt(sv[1], IPPROTO_TCP, TCP_NODELAY, &one, sizeof one);
		} else {
			socketpair(AF_UNIX, SOCK_STREAM | SOCK_NONBLOCK, 0, sv);
		}
		pid_t p = fork();
		if (p == 0) {
			close(sv[0]);
			fcntl(sv[1], F_SETFL, 0); // the client blocks unless SPIN
			pin(2 + i);
			client(sv[1]);
		}
		kids[i] = p;
		close(sv[1]);
		fds[i] = sv[0];
	}
	pin(0);
	twarm = now() + 0.5;
	tend = twarm + secs;
	if (!strcmp(mode, "epoll")) run_epoll();
	else if (!strcmp(mode, "uring")) run_uring(IORING_SETUP_SINGLE_ISSUER | IORING_SETUP_DEFER_TASKRUN);
	else if (!strcmp(mode, "uring_pf")) { pollfirst = 1; run_uring(IORING_SETUP_SINGLE_ISSUER | IORING_SETUP_DEFER_TASKRUN); }
	else if (!strcmp(mode, "sqpoll")) { sqpoll = 1; run_uring(IORING_SETUP_SQPOLL | IORING_SETUP_SINGLE_ISSUER); }
	else if (!strcmp(mode, "sqpoll_pf")) { sqpoll = 1; pollfirst = 1; run_uring(IORING_SETUP_SQPOLL | IORING_SETUP_SINGLE_ISSUER); }
	else { fprintf(stderr, "bad mode\n"); return 2; }
	struct cpu c1 = sample();
	long long irq1[NIRQ];
	irqs(irq1);
	double dt = now() - t0;
	long long m = nmsg - m0;
	for (int i = 0; i < nc; i++) kill(kids[i], SIGKILL);
	for (int i = 0; i < nc; i++) waitpid(kids[i], 0, 0);
	double us = 1e6 / m;
	double tot = ((c1.self_u - c0.self_u) + (c1.self_s - c0.self_s) + (c1.other - c0.other)) * us;
	printf("%-9s %s%s%s sspin %-3.0f waitn %-2u clients %3d work %4.1f  msgs/s %7.0f  cpu/msg %5.2f us (user %5.2f sys %5.2f sqpoll %5.2f)  busy %3.0f%%  sqes/enter %4.1f  per msg:",
	       mode, tcp ? "tcp " : "unix", pollc ? "+poll" : "", spinc ? "+spin" : "", sspin, waitn, nc, work, m / dt, tot,
	       (c1.self_u - c0.self_u) * us, (c1.self_s - c0.self_s) * us, (c1.other - c0.other) * us,
	       100 * ((c1.self_u - c0.self_u) + (c1.self_s - c0.self_s)) / dt,
	       nenter ? (double)nbatch / nenter : 0);
	for (int k = 0; k < NIRQ; k++) printf(" %s %.2f", irqname[k], (double)(irq1[k] - irq0[k]) / m);
	printf("\n");
	return 0;
}
