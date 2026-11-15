# probe2.py SOCKDIR MASTER_PORT REPLICA_PORT SECONDS [CONNS] [EVERY_MS]: the master commits a counter every EVERY_MS;
# CONNS threads, each with its own replica connection, poll it without pause. A thread's delay for a value is the time
# from the master's commit acknowledgement to the first read that shows it (to within one read, about 0.1 ms).
import sys, time, threading, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pgw import Conn
sd, mp, rp, secs = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), float(sys.argv[4])
nconn = int(sys.argv[5]) if len(sys.argv) > 5 else 6
every = (float(sys.argv[6]) if len(sys.argv) > 6 else 50) / 1000
m = Conn(sd, mp)
m.query('create table if not exists lagm (id int primary key, n bigint)')
m.query('insert into lagm values (1, 0) on conflict (id) do nothing')
start = int(m.query('select n from lagm where id = 1')[0][0])
acked = {}; slow = []; t00 = time.perf_counter(); stop = False; delays = [[] for _ in range(nconn)]; reads = [0] * nconn
def reader(i):
    c = Conn(sd, rp); last = start
    while not stop:
        v = int(c.query('select n from lagm where id = 1')[0][0]); t = time.perf_counter(); reads[i] += 1
        while last < v:
            last += 1
            a = acked.get(last)
            if a is None:            # visible before its ack reached us
                time.sleep(0.0005); a = acked.get(last)
            if a is not None:
                delays[i].append((t - a) * 1000)
                if (t - a) > 0.001: slow.append((a - t00, last, i, (t - a) * 1000))
ts = [threading.Thread(target=reader, args=(i,)) for i in range(nconn)]
for t in ts: t.start()
time.sleep(0.3)
end = time.time() + secs; n = 0
while time.time() < end:
    t0 = time.perf_counter()
    v = int(m.query('update lagm set n = n + 1 where id = 1 returning n')[0][0])
    acked[v] = time.perf_counter(); n += 1
    left = every - (time.perf_counter() - t0)
    if left > 0: time.sleep(left)
time.sleep(0.5); stop = True
for t in ts: t.join()
allv = sorted(x for d in delays for x in d)
q = lambda a, p: a[min(len(a) - 1, int(p * len(a)))]
print('commits %d; reads %d; ack-to-visible ms over %d observations: p50 %.2f p90 %.2f p99 %.2f p99.9 %.2f max %.2f' %
      (n, sum(reads), len(allv), q(allv, .5), q(allv, .9), q(allv, .99), q(allv, .999), allv[-1]))
print('  over 1 ms: %d (%.2f%%)' % (sum(1 for x in allv if x > 1), 100.0 * sum(1 for x in allv if x > 1) / len(allv)))
by = {}
for a, v, i, d in slow: by.setdefault(v, []).append((i, d, a))
for v in sorted(by)[:20]:
    xs = by[v]; print('  commit %d at +%.2fs: %d of %d connections over 1 ms, worst %.1f ms' % (v, xs[0][2], len(xs), nconn, max(x[1] for x in xs)))
