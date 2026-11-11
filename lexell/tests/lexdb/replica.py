"""The replica test: a master and a read-only replica (lexdb --replica), two
real processes on one data directory (design/lexdb.md 9.72).

    python3 lexell/tests/lexdb/replica.py [--rounds N] [--seed S] [--keep]

The master runs with a 4 MB cache, 1 MB log segments and a checkpoint every
512 KB of log, so that the replica's holds (pages and segments) are tested
by many checkpoints. Through psql:

- each round writes on the master (inserts, updates, deletes, large values,
  a table added now and then); the replica must then give the master's
  answers to a set of queries (it follows: it is waited for, up to 10 s);
- the replica refuses writes (25006) and goes on;
- the replica is killed (SIGKILL) during a round's writes every third round
  and started again: the master goes on, and the new replica catches up;
- the master is killed (SIGKILL) at round R/2: the replica must stop by
  itself (exit 1) within 10 s; both start again, the master recovering;
- at the end the master stops (SIGTERM) and the replica must stop too.

Exit 0 when all of that holds; 77 when psql is not installed.
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

QUERIES = [
    "select count(*), sum(v), sum(length(s)), min(id), max(id) from t",
    "select id, v from t order by id desc limit 5",
    "select g, count(*), sum(v) from t group by g order by g",
    "select count(*) from t where g = 3 and v > 50",
    "select id from t where id between 100 and 140 order by id",
    "select count(*), min(id), max(id) from u",
]


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


class Proc:
    def __init__(self, args, port, log, env):
        self.args, self.port, self.log, self.env = args, port, log, env
        self.p = None

    def start(self):
        out = open(self.log, 'a')
        out.write('--- start\n')
        out.flush()
        self.p = subprocess.Popen(self.args, stdout=out, stderr=out, env=self.env)
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
        if self.p.poll() is not None:
            return self.p.returncode
        self.p.send_signal(signal.SIGTERM)
        try:
            return self.p.wait(timeout)
        except subprocess.TimeoutExpired:
            self.kill()
            return 'hung'


def psql(port, sql, check=True):
    r = subprocess.run(['psql', '-h', '127.0.0.1', '-p', str(port), '-U', 'test', '-d', 'test', '-X', '-At',
                        '-v', 'ON_ERROR_STOP=1', '-c', sql], capture_output=True, text=True, timeout=120)
    if check and r.returncode != 0:
        raise RuntimeError('psql on %d: %s: %s' % (port, sql[:80], r.stderr.strip()))
    return r


def answers(port):
    out = []
    for q in QUERIES:
        r = psql(port, q, check=False)
        out.append(r.stdout if r.returncode == 0 else 'error: ' + r.stderr.strip())
    return out


def writes(rng, rnd):
    """One round's statements for the master."""
    sql = []
    for _ in range(rng.randrange(3, 8)):
        k = rng.randrange(6)
        a = rng.randrange(1, 3000)
        if k == 0:
            sql.append("insert into t select i, i %% 97, i %% 5, 'r%d-' || i from generate_series(%d, %d) i "
                       "where i not in (select id from t)" % (rnd, a, a + rng.randrange(1, 200)))
        elif k == 1:
            sql.append("update t set v = v + %d where id between %d and %d" % (rng.randrange(1, 9), a, a + 300))
        elif k == 2:
            sql.append("delete from t where id between %d and %d" % (a, a + rng.randrange(1, 40)))
        elif k == 3:
            sql.append("update t set s = '%s' where id = %d" % ('L' * rng.randrange(1500, 9000), a))
        elif k == 4:
            k = rnd * 100 + rng.randrange(100)
            sql.append("insert into u select i, 'u%d' from generate_series(%d, %d) i where i not in (select id from u)" % (rnd, k, k))
        else:
            sql.append("update t set g = (g + 1) %% 5 where id %% 13 = %d" % rng.randrange(13))
    return sql


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--rounds', type=int, default=12)
    ap.add_argument('--seed', type=int, default=None)
    ap.add_argument('--keep', action='store_true')
    a = ap.parse_args()
    if shutil.which('psql') is None:
        print('replica test: psql is not installed: skipped')
        sys.exit(77)
    seed = a.seed if a.seed is not None else random.randrange(1 << 30)
    rng = random.Random(seed)
    work = tempfile.mkdtemp(prefix='lexdb-replica-')
    exe = os.path.join(work, 'lexdb')
    r = subprocess.run([LXLC, os.path.join(ROOT, 'cmd', 'lexdb.lxl'), '-o', exe], capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit('replica.py: building lexdb failed:\n' + r.stdout + r.stderr)
    data = os.path.join(work, 'data')
    mport, rport = free_port(), free_port()
    env = dict(os.environ, LEXDB_CACHE_MB='4', LEXDB_SEG_KB='1024', LEXDB_CKPT_KB='512')
    master = Proc([exe, data, '127.0.0.1:%d' % mport], mport, os.path.join(work, 'master.log'), env)
    replica = Proc([exe, '--replica', data, '127.0.0.1:%d' % rport], rport, os.path.join(work, 'replica.log'), env)
    print('replica test: seed %d, %d rounds, work %s' % (seed, a.rounds, work), flush=True)

    def fail(why):
        replica.kill()
        master.kill()
        print('FAIL: ' + why)
        for name in ('master.log', 'replica.log'):
            p = os.path.join(work, name)
            if os.path.exists(p):
                print('--- ' + name)
                print(''.join(open(p).readlines()[-15:]))
        print('work kept: ' + work)
        sys.exit(1)

    def caught_up(rnd):
        want = answers(mport)
        end = time.time() + 10
        got = None
        while time.time() < end:
            got = answers(rport)
            if got == want:
                return
            time.sleep(0.05)
        for q, w, g in zip(QUERIES, want, got):
            if w != g:
                fail('round %d: the replica did not catch up: %s\n  master  %s\n  replica %s' % (rnd, q, w[:300], g[:300]))

    master.start()
    if not master.ready():
        fail('the master did not start')
    psql(mport, "create table t (id int primary key, v int not null, g int not null, s text)")
    psql(mport, "create index t_g on t (g)")
    psql(mport, "create table u (id int primary key, name text)")
    psql(mport, "insert into t select i, i % 97, i % 5, 'row ' || i from generate_series(1, 20000) i")
    replica.start()
    if not replica.ready():
        fail('the replica did not start')
    caught_up(0)
    refused = 0
    for rnd in range(1, a.rounds + 1):
        sql = writes(rng, rnd)
        if rnd % 4 == 0:
            sql.append('create table t%d (a int primary key, b text)' % rnd)
            sql.append("insert into t%d values (1, 'x'), (2, 'y')" % rnd)
            QUERIES.append('select a, b from t%d order by a' % rnd)        # a table made since
        kill_replica = rnd % 3 == 0
        bg = None
        if kill_replica:
            # the writes go on while the replica is killed
            bg = subprocess.Popen(['psql', '-h', '127.0.0.1', '-p', str(mport), '-U', 'test', '-d', 'test', '-X', '-q',
                                   '-v', 'ON_ERROR_STOP=1', '-c', '; '.join(sql)],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
            time.sleep(rng.uniform(0.0, 0.3))
            replica.kill()
            if bg.wait(120) != 0:
                fail('round %d: the master failed while the replica was killed: %s' % (rnd, bg.stderr.read()))
            replica.start()
            if not replica.ready():
                fail('round %d: the replica did not start again' % rnd)
        else:
            for q in sql:
                psql(mport, q)
        caught_up(rnd)
        w = psql(rport, "insert into u values (999999, 'no')", check=False)
        if '25006' in w.stderr or 'read-only' in w.stderr:
            refused += 1
        else:
            fail('round %d: a write on the replica was not refused: %s %s' % (rnd, w.stdout, w.stderr))
        if rnd == a.rounds // 2:
            master.kill()
            try:
                code = replica.p.wait(10)
            except subprocess.TimeoutExpired:
                fail('the replica did not stop after the master was killed')
            if code != 1:
                fail('the replica stopped with %s after the master was killed, not 1' % code)
            master.start()
            if not master.ready():
                fail('the master did not recover')
            replica.start()
            if not replica.ready():
                fail('the replica did not start after the master recovered')
            caught_up(rnd)
    code = master.stop()
    if code != 0:
        fail('the master stopped with %s' % code)
    try:
        rc = replica.p.wait(10)
    except subprocess.TimeoutExpired:
        fail('the replica did not stop after the master did')
    print('replica test: %d rounds, the replica caught up every round, %d writes refused, killed and started again %d times, '
          'the master killed once: passed' % (a.rounds, refused, a.rounds // 3))
    if not a.keep:
        shutil.rmtree(work)


if __name__ == '__main__':
    main()
