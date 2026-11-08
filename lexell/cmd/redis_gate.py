#!/usr/bin/env python3
"""Runs the redis-cli gate against an in-process RESP server.

    python3 cmd/redis_gate.py [--c] [-k PATTERN]

It builds cmd/redis-cli.lxl (native, or through C with --c) and runs command
lines, pipe mode, -x and -r against a small RESP2 server, checking stdout,
stderr and the exit status. A live Redis is not needed; see
lib/tests/run/redis_live.lxl for the live path.
"""
import argparse
import os
import socket
import subprocess
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
LXLC = os.path.join(ROOT, 'lexell', 'compiler', 'out', 'lxlc')


def read_line(f):
    b = f.readline()
    if not b:
        return None
    if not b.endswith(b'\r\n'):
        return None
    return b[:-2]


def read_cmd(f):
    line = read_line(f)
    if line is None or not line.startswith(b'*'):
        return None
    n = int(line[1:])
    out = []
    for _ in range(n):
        h = read_line(f)
        if h is None or not h.startswith(b'$'):
            return None
        k = int(h[1:])
        data = f.read(k)
        if data is None or len(data) != k:
            return None
        if f.read(2) != b'\r\n':
            return None
        out.append(data)
    return out


def bulk(s):
    if s is None:
        return b'$-1\r\n'
    return b'$%d\r\n' % len(s) + s + b'\r\n'


def simple(s):
    return b'+' + s + b'\r\n'


def integer(n):
    return b':%d\r\n' % n


def err(s):
    return b'-' + s + b'\r\n'


class Server:
    def __init__(self):
        self.kv = {}
        self.h = {}
        self.l = {}
        self.sock = socket.socket()
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(('127.0.0.1', 0))
        self.sock.listen(16)
        self.port = self.sock.getsockname()[1]
        self.stop = False
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        while not self.stop:
            try:
                c, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self.serve, args=(c,), daemon=True).start()

    def serve(self, c):
        f = c.makefile('rb')
        try:
            while True:
                args = read_cmd(f)
                if args is None:
                    return
                out = self.dispatch(args)
                if out is None:
                    return
                c.sendall(out)
        finally:
            c.close()

    def dispatch(self, args):
        cmd = args[0].decode().upper()
        a = [x.decode('utf-8', 'surrogateescape') for x in args[1:]]
        if cmd == 'PING':
            return simple(b'PONG')
        if cmd == 'ECHO':
            return bulk(args[1])
        if cmd == 'SET':
            self.kv[a[0]] = a[1]
            return simple(b'OK')
        if cmd == 'GET':
            return bulk(self.kv.get(a[0], '').encode() if a[0] in self.kv else None)
        if cmd == 'DEL':
            n = 0
            for k in a:
                if k in self.kv:
                    del self.kv[k]
                    n += 1
            return integer(n)
        if cmd == 'INCR':
            n = int(self.kv.get(a[0], '0')) + 1
            self.kv[a[0]] = str(n)
            return integer(n)
        if cmd == 'RPUSH':
            self.l.setdefault(a[0], []).extend(a[1:])
            return integer(len(self.l[a[0]]))
        if cmd == 'LRANGE':
            xs = self.l.get(a[0], [])
            start, stop = int(a[1]), int(a[2])
            if stop < 0:
                stop = len(xs) + stop
            out = b'*%d\r\n' % len(xs[start:stop + 1])
            for x in xs[start:stop + 1]:
                out += bulk(x.encode())
            return out
        if cmd == 'HSET':
            h = self.h.setdefault(a[0], {})
            h[a[1]] = a[2]
            return integer(1)
        if cmd == 'HGET':
            h = self.h.get(a[0], {})
            return bulk(h.get(a[1], '').encode() if a[1] in h else None)
        if cmd == 'HGETALL':
            h = self.h.get(a[0], {})
            out = b'*%d\r\n' % (2 * len(h))
            for k, v in h.items():
                out += bulk(k.encode()) + bulk(v.encode())
            return out
        if cmd == 'QUIT':
            return simple(b'OK')
        return err(b"ERR unknown command '" + args[0] + b"'")


def build(through_c, out):
    cmd = [LXLC, os.path.join(HERE, 'redis-cli.lxl'), '--c' if through_c else '--native', '-o', out]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise SystemExit('build failed:\n' + p.stdout + p.stderr)


def run(exe, args, stdin=''):
    p = subprocess.run([exe] + args, input=stdin, capture_output=True, text=True,
                       env=dict(os.environ, LXL_CHECK='1'), timeout=10)
    return p.returncode, p.stdout, p.stderr


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument('--c', action='store_true', help='build through the C backend')
    ap.add_argument('-k', default=None, help='only cases whose name contains this')
    a = ap.parse_args(argv)
    srv = Server()
    base = ['-p', str(srv.port)]
    cases = [
        ('ping', ['ping'], '', 0, 'PONG\n', ''),
        ('set', ['set', 'k', 'v'], '', 0, 'OK\n', ''),
        ('get', ['get', 'k'], '', 0, 'v\n', ''),
        ('missing', ['get', 'missing'], '', 0, '\n', ''),
        ('formatted', ['--no-raw', 'get', 'k'], '', 0, '"v"\n', ''),
        ('list', ['lrange', 'l', '0', '-1'], '', 0, '\n', ''),
        ('push', ['rpush', 'l', 'a', 'b'], '', 0, '2\n', ''),
        ('list2', ['lrange', 'l', '0', '-1'], '', 0, 'a\nb\n', ''),
        ('listfmt', ['--no-raw', 'lrange', 'l', '0', '-1'], '', 0, '1) "a"\n2) "b"\n', ''),
        ('hash', ['hset', 'h', 'f', 'v'], '', 0, '1\n', ''),
        ('hash2', ['hgetall', 'h'], '', 0, 'f\nv\n', ''),
        ('hashfmt', ['--no-raw', 'hgetall', 'h'], '', 0, '1) "f"\n2) "v"\n', ''),
        ('error', ['nope'], '', 1, '', '(error) ERR unknown command \'nope\'\n'),
        ('repeat', ['-r', '2', 'incr', 'c'], '', 0, '1\n2\n', ''),
        ('readlast', ['-x', 'echo'], 'hello\n', 0, 'hello\n', ''),
        ('pipe', [], 'ping\nset p 7\nget p\n', 0, 'PONG\nOK\n7\n', ''),
        ('pipefmt', ['--no-raw'], 'ping\nget p\n', 0, 'PONG\n"7"\n', ''),
    ]
    with tempfile.TemporaryDirectory(prefix='redisgate_') as tmp:
        exe = os.path.join(tmp, 'redis-cli')
        build(a.c, exe)
        passed = failed = skipped = 0
        for name, args, stdin, code, out, err in cases:
            if a.k and a.k not in name:
                skipped += 1
                continue
            try:
                rc, so, se = run(exe, base + args, stdin)
            except subprocess.TimeoutExpired:
                print('FAIL %s: timeout' % name)
                failed += 1
                continue
            want = (code, out, err)
            got = (rc, so, se)
            if got != want:
                print('FAIL %s\n  want: %r\n  got:  %r' % (name, want, got))
                failed += 1
            else:
                passed += 1
        print('%d passed, %d failed, %d skipped' % (passed, failed, skipped))
        srv.stop = True
        srv.sock.close()
        return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
