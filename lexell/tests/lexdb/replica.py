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

Then the supervised form, lexdb DATADIR ADDR --replicas 2: both replicas
answer on the replicas' port; the master (a worker) killed with SIGKILL is
started again by the supervisor, and the replicas with it, the data
intact; a replica killed is started again on its own; SIGTERM to the
supervisor stops them all (exit 0).

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


def children(pid):
    try:
        return [int(x) for x in open('/proc/%d/task/%d/children' % (pid, pid)).read().split()]
    except OSError:
        return []


def holds_lock(pid, data):
    lock = os.path.join(data, 'lock')
    try:
        for fd in os.listdir('/proc/%d/fd' % pid):
            try:
                if os.readlink('/proc/%d/fd/%s' % (pid, fd)) == lock:
                    return True
            except OSError:
                pass
    except OSError:
        pass
    return False


def wait_for(cond, timeout):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


def supervised(exe, work, env, fail):
    data = os.path.join(work, 'sdata')
    mport = free_port()
    rport = free_port()
    log = os.path.join(work, 'supervised.log')
    sup = Proc([exe, data, '127.0.0.1:%d' % mport, '--replicas', '2', '--replica-addr', '127.0.0.1:%d' % rport],
               mport, log, env)
    sup.start()
    if not sup.ready():
        fail('supervised: the master did not start')
    replica_up = lambda: psql(rport, 'select 1', check=False).returncode == 0
    if not wait_for(replica_up, 60):
        fail('supervised: the replicas did not start')
    psql(mport, 'create table s (id int primary key, v int not null)')
    psql(mport, 'insert into s select i, i from generate_series(1, 5000) i')
    want = psql(mport, 'select count(*), sum(v) from s').stdout
    same = lambda: psql(rport, 'select count(*), sum(v) from s', check=False).stdout == want
    # every replica: enough connections that both answer
    if not wait_for(lambda: all(same() for _ in range(8)), 10):
        fail('supervised: the replicas did not catch up')
    kids = children(sup.p.pid)
    if len(kids) != 3:
        fail('supervised: %d workers, not 3' % len(kids))
    masters = [k for k in kids if holds_lock(k, data)]
    if len(masters) != 1:
        fail('supervised: %d workers hold the lock' % len(masters))
    os.kill(masters[0], signal.SIGKILL)
    if not wait_for(lambda: len(children(sup.p.pid)) == 3 and masters[0] not in children(sup.p.pid), 10):
        fail('supervised: the master was not started again')
    if not wait_for(lambda: psql(mport, 'select count(*), sum(v) from s', check=False).stdout == want, 60):
        fail('supervised: the master did not come back with the data')
    psql(mport, 'insert into s values (5001, 5001)')
    want = psql(mport, 'select count(*), sum(v) from s').stdout
    if not wait_for(lambda: all(same() for _ in range(8)), 60):
        fail('supervised: the replicas did not come back after the master')
    reps = [k for k in children(sup.p.pid) if not holds_lock(k, data)]
    os.kill(reps[0], signal.SIGKILL)
    if not wait_for(lambda: len(children(sup.p.pid)) == 3 and reps[0] not in children(sup.p.pid), 10):
        fail('supervised: the replica was not started again')
    if not wait_for(lambda: all(same() for _ in range(8)), 60):
        fail('supervised: the replica did not come back')
    w = psql(rport, 'delete from s', check=False)
    if '25006' not in w.stderr and 'read-only' not in w.stderr:
        fail('supervised: a write on a replica was not refused')
    code = sup.stop()
    if code != 0:
        fail('supervised: the supervisor stopped with %s' % code)
    print('replica test: supervised, a master and 2 replicas: the master killed and started again with the replicas, '
          'a replica killed and started again, stopped by SIGTERM: passed', flush=True)


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
          'the master killed once: passed' % (a.rounds, refused, a.rounds // 3), flush=True)
    supervised(exe, work, env, fail)
    if not a.keep:
        shutil.rmtree(work)


if __name__ == '__main__':
    main()
