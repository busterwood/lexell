#!/usr/bin/env python3
# pgmeasure.py PORT QUERIES RUNS [user] [db]: median wall ms, output discarded.
import subprocess, sys, time, statistics
port = sys.argv[1]; qfile = sys.argv[2]; runs = int(sys.argv[3])
user = sys.argv[4] if len(sys.argv) > 4 else 'me'
db = sys.argv[5] if len(sys.argv) > 5 else 'postgres'
qs = []
for line in open(qfile):
    line = line.strip()
    if not line or line.startswith('#'): continue
    name, sql = line.split('|', 1); qs.append((name, sql))
def run(sql):
    return subprocess.run(['psql', '-X', '-q', '-A', '-t', '-h', '127.0.0.1', '-p', port,
                           '-U', user, '-d', db, '-c', sql],
                          stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
for _, sql in qs: run(sql)   # warm
print(f"{'query':22s} {'wall ms':>9s}")
for name, sql in qs:
    ws = []
    for _ in range(runs):
        t0 = time.perf_counter_ns(); p = run(sql); t1 = time.perf_counter_ns()
        if p.returncode != 0:
            print(name, 'ERROR', p.stderr.decode().strip()[:120]); break
        ws.append((t1 - t0) / 1e6)
    else:
        print(f"{name:22s} {statistics.median(ws):9.1f}")
