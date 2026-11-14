#!/usr/bin/env python3
"""Tests of lexdb's --log-dir (design/lexdb.md 9.124).

    python3 lexell/tests/lexdb/logdir.py

A data directory made with --log-dir DIR keeps its log segments (log.N,
log.spare) in DIR and none beside data.lxdb; a restart recovers from them
(also after SIGKILL). The start-up check refuses, exit 1 and a message, the
wrong log: the directory started without the option or with another log
directory (empty, or another database's), one made without the option started
with it, a new database given a log directory that already has a log. A
directory made without the option is as it was (no extra files). A replica
(--replica, and --replicas) follows a master whose log is in a log directory,
and is refused without the option; --unsafe-no-sync works with it. Ports are
20000 to 29999, below the ephemeral range. Needs psql."""
import glob
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
fails = []


def check(name, ok, detail=''):
    print(('ok   ' if ok else 'FAIL ') + name + ('' if ok else ': ' + detail), flush=True)
    if not ok:
        fails.append(name)


def free_port():
    while True:
        p = random.randrange(20000, 30000)
        ss = [socket.socket(), socket.socket()]
        try:
            ss[0].bind(('127.0.0.1', p))
            ss[1].bind(('127.0.0.1', p + 1))
            return p
        except OSError:
            pass
        finally:
            for x in ss:
                x.close()


def psql(port, sql):
    r = subprocess.run(['psql', '-h', '127.0.0.1', '-p', str(port), '-U', 'test', '-d', 'test', '-X', '-At',
                        '-v', 'ON_ERROR_STOP=1', '-c', sql], capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError(sql + ': ' + r.stderr)
    return r.stdout.strip()


def start(exe, data, port, flags, log):
    out = open(log, 'a')
    p = subprocess.Popen([exe, data, '127.0.0.1:%d' % port] + flags, stdout=out, stderr=out)
    out.close()
    end = time.time() + 60
    while time.time() < end:
        if p.poll() is not None:
            return p, False
        try:
            socket.create_connection(('127.0.0.1', port), 0.2).close()
            return p, True
        except OSError:
            time.sleep(0.02)
    return p, False


def stop(p, sig=signal.SIGTERM):
    p.send_signal(sig)
    try:
        return p.wait(60)
    except subprocess.TimeoutExpired:
        p.kill()
        p.wait()
        return 'hung'


def read(path):
    return open(path).read()


def segs(d):
    return sorted(os.path.basename(f) for f in glob.glob(os.path.join(d, 'log.*')))


def refused(exe, work, args, want, name):
    """Runs lexdb with args (no listener is reached: it must exit 1 at once with want in its message)."""
    log = os.path.join(work, 'refuse.log')
    open(log, 'w').close()
    p, up = start(exe, args[0], free_port(), args[1:], log)
    if up:
        stop(p)
    else:
        try:
            p.wait(30)
        except subprocess.TimeoutExpired:
            p.kill()
    text = read(log)
    check(name, not up and p.returncode == 1 and want in text, repr((up, p.returncode, text)))


def wait_rows(port, sql, want):
    seen = ''
    for _ in range(100):
        try:
            seen = psql(port, sql)
            if seen == want:
                return seen
        except RuntimeError:
            pass
        time.sleep(0.1)
    return seen


def main():
    work = tempfile.mkdtemp(prefix='lexdb-logdir-')
    exe = os.path.join(work, 'lexdb')
    r = subprocess.run([LXLC, os.path.join(ROOT, 'cmd', 'lexdb.lxl'), '-o', exe], capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit('building lexdb failed:\n' + r.stdout + r.stderr)
    data, logd = os.path.join(work, 'data'), os.path.join(work, 'wal', 'nested')
    log, port = os.path.join(work, 'a.log'), free_port()
    # a new data directory with a log directory (made, with its parents)
    p, up = start(exe, data, port, ['--log-dir', logd], log)
    check('new database with --log-dir starts', up, read(log))
    if up:
        psql(port, 'create table t(id int primary key, s text)')
        psql(port, "insert into t select g, repeat('x', 200) from generate_series(1, 2000) g")
        check('segments are in the log directory', 'log.1' in segs(logd), str(os.listdir(logd)))
        check('no segments in the data directory', segs(data) == [], str(os.listdir(data)))
        check('data file in the data directory only', os.path.exists(os.path.join(data, 'data.lxdb'))
              and not os.path.exists(os.path.join(logd, 'data.lxdb')))
        check('stops cleanly', stop(p) == 0)
    # restart: recover
    p, up = start(exe, data, port, ['--log-dir', logd], log)
    check('restart with the same --log-dir', up, read(log))
    if up:
        check('data kept', psql(port, 'select count(*) from t') == '2000')
        psql(port, "insert into t values (5000, 'after')")
        stop(p, signal.SIGKILL)          # no shutdown checkpoint: recovery replays the log directory's segments
    p, up = start(exe, data, port, ['--log-dir', logd], log)
    check('restart after SIGKILL', up, read(log))
    if up:
        check('log replayed from the log directory', psql(port, 'select count(*) from t') == '2001')
        stop(p)
    # refusals
    refused(exe, work, [data], 'start it with --log-dir', 'refused: made with --log-dir, started without')
    other = os.path.join(work, 'other')
    refused(exe, work, [data, '--log-dir', other], 'missing or is not this database', 'refused: another (new) log directory')
    check('the refusal made no log directory', not os.path.exists(other))
    os.makedirs(other)
    refused(exe, work, [data, '--log-dir', other], 'missing or is not this database', 'refused: another (empty) log directory')
    refused(exe, work, [data, '--log-dir', work], 'missing or is not this database', 'refused: the data directory'
            's parent as log directory')
    # another database's log directory
    data2, logd2 = os.path.join(work, 'data2'), os.path.join(work, 'wal2')
    p, up = start(exe, data2, port, ['--log-dir', logd2], log)
    check('second database starts', up, read(log))
    if up:
        psql(port, 'create table u(a int)')
        stop(p)
    refused(exe, work, [data, '--log-dir', logd2], 'belongs to another database', 'refused: another database\'s log directory')
    refused(exe, work, [os.path.join(work, 'data3'), '--log-dir', logd2], 'already holds a log', 'refused: a new database on a used log directory')
    # a log directory that has run a while: log.57 and no log.1
    old = os.path.join(work, 'old')
    os.makedirs(old)
    open(os.path.join(old, 'log.57'), 'w').close()
    refused(exe, work, [os.path.join(work, 'data6'), '--log-dir', old], 'already holds a log', 'refused: a log directory with only log.57')
    # the log directory lost
    moved = logd + '.gone'
    os.rename(logd, moved)
    refused(exe, work, [data, '--log-dir', logd], 'missing or is not this database', 'refused: the log directory is missing')
    os.rename(moved, logd)
    p, up = start(exe, data, port, ['--log-dir', logd], log)
    check('the log directory back: starts', up, read(log))
    if up:
        check('data intact', psql(port, 'select count(*) from t') == '2001')
        stop(p)
    # made without: not started with it, and nothing new in it
    plain = os.path.join(work, 'plain')
    p, up = start(exe, plain, port, [], log)
    check('plain database starts', up, read(log))
    if up:
        psql(port, 'create table t(a int)')
        psql(port, 'insert into t values (1)')
        stop(p)
        check('plain directory has no log-directory files', sorted(os.listdir(plain)) ==
              sorted(f for f in os.listdir(plain) if f in ('data.lxdb', 'lock', 'repl.sock') or f.startswith('log.')), str(os.listdir(plain)))
        check('plain directory has its segments', 'log.1' in segs(plain))
    refused(exe, work, [plain, '--log-dir', os.path.join(work, 'wal3')], 'start it without --log-dir', 'refused: made without --log-dir, started with it')
    p, up = start(exe, plain, port, [], log)
    check('plain database restarts', up, read(log))
    if up:
        check('plain data kept', psql(port, 'select count(*) from t') == '1')
        stop(p)
    # a replica of a master with a log directory
    data4, logd4 = os.path.join(work, 'data4'), os.path.join(work, 'wal4')
    log4, port4 = os.path.join(work, 'd.log'), free_port()
    p, up = start(exe, data4, port4, ['--log-dir', logd4, '--unsafe-no-sync'], log4)
    check('master with --log-dir and --unsafe-no-sync starts', up, read(log4))
    if up:
        psql(port4, 'create table t(id int primary key)')
        psql(port4, 'insert into t select g from generate_series(1, 100) g')
        rlog = os.path.join(work, 'r.log')
        rp, rup = start(exe, data4, port4 + 1, ['--replica', '--log-dir', logd4, '--unsafe-no-sync'], rlog)
        check('replica with --log-dir starts', rup, read(rlog))
        if rup:
            check('replica sees the rows', wait_rows(port4 + 1, 'select count(*) from t', '100') == '100')
            psql(port4, 'insert into t select g from generate_series(101, 3000) g')
            check('replica follows new commits from the log directory', wait_rows(port4 + 1, 'select count(*) from t', '3000') == '3000')
            stop(rp)
        # a replica without it is refused
        rlog2 = os.path.join(work, 'r2.log')
        open(rlog2, 'w').close()
        rp2 = subprocess.Popen([exe, '--replica', data4, '127.0.0.1:%d' % (port4 + 1)], stdout=open(rlog2, 'a'), stderr=subprocess.STDOUT)
        try:
            rc = rp2.wait(60)
        except subprocess.TimeoutExpired:
            rp2.kill()
            rc = 'hung'
        check('replica without --log-dir refused', rc == 1 and 'start it with --log-dir' in read(rlog2), repr((rc, read(rlog2))))
        stop(p)
    # supervised, with replicas: the option reaches every worker
    data5, logd5 = os.path.join(work, 'data5'), os.path.join(work, 'wal5')
    log5, port5 = os.path.join(work, 'e.log'), free_port()
    p, up = start(exe, data5, port5, ['--replicas', '1', '--log-dir', logd5], log5)
    check('supervised --replicas with --log-dir starts', up, read(log5))
    if up:
        psql(port5, 'create table t(id int primary key)')
        psql(port5, 'insert into t select g from generate_series(1, 500) g')
        check('supervised replica follows', wait_rows(port5 + 1, 'select count(*) from t', '500') == '500')
        check('supervised: segments in the log directory only', 'log.1' in segs(logd5) and segs(data5) == [])
        check('supervised stops', stop(p) == 0)
    shutil.rmtree(work, ignore_errors=True)
    print('FAILED: ' + ', '.join(fails) if fails else 'all passed')
    sys.exit(1 if fails else 0)


main()
