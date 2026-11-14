#!/usr/bin/env python3
"""Tests of lexdb's --unsafe-no-sync and --cache-mb (design/lexdb.md 9.123).

    python3 lexell/tests/lexdb/nosync.py

Bad option values are refused (exit 2, a message); the no-sync warning is
printed at start, also under --replicas (the supervisor and its workers);
with no-sync a SIGTERM stop and a restart keep every committed row; the
cache budget shows in the stop line. Ports are 20000 to 29999, below the
ephemeral range. Needs psql."""
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
WARN = 'WARNING: --unsafe-no-sync'
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


def stop(p):
    p.send_signal(signal.SIGTERM)
    try:
        return p.wait(60)
    except subprocess.TimeoutExpired:
        p.kill()
        p.wait()
        return 'hung'


def read(path):
    return open(path).read()


def main():
    work = tempfile.mkdtemp(prefix='lexdb-nosync-')
    exe = os.path.join(work, 'lexdb')
    r = subprocess.run([LXLC, os.path.join(ROOT, 'cmd', 'lexdb.lxl'), '-o', exe], capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit('building lexdb failed:\n' + r.stdout + r.stderr)
    # option parsing: refused with exit 2 and a message, before anything starts
    for bad in (['--cache-mb', '0'], ['--cache-mb', '-5'], ['--cache-mb', 'abc'], ['--cache-mb', '1048577'],
                ['--cache-mb', '99999999999999999999'], ['--cache-mb', '4000000000000'], ['--cache-mb', '']):
        r = subprocess.run([exe, os.path.join(work, 'bad')] + bad, capture_output=True, text=True, timeout=30)
        check('refuses ' + ' '.join(bad), r.returncode == 2 and '--cache-mb' in r.stderr, repr((r.returncode, r.stderr)))
    r = subprocess.run([exe, os.path.join(work, 'bad'), '--cache-mb'], capture_output=True, text=True, timeout=30)
    check('--cache-mb needs a value', r.returncode == 2 and 'usage' in r.stderr, r.stderr)
    r = subprocess.run([exe, os.path.join(work, 'bad'), '--unsafe-no-sync', '--bogus'], capture_output=True, text=True, timeout=30)
    check('unknown option refused', r.returncode == 2 and 'usage' in r.stderr and 'unsafe-no-sync' in r.stderr, r.stderr)
    # no-sync: the warning, and a clean stop and restart keep the data
    data, log, port = os.path.join(work, 'data'), os.path.join(work, 'a.log'), free_port()
    p, up = start(exe, data, port, ['--unsafe-no-sync', '--cache-mb', '16'], log)
    check('no-sync server starts', up, read(log))
    if up:
        psql(port, 'create table t(id int primary key, s text)')
        for i in range(50):
            psql(port, "insert into t values (%d, 'row %d')" % (i, i))
        psql(port, 'truncate t')
        psql(port, "insert into t select g, 'again ' || g from generate_series(1, 300) g")
        check('stops cleanly', stop(p) == 0)
        text = read(log)
        check('warning printed', WARN in text, text)
        check('cache budget in the stop line', 'of 16 MB' in text, text)
        p, up = start(exe, data, port, ['--unsafe-no-sync'], log)
        check('restarts', up, read(log))
        if up:
            check('data kept', psql(port, 'select count(*), sum(id) from t') == '300|45150')
            stop(p)
    # without the flag: no warning
    log2, port2 = os.path.join(work, 'b.log'), free_port()
    p, up = start(exe, os.path.join(work, 'data'), port2, [], log2)
    check('plain server starts', up, read(log2))
    if up:
        check('data kept without the flag too', psql(port2, 'select count(*) from t') == '300')
        stop(p)
        check('no warning without the flag', WARN not in read(log2))
    # supervised, with a replica: the flag reaches the workers; the replica sees the master's rows
    data3, log3, port3 = os.path.join(work, 'data3'), os.path.join(work, 'c.log'), free_port()
    p, up = start(exe, data3, port3, ['--replicas', '1', '--unsafe-no-sync', '--cache-mb', '8'], log3)
    check('supervised no-sync starts', up, read(log3))
    if up:
        psql(port3, 'create table t(id int primary key)')
        psql(port3, 'insert into t select g from generate_series(1, 100) g')
        seen = ''
        for _ in range(100):
            try:
                seen = psql(port3 + 1, 'select count(*) from t')
                if seen == '100':
                    break
            except RuntimeError:
                pass
            time.sleep(0.1)
        check('replica follows a no-sync master', seen == '100', seen)
        stop(p)
        check('supervised stop warning', WARN in read(log3))
    shutil.rmtree(work, ignore_errors=True)
    print('FAILED: ' + ', '.join(fails) if fails else 'all passed')
    sys.exit(1 if fails else 0)


main()
