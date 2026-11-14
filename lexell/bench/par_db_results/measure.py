#!/usr/bin/env python3
# measure.py PORT PID QUERIES [runs]: wall ms and server CPU ms, median.
import os, subprocess, sys, time, statistics

port, pid = sys.argv[1], int(sys.argv[2])
qfile, runs = sys.argv[3], int(sys.argv[4]) if len(sys.argv) > 4 else 3
qs = []
for line in open(qfile):
    line = line.strip()
    if not line or line.startswith('#'):
        continue
    name, sql = line.split('|', 1)
    qs.append((name, sql))

def cpu():
    f = open(f'/proc/{pid}/stat').read().split()
    return (int(f[13]) + int(f[14])) * 10.0  # ms

def psql(sql):
    return subprocess.run(['psql', '-X', '-q', '-A', '-t', '-h', '127.0.0.1', '-p', port,
                           '-U', 'lexdb', '-d', 'lexdb', '-c', sql],
                          stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

# warm
for _, sql in qs:
    psql(sql)
print(f"{'query':22s} {'wall ms':>9s} {'cpu ms':>9s}")
for name, sql in qs:
    ws, cs = [], []
    for _ in range(runs):
        c0 = cpu(); t0 = time.perf_counter_ns()
        p = psql(sql)
        t1 = time.perf_counter_ns(); c1 = cpu()
        if p.returncode != 0:
            print(name, 'ERROR', p.stderr.decode().strip()[:120]); break
        ws.append((t1 - t0) / 1e6); cs.append(c1 - c0)
    else:
        print(f"{name:22s} {statistics.median(ws):9.1f} {statistics.median(cs):9.1f}")
