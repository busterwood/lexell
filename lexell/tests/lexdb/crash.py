#!/usr/bin/env python3
"""The whole-server crash test: a real lexdb process, on the real disk,
killed while 12 connections load it, then restarted and checked.

    python3 lexell/tests/lexdb/crash.py [--rounds N] [--seed S] [--keep]

Each round starts the server (recovering from the last kill), runs
crash/client.lxl's load (transfers in blocks, prepared inserts that split
the tree, deletes), and after 0.3 to 3 s kills the server with SIGKILL;
every fifth round it stops it with SIGTERM instead, and it must exit 0.
Every fourth round the restarted server is killed again during its
recovery. Then the server starts once more and the client checks the
database against every round's records: acknowledged commits there,
acknowledged deletes gone, nothing never attempted, every row as written,
the accounts' sum kept, the index agreeing with the scan.

The server runs with a 4 MB cache, 1 MB log segments and a checkpoint every
512 KB of log (LEXDB_CACHE_MB, LEXDB_SEG_KB, LEXDB_CKPT_KB), so that kills
land in evictions, segment switches and checkpoints. A kill of the process
leaves the kernel's page cache intact: this tests the server's own path
(sockets, group commit, checkpoints, recovery), not a power cut, which the
simulated disk's tests cover (store_crash).

Exit 0 when every round's check passes; on a failure the work directory is
kept and named.
"""
import argparse
import os
import random
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..', '..'))
LXLC = os.environ.get('LXLC', os.path.join(ROOT, 'compiler', 'out', 'lxlc'))


def build(src, out):
    r = subprocess.run([LXLC, src, '-o', out], capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit('crash.py: building %s failed:\n%s%s' % (src, r.stdout, r.stderr))


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


class Server:
    def __init__(self, exe, data, port, log):
        self.exe, self.data, self.port, self.log = exe, data, port, log
        self.p = None

    def start(self):
        env = dict(os.environ, LEXDB_CACHE_MB='4', LEXDB_SEG_KB='1024', LEXDB_CKPT_KB='512')
        out = open(self.log, 'a')
        out.write('--- start\n')
        out.flush()
        self.p = subprocess.Popen([self.exe, self.data, '127.0.0.1:%d' % self.port], stdout=out, stderr=out, env=env)
        out.close()

    def ready(self, timeout=60):
        end = time.time() + timeout
        while time.time() < end:
            if self.p.poll() is not None:
                return False
            try:
                socket.create_connection(('127.0.0.1', self.port), 0.2).close()
                return True
            except OSError:
                time.sleep(0.02)
        return False

    def kill(self):
        if self.p and self.p.poll() is None:
            self.p.send_signal(signal.SIGKILL)
            self.p.wait()

    def stop(self, timeout=60):
        self.p.send_signal(signal.SIGTERM)
        try:
            return self.p.wait(timeout)
        except subprocess.TimeoutExpired:
            self.kill()
            return 'hung'


def tail(path, n=20):
    with open(path) as f:
        return ''.join(f.readlines()[-n:])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--rounds', type=int, default=20)
    ap.add_argument('--seed', type=int, default=None)
    ap.add_argument('--keep', action='store_true')
    a = ap.parse_args()
    seed = a.seed if a.seed is not None else random.randrange(1 << 30)
    rng = random.Random(seed)
    work = tempfile.mkdtemp(prefix='lexdb-crash-')
    exe, client = os.path.join(work, 'lexdb'), os.path.join(work, 'client')
    build(os.path.join(ROOT, 'cmd', 'lexdb.lxl'), exe)
    build(os.path.join(HERE, 'crash', 'client.lxl'), client)
    data, recs, log = os.path.join(work, 'data'), os.path.join(work, 'records'), os.path.join(work, 'server.log')
    os.makedirs(recs)
    port = free_port()
    dsn = 'host=127.0.0.1 port=%d user=crash dbname=crash sslmode=disable' % port
    srv = Server(exe, data, port, log)
    print('crash test: seed %d, %d rounds, work %s' % (seed, a.rounds, work), flush=True)

    def fail(why):
        srv.kill()
        print('FAIL: %s\nserver log (tail):\n%s\nwork directory kept: %s' % (why, tail(log), work))
        sys.exit(1)

    srv.start()
    if not srv.ready():
        fail('the server did not start')
    r = subprocess.run([client, 'setup', dsn, recs], capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        fail('setup: ' + r.stdout + r.stderr)
    for rnd in range(1, a.rounds + 1):
        load = subprocess.Popen([client, 'load', dsn, recs, str(rnd)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        time.sleep(rng.uniform(0.3, 3.0))
        clean = rnd % 5 == 0
        if clean:
            code = srv.stop()
            how = 'SIGTERM'
            if code != 0:
                fail('round %d: SIGTERM: the server exited %s' % (rnd, code))
        else:
            srv.kill()
            how = 'SIGKILL'
        try:
            out, _ = load.communicate(timeout=120)
        except subprocess.TimeoutExpired:
            load.kill()
            fail('round %d: the load did not end after the server stopped' % rnd)
        if load.returncode != 0:
            fail('round %d: load exited %d: %s' % (rnd, load.returncode, out))
        again = ''
        if rnd % 4 == 0:
            srv.start()
            time.sleep(rng.uniform(0.0, 0.3))
            srv.kill()
            again = ', killed again in recovery'
        srv.start()
        t0 = time.time()
        if not srv.ready():
            fail('round %d: the server did not come back' % rnd)
        up = time.time() - t0
        r = subprocess.run([client, 'check', dsn, recs], capture_output=True, text=True, timeout=300)
        if r.returncode != 0:
            fail('round %d (%s%s): check:\n%s%s' % (rnd, how, again, r.stdout, r.stderr))
        print('round %2d: %s%s, up in %.2f s, %s' % (rnd, how, again, up, r.stdout.strip()), flush=True)
    code = srv.stop()
    if code != 0:
        fail('final SIGTERM: the server exited %s' % code)
    with open(log) as f:
        text = f.read()
    for bad in ('panic', 'corrupt', 'Lexell:'):
        if bad in text:
            fail('the server log mentions "%s"' % bad)
    du = sum(os.path.getsize(os.path.join(data, n)) for n in os.listdir(data))
    print('passed: %d rounds, data %.1f MB' % (a.rounds, du / 1e6))
    if not a.keep:
        shutil.rmtree(work)


if __name__ == '__main__':
    main()
