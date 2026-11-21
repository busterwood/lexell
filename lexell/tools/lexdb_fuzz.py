#!/usr/bin/env python3
"""lexdb_fuzz.py: a differential and metamorphic SQL fuzzer for lexdb.

Random schemas, data and queries; each query runs under several lexdb
configurations and against PostgreSQL, and is rewritten into equivalent
forms (TLP, NoREC). A difference is reduced (query and data) to a minimal
repro. See design/lexdb-fuzz.md for the checks, the options and the bugs
found.

    lexdb_fuzz.py build [--out BIN]          the switch-aware binary (env LEXDB_FUZZ_*)
    lexdb_fuzz.py run --bin BIN [options]    fuzz for --duration seconds
    lexdb_fuzz.py report DIR                 the distinct failures of a run
    lexdb_fuzz.py repro CASE.json --bin BIN  rerun a case under every configuration

No dependencies beyond Python 3 and the PostgreSQL 18 server binaries
(initdb, postgres) on PATH; it speaks the wire protocol itself.
"""

import argparse
import copy
import glob
import json
import multiprocessing
import os
import random
import re
import shutil
import signal
import socket
import struct
import subprocess
import sys
import time
from decimal import Decimal, InvalidOperation

HERE = os.path.dirname(os.path.abspath(__file__))
LEXELL = os.path.dirname(HERE)

# ---------------------------------------------------------------- wire client


class WireError(Exception):
    pass


class Res:
    """A statement's outcome: rows, error, crash or hang."""

    def __init__(self, kind, cols=None, oids=None, rows=None, code=None, msg=None, tag=None):
        self.kind, self.cols, self.oids, self.rows = kind, cols or [], oids or [], rows or []
        self.code, self.msg, self.tag = code, msg, tag

    def brief(self, n=12):
        if self.kind == 'rows':
            s = '%d rows' % len(self.rows)
            body = ['|'.join('NULL' if v is None else v for v in r) for r in self.rows[:n]]
            if len(self.rows) > n:
                body.append('...')
            return s + (': ' + '; '.join(body) if body else '')
        if self.kind == 'error':
            return 'ERROR %s: %s' % (self.code, self.msg)
        return '%s: %s' % (self.kind.upper(), self.msg)

    def js(self):
        d = {'kind': self.kind}
        if self.kind == 'rows':
            d['oids'] = self.oids
            d['rows'] = self.rows[:200]
            d['nrows'] = len(self.rows)
        else:
            d['code'], d['msg'] = self.code, self.msg
        return d


class Conn:
    """The PostgreSQL wire protocol, simple queries only, trust auth."""

    def __init__(self, host, port, user, db, timeout):
        self.s = socket.create_connection((host, port), timeout=timeout)
        self.s.settimeout(timeout)
        self.s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.buf = b''
        self.pos = 0
        params = b'user\0' + user.encode() + b'\0database\0' + db.encode() + b'\0client_encoding\0UTF8\0\0'
        body = struct.pack('!i', 196608) + params
        self.s.sendall(struct.pack('!i', len(body) + 4) + body)
        while True:
            t, p = self._msg()
            if t == b'R':
                code = struct.unpack('!i', p[:4])[0]
                if code != 0:
                    raise WireError('authentication method %d is not supported' % code)
            elif t == b'E':
                raise WireError('startup: %s' % (self._err(p),))
            elif t == b'Z':
                break

    def close(self):
        try:
            self.s.sendall(b'X\0\0\0\4')
        except OSError:
            pass
        try:
            self.s.close()
        except OSError:
            pass

    def _fill(self, n):
        while len(self.buf) - self.pos < n:
            chunk = self.s.recv(1 << 17)
            if not chunk:
                raise WireError('the server closed the connection')
            if self.pos:
                self.buf = self.buf[self.pos:]
                self.pos = 0
            self.buf += chunk

    def _msg(self):
        self._fill(5)
        t = self.buf[self.pos:self.pos + 1]
        ln = struct.unpack_from('!i', self.buf, self.pos + 1)[0]
        self._fill(1 + ln)
        p = self.buf[self.pos + 5:self.pos + 1 + ln]
        self.pos += 1 + ln
        return t, p

    @staticmethod
    def _err(p):
        f = {}
        for part in p.split(b'\0'):
            if part:
                f[part[:1]] = part[1:].decode('utf-8', 'replace')
        return f.get(b'C', '?'), f.get(b'M', '?')

    def query(self, sql, maxrows=200000):
        b = sql.encode() + b'\0'
        self.s.sendall(b'Q' + struct.pack('!i', len(b) + 4) + b)
        cols, oids, rows, err, tag = [], [], [], None, None
        while True:
            t, p = self._msg()
            if t == b'D':
                if len(rows) >= maxrows:
                    continue
                n = struct.unpack_from('!h', p, 0)[0]
                o = 2
                row = []
                for _ in range(n):
                    ln = struct.unpack_from('!i', p, o)[0]
                    o += 4
                    if ln < 0:
                        row.append(None)
                    else:
                        row.append(p[o:o + ln].decode('utf-8', 'replace'))
                        o += ln
                rows.append(tuple(row))
            elif t == b'T':
                n = struct.unpack_from('!h', p, 0)[0]
                o = 2
                cols, oids = [], []
                for _ in range(n):
                    z = p.index(b'\0', o)
                    cols.append(p[o:z].decode('utf-8', 'replace'))
                    o = z + 1
                    oids.append(struct.unpack_from('!i', p, o + 6)[0])
                    o += 18
            elif t == b'C':
                tag = p[:-1].decode()
            elif t == b'E':
                err = self._err(p)
            elif t == b'Z':
                break
        if err:
            return Res('error', code=err[0], msg=err[1])
        return Res('rows', cols=cols, oids=oids, rows=rows, tag=tag)


# ---------------------------------------------------------------- servers

STMT_TIMEOUT_MS = 5000
SOCK_TIMEOUT = 30.0


def popen_pinned(cmd, cpus, log, env=None):
    return subprocess.Popen(['nice', '-n', '15', 'taskset', '-c', cpus] + cmd, stdout=log, stderr=log,
                            env=env, start_new_session=True)


def wait_port(port, proc, secs=30):
    t0 = time.time()
    while time.time() - t0 < secs:
        if proc is not None and proc.poll() is not None:
            return False
        try:
            s = socket.create_connection(('127.0.0.1', port), timeout=1)
            s.close()
            return True
        except OSError:
            time.sleep(0.05)
    return False


class Lexdb:
    """One lexdb server: its own data directory, port, CPUs, environment; a
    connection per configuration (a list of SET statements)."""

    def __init__(self, name, binary, root, port, cpus, env, cfgs):
        self.name, self.binary, self.port, self.cpus = name, binary, port, cpus
        self.dir = os.path.join(root, 'data-' + name)
        self.logpath = os.path.join(root, 'srv-' + name + '.log')
        self.env = dict(os.environ)
        for k in list(self.env):
            if k.startswith('LEXDB_FUZZ_'):
                del self.env[k]
        self.env.update(env)
        self.cfgs = cfgs
        self.conns = {}
        self.p = None
        self.loaded = None      # the key of the setup loaded
        self.starts = 0

    def start(self):
        self.stop()
        shutil.rmtree(self.dir, ignore_errors=True)
        log = open(self.logpath, 'ab')
        log.write(b'--- start %s\n' % time.strftime('%H:%M:%S').encode())
        log.flush()
        self.p = popen_pinned([self.binary, '--unsafe-no-sync', '--cache-mb', '64', self.dir,
                               '127.0.0.1:%d' % self.port], self.cpus, log, self.env)
        log.close()
        self.loaded = None
        self.starts += 1
        if not wait_port(self.port, self.p):
            raise RuntimeError('lexdb %s did not start; see %s' % (self.name, self.logpath))

    def alive(self):
        return self.p is not None and self.p.poll() is None

    def stop(self):
        for c in self.conns.values():
            c.close()
        self.conns = {}
        if self.p is not None and self.p.poll() is None:
            try:
                os.killpg(self.p.pid, signal.SIGTERM)
                self.p.wait(5)
            except (subprocess.TimeoutExpired, ProcessLookupError):
                try:
                    os.killpg(self.p.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                self.p.wait()
        self.p = None

    def log_tail(self, n=6):
        try:
            with open(self.logpath, 'rb') as f:
                f.seek(0, 2)
                f.seek(max(0, f.tell() - 4000))
                lines = f.read().decode('utf-8', 'replace').splitlines()
            return ' | '.join(lines[-n:])
        except OSError:
            return ''

    def conn(self, cfg):
        c = self.conns.get(cfg)
        if c is None:
            c = Conn('127.0.0.1', self.port, 'lexdb', 'lexdb', SOCK_TIMEOUT)
            for s in ['set statement_timeout = %d' % STMT_TIMEOUT_MS] + self.cfgs[cfg]:
                r = c.query(s)
                if r.kind != 'rows':
                    raise RuntimeError('%s: %s: %s' % (self.name, s, r.brief()))
            self.conns[cfg] = c
        return c

    def run(self, cfg, sql):
        try:
            r = self.conn(cfg).query(sql)
        except (WireError, OSError, struct.error) as e:
            hang = isinstance(e, socket.timeout)
            for c in self.conns.values():
                c.close()
            self.conns = {}
            time.sleep(0.2)
            alive = self.alive()
            if hang or not alive:
                state = 'alive' if alive else 'exited %s' % self.p.returncode
            else:
                state = 'alive (the session was cut off)'
            r = Res('hang' if hang else 'crash', msg='%s; server %s; log: %s' % (e, state, self.log_tail()))
            self.loaded = None
            self.start()            # a fresh server; the caller reloads
            return r
        if r.kind == 'error' and r.code == '57014':
            return Res('hang', msg='statement timeout (%d ms): %s' % (STMT_TIMEOUT_MS, r.msg))
        return r


class Postgres:
    """The scratch PostgreSQL 18: its own data directory (initdb --locale=C),
    a database per worker."""

    def __init__(self, root, port, cpus):
        self.root, self.port, self.cpus = root, port, cpus
        self.dir = os.path.join(root, 'pg')
        self.sock = os.path.join(root, 'pgsock')
        self.p = None

    def start(self):
        os.makedirs(self.sock, exist_ok=True)
        if not os.path.exists(os.path.join(self.dir, 'PG_VERSION')):
            subprocess.run(['initdb', '-D', self.dir, '-U', 'fuzz', '--auth=trust', '--locale=C', '-E', 'UTF8'],
                           check=True, stdout=subprocess.DEVNULL)
        log = open(os.path.join(self.root, 'pg.log'), 'ab')
        self.p = popen_pinned(['postgres', '-D', self.dir, '-p', str(self.port), '-k', self.sock,
                               '-c', 'listen_addresses=127.0.0.1', '-c', 'fsync=off', '-c', 'synchronous_commit=off',
                               '-c', 'full_page_writes=off', '-c', 'shared_buffers=128MB', '-c', 'max_connections=60',
                               '-c', 'max_parallel_workers_per_gather=0', '-c', 'jit=off',
                               '-c', 'autovacuum=off'], self.cpus, log)
        log.close()
        if not wait_port(self.port, self.p):
            raise RuntimeError('PostgreSQL did not start; see %s/pg.log' % self.root)
        for _ in range(50):
            try:
                Conn('127.0.0.1', self.port, 'fuzz', 'postgres', 5).close()
                return
            except (WireError, OSError):
                time.sleep(0.2)

    def ensure_db(self, name):
        c = Conn('127.0.0.1', self.port, 'fuzz', 'postgres', 30)
        r = c.query("select 1 from pg_database where datname = '%s'" % name)
        if not r.rows:
            c.query('create database %s' % name)
        c.close()

    def stop(self):
        if self.p is not None and self.p.poll() is None:
            self.p.send_signal(signal.SIGINT)
            try:
                self.p.wait(20)
            except subprocess.TimeoutExpired:
                self.p.kill()
                self.p.wait()


class PgClient:
    def __init__(self, port, db):
        self.port, self.db, self.c, self.loaded = port, db, None, None

    def run(self, sql):
        for attempt in range(2):
            try:
                if self.c is None:
                    self.c = Conn('127.0.0.1', self.port, 'fuzz', self.db, SOCK_TIMEOUT)
                    self.c.query('set statement_timeout = %d' % STMT_TIMEOUT_MS)
                    self.c.query('set extra_float_digits = 0')
                return self.c.query(sql)
            except (WireError, OSError, struct.error) as e:
                self.c = None
                self.loaded = None
                if attempt:
                    return Res('crash', msg='postgres: %s' % e)
        return Res('crash', msg='postgres')


# ---------------------------------------------------------------- schema and data

LETTERS = 'abcdefgh'
INT_SMALL = list(range(-3, 13))
NUM_VALS = ['0', '1', '-1', '1.5', '2.25', '-0.5', '10', '0.01', '3.333', '2.50', '7']
TEXT_VALS = ['a', 'b', 'c', 'ab', 'ba', 'A', 'B', '', ' a', 'a ', 'abc', 'a%b', 'a_c', 'z', 'Ab', 'bb']
FLOAT_VALS = ['0', '0.5', '-1.25', '3', '1e10', '2.5', '-0']
DATE_VALS = ['2024-01-%02d' % d for d in range(1, 11)] + ['2023-12-31', '2024-02-29', '2000-01-01']
BIG = {'int': ['2147483647', '-2147483648'], 'bigint': ['9223372036854775807', '-9223372036854775807'],
       'smallint': ['32767', '-32768']}

COL_TYPES = [('int', 'int', 25), ('bigint', 'int', 7), ('smallint', 'int', 2), ('numeric', 'num', 5),
             ('numeric(6,2)', 'num', 6), ('text', 'text', 18), ('varchar(4)', 'text', 5), ('char(3)', 'text', 2),
             ('date', 'date', 7), ('bool', 'bool', 9), ('float8', 'float', 2)]


def wchoice(r, items):
    tot = sum(i[-1] for i in items)
    x = r.random() * tot
    for it in items:
        x -= it[-1]
        if x < 0:
            return it
    return items[-1]


def q_text(s):
    return "'" + s.replace("'", "''") + "'"


def type_len(sqltype):
    m = re.match(r'(?:varchar|char)\((\d+)\)', sqltype)
    return int(m.group(1)) if m else None


def gen_value(r, sqltype, cat):
    if cat == 'int':
        if r.random() < 0.03:
            return r.choice(BIG.get(sqltype, BIG['int']))
        return str(r.choice(INT_SMALL))
    if cat == 'num':
        return r.choice(NUM_VALS)
    if cat == 'text':
        n = type_len(sqltype)
        vals = [v for v in TEXT_VALS if n is None or len(v) <= n]
        return q_text(r.choice(vals))
    if cat == 'date':
        return q_text(r.choice(DATE_VALS))
    if cat == 'bool':
        return r.choice(['true', 'false'])
    if cat == 'float':
        return r.choice(FLOAT_VALS)
    raise ValueError(cat)


class Table:
    def __init__(self, name, cols, pk, rows):
        self.name, self.cols, self.pk, self.rows = name, cols, pk, rows   # cols: [name, sqltype, cat, notnull]

    def create_sql(self):
        parts = []
        for n, t, c, nn in self.cols:
            s = '%s %s' % (n, t)
            if n == self.pk:
                s += ' primary key'
            elif nn:
                s += ' not null'
            parts.append(s)
        return 'create table %s (%s)' % (self.name, ', '.join(parts))

    def insert_sql(self):
        if not self.rows:
            return None
        return 'insert into %s values %s' % (self.name, ', '.join('(' + ', '.join(row) + ')' for row in self.rows))


class Setup:
    """The tables, their rows and the statements after the inserts (indexes,
    deletes and updates, views, ANALYZE)."""

    def __init__(self, tables, post):
        self.tables, self.post = tables, post     # post: [kind, sql]

    def stmts(self, noidx=False):
        out = [t.create_sql() for t in self.tables]
        out += [s for s in (t.insert_sql() for t in self.tables) if s]
        out += [s for k, s in self.post if not (noidx and k == 'index')]
        return out

    def key(self, noidx=False):
        return '\n'.join(self.stmts(noidx))

    def views(self):
        return [re.match(r'create view (\w+)', s).group(1) for k, s in self.post if k == 'view']

    def js(self):
        return {'tables': [[t.name, t.cols, t.pk, t.rows] for t in self.tables], 'post': self.post}

    @staticmethod
    def from_js(d):
        d = copy.deepcopy(d)
        return Setup([Table(*t) for t in d['tables']], [list(p) for p in d['post']])


DROPS = ['drop view if exists v%d' % i for i in range(3)] + ['drop table if exists t%d' % i for i in range(5)]


def gen_setup(r):
    ntab = r.choice([1, 2, 2, 3, 3, 3, 4])
    tables, post = [], []
    for ti in range(ntab):
        L = LETTERS[ti]
        ncol = r.randint(2, 6)
        cols = []
        for j in range(ncol):
            t, c, _ = wchoice(r, COL_TYPES)
            cols.append([L + str(j), t, c, r.random() < 0.1])
        pk = None
        if cols[0][2] == 'int' and r.random() < 0.6:
            pk = cols[0][0]
        nrows = r.choice([0, 1, 2, 3, 4, 6, 8, 10, 12, 15, 20, 20])
        rows = []
        pkvals = r.sample(range(-2, 40), nrows) if pk else None
        nullp = r.choice([0.0, 0.1, 0.2, 0.35])
        for k in range(nrows):
            row = []
            for j, (n, t, c, nn) in enumerate(cols):
                if n == pk:
                    row.append(str(pkvals[k]))
                elif not nn and r.random() < nullp:
                    row.append('NULL')
                else:
                    row.append(gen_value(r, t, c))
            rows.append(row)
        tab = Table('t%d' % ti, cols, pk, rows)
        tables.append(tab)
        # indexes
        for k in range(r.choice([0, 0, 1, 1, 2, 3])):
            cand = [cc for cc in cols if cc[2] != 'float']
            if not cand:
                break
            pick = r.sample(cand, min(len(cand), r.choice([1, 1, 2, 2, 3])))
            if r.random() < 0.1:
                cc = pick[0]
                ex = {'int': '(%s + 1)', 'text': 'lower(%s)', 'num': '(%s * 2)', 'date': '(%s + 1)',
                      'bool': '(not %s)'}[cc[2]] % cc[0]
                target = '(%s)' % ex
            else:
                target = ', '.join(cc[0] for cc in pick)
            s = 'create index %s_i%d on %s (%s)' % (tab.name, k, tab.name, target)
            if r.random() < 0.2:
                cc = r.choice(cols)
                if cc[2] == 'bool':
                    s += ' where %s' % cc[0]
                elif cc[2] == 'int':
                    s += ' where %s > %d' % (cc[0], r.choice([0, 2, 5]))
                else:
                    s += ' where %s is not null' % cc[0]
            post.append(['index', s])
        # deletes and updates after the load (tombstones, changed rows)
        if rows and r.random() < 0.25:
            cc = r.choice(cols)
            post.append(['dml', 'delete from %s where %s = %s' % (tab.name, cc[0], gen_value(r, cc[1], cc[2]))])
        if rows and r.random() < 0.25:
            cands = [cc for cc in cols if cc[0] != pk]
            if cands:
                cc = r.choice(cands)
                v = 'NULL' if (not cc[3] and r.random() < 0.3) else gen_value(r, cc[1], cc[2])
                w = r.choice(cols)
                post.append(['dml', 'update %s set %s = %s where %s = %s' % (tab.name, cc[0], v, w[0],
                                                                           gen_value(r, w[1], w[2]))])
    # a view
    if r.random() < 0.3:
        tab = r.choice(tables)
        cs = r.sample(tab.cols, r.randint(1, len(tab.cols)))
        s = 'create view v0 as select %s from %s' % (', '.join(c[0] for c in cs), tab.name)
        ints = [c for c in tab.cols if c[2] == 'int']
        if ints and r.random() < 0.7:
            s += ' where %s > %d' % (r.choice(ints)[0], r.choice([0, 1, 3]))
        post.append(['view', s])
    if r.random() < 0.6:
        post.append(['analyze', 'analyze'])
    return Setup(tables, post)


def setup_relations(setup):
    """name -> [(col, cat)] for the tables and views."""
    rel = {}
    for t in setup.tables:
        rel[t.name] = [(c[0], c[2]) for c in t.cols]
    for k, s in setup.post:
        if k == 'view':
            m = re.match(r'create view (\w+) as select (.*?) from (\w+)', s)
            base = {c: cat for c, cat in rel.get(m.group(3), [])}
            rel[m.group(1)] = [(c.strip(), base[c.strip()]) for c in m.group(2).split(',')]
    return rel


# ---------------------------------------------------------------- query AST

class E:
    """An expression: fmt with {0}.. for its kids (expressions or queries)."""
    __slots__ = ('fmt', 'kids', 'cat', 'agg', 'win', 'lit', 'fixed')

    def __init__(self, fmt, kids, cat, agg=None, win=False, lit=False, fixed=False):
        self.fmt, self.kids, self.cat, self.agg, self.win, self.lit, self.fixed = fmt, kids, cat, agg, win, lit, fixed

    def sql(self):
        if not self.kids:
            return self.fmt
        return self.fmt.format(*[k.sql() for k in self.kids])


class Q:
    """A SELECT: ctes, items, from, where, group, having, a set operation,
    order (positions), limit, offset."""

    def __init__(self):
        self.ctes = []        # [name, Q]
        self.distinct = False
        self.items = []       # [E, alias]
        self.frm = []         # From nodes
        self.where = None
        self.group = []
        self.having = None
        self.setop = None     # [op, Q]
        self.order = []       # [pos, dir]
        self.limit = None
        self.offset = None
        self.rowctx = None    # the generator's contexts (TLP)
        self.grpctx = None

    def core(self):
        s = 'select ' + ('distinct ' if self.distinct else '')
        s += ', '.join('%s as %s' % (e.sql(), a) for e, a in self.items)
        if self.frm:
            s += ' from ' + ', '.join(f.sql() for f in self.frm)
        if self.where is not None:
            s += ' where ' + self.where.sql()
        if self.group:
            s += ' group by ' + ', '.join(g.sql() for g in self.group)
        if self.having is not None:
            s += ' having ' + self.having.sql()
        return s

    def sql(self):
        s = ''
        if self.ctes:
            s = 'with ' + ', '.join('%s as (%s)' % (n, q.sql()) for n, q in self.ctes) + ' '
        if self.setop:
            s += '(%s) %s (%s)' % (self.core(), self.setop[0], self.setop[1].sql())
        else:
            s += self.core()
        if self.order:
            s += ' order by ' + ', '.join('%d%s' % (p, d) for p, d in self.order)
            if self.limit is not None:
                s += ' limit %d' % self.limit
            if self.offset is not None:
                s += ' offset %d' % self.offset
        return s

    def ordered(self):
        return bool(self.order) and sorted(p for p, d in self.order) == list(range(1, len(self.items) + 1))

    def has_window(self):
        return any(e.win for e, a in self.items) or any(_has_win(e) for e, a in self.items)

    def is_agg(self):
        return bool(self.group) or self.having is not None or any(_has_agg(e) for e, a in self.items)


def _has_agg(e):
    if not isinstance(e, E):
        return False
    return e.agg is not None or any(_has_agg(k) for k in e.kids if isinstance(k, E))


def _has_win(e):
    if not isinstance(e, E):
        return False
    return e.win or any(_has_win(k) for k in e.kids if isinstance(k, E))


class FT:
    def __init__(self, name, alias):
        self.name, self.alias = name, alias

    def sql(self):
        return '%s as %s' % (self.name, self.alias)


class FD:
    def __init__(self, q, alias, lateral):
        self.q, self.alias, self.lateral = q, alias, lateral

    def sql(self):
        return '%s(%s) as %s' % ('lateral ' if self.lateral else '', self.q.sql(), self.alias)


class FJ:
    def __init__(self, kind, left, right, on):
        self.kind, self.left, self.right, self.on = kind, left, right, on

    def sql(self):
        s = '%s %s %s' % (self.left.sql(), self.kind, self.right.sql())
        if self.on is not None:
            s += ' on ' + self.on.sql()
        return s


# ---------------------------------------------------------------- generator

NUMERIC_CATS = ('int', 'num', 'float')
NULLLIT = {'int': 'cast(null as int)', 'num': 'cast(null as numeric)', 'text': 'cast(null as text)',
           'date': 'cast(null as date)', 'bool': 'cast(null as bool)', 'float': 'cast(null as float8)'}
SIMPLE_LIT = {'int': '1', 'num': '1.5', 'text': "'a'", 'date': "date '2024-01-03'", 'bool': 'true',
              'float': 'cast(0.5 as float8)'}
LIKE_PATS = ["'a%'", "'%b'", "'_'", "'%'", "'a_'", "'%a%'", "'A%'", "'a\\%%'", "''", "'%_'"]


class Ctx:
    def __init__(self, cols, agg=None, win=False, nosub=False, depth=0, outer=None):
        self.cols = cols        # [(ref, cat)]
        self.agg = agg          # the row context of an aggregate's argument, or None
        self.win = win
        self.nosub = nosub
        self.depth = depth      # subquery nesting
        self.outer = outer or []

    def all_cols(self):
        return self.cols + self.outer


class Gen:
    def __init__(self, r, setup, opts=None):
        self.r = r
        self.setup = setup
        self.rel = setup_relations(setup)
        self.n = 0
        self.opts = opts or {}
        self.ctes = {}         # name -> [(col, cat)]

    def alias(self, p):
        self.n += 1
        return '%s%d' % (p, self.n)

    # -- literals and leaves
    def lit(self, cat, nullp=0.08):
        r = self.r
        if r.random() < nullp:
            return E(NULLLIT[cat], [], cat, lit=True)
        if cat == 'int':
            v = r.choice(INT_SMALL) if r.random() > 0.02 else r.choice([2147483647, -2147483648])
            return E('(%d)' % v if v < 0 else str(v), [], cat, lit=True)
        if cat == 'num':
            v = r.choice(NUM_VALS)
            return E('(%s)' % v if v.startswith('-') else v, [], cat, lit=True)
        if cat == 'text':
            return E(q_text(r.choice(TEXT_VALS)), [], cat, lit=True)
        if cat == 'date':
            return E("date '%s'" % r.choice(DATE_VALS), [], cat, lit=True)
        if cat == 'bool':
            return E(r.choice(['true', 'false']), [], cat, lit=True)
        if cat == 'float':
            return E('cast(%s as float8)' % r.choice(FLOAT_VALS), [], cat, lit=True)

    def colref(self, ctx, cat):
        cs = [c for c in ctx.cols if c[1] == cat]
        if ctx.outer and self.r.random() < 0.3:
            cs = cs + [c for c in ctx.outer if c[1] == cat]
        if not cs:
            cs = [c for c in ctx.outer if c[1] == cat]
        if not cs:
            return None
        ref, c = self.r.choice(cs)
        return E(ref, [], c)

    def leaf(self, ctx, cat):
        if self.r.random() < 0.75:
            c = self.colref(ctx, cat)
            if c is not None:
                return c
        if cat == 'bool' and self.r.random() < 0.8:
            # a comparison rather than a bare TRUE or FALSE
            k = self.pick_cat(ctx, ['int', 'int', 'num', 'text', 'date'])
            c = self.colref(ctx, k)
            if c is not None:
                op = self.r.choice(['=', '<>', '<', '<=', '>', '>=', '='])
                return E('({0} %s {1})' % op, [c, self.lit(k, 0.05)], 'bool')
        return self.lit(cat)

    def cats_of(self, ctx):
        return sorted(set(c for _, c in ctx.all_cols()))

    def pick_cat(self, ctx, allow=None):
        have = self.cats_of(ctx)
        if allow:
            have = [c for c in have if c in allow] or list(allow)
        if not have or self.r.random() < 0.1:
            return self.r.choice(list(allow) if allow else ['int', 'int', 'text', 'num', 'date', 'bool'])
        return self.r.choice(have)

    # -- expressions
    def expr(self, ctx, cat, d):
        r = self.r
        if d <= 0 or r.random() < 0.3:
            if ctx.agg is not None and r.random() < 0.4:
                a = self.aggregate(ctx, cat, d)
                if a is not None:
                    return a
            return self.leaf(ctx, cat)
        if ctx.agg is not None and r.random() < 0.35:
            a = self.aggregate(ctx, cat, d)
            if a is not None:
                return a
        if not ctx.nosub and ctx.depth < 2 and cat != 'bool' and r.random() < 0.06:
            return self.scalar_sub(ctx, cat)
        return getattr(self, 'e_' + cat)(ctx, d)

    def E(self, fmt, kinds, cat, ctx, d, **kw):
        kids = [self.expr(ctx, k, d - 1) for k in kinds]
        return E(fmt, kids, cat, **kw)

    def e_int(self, ctx, d):
        r = self.r
        x = r.random()
        if x < 0.25:
            return self.E('(%s)' % ('{0} ' + r.choice(['+', '-', '*', '+', '-']) + ' {1}'), ['int', 'int'], 'int', ctx, d)
        if x < 0.3:
            return self.E('(- {0})', ['int'], 'int', ctx, d)
        if x < 0.36:
            if r.random() < 0.15:
                return self.E('({0} %s {1})' % r.choice(['/', '%']), ['int', 'int'], 'int', ctx, d)
            return self.E('({0} %s nullif({1}, 0))' % r.choice(['/', '%']), ['int', 'int'], 'int', ctx, d)
        if x < 0.4:
            return self.E('abs({0})', ['int'], 'int', ctx, d)
        if x < 0.5:
            return self.case(ctx, 'int', d)
        if x < 0.58:
            return self.E('coalesce({0}, {1})', ['int', 'int'], 'int', ctx, d)
        if x < 0.62:
            return self.E('nullif({0}, {1})', ['int', 'int'], 'int', ctx, d)
        if x < 0.67:
            return self.E('%s({0}, {1})' % r.choice(['greatest', 'least']), ['int', 'int'], 'int', ctx, d)
        if x < 0.73:
            return self.E('%s({0})' % r.choice(['length', 'char_length']), ['text'], 'int', ctx, d)
        if x < 0.78:
            return self.E('cast({0} as int)', ['num'], 'int', ctx, d)
        if x < 0.82:
            return self.E('({0} - {1})', ['date', 'date'], 'int', ctx, d)
        if x < 0.85:
            return self.E('cast(extract(%s from {0}) as int)' % r.choice(['day', 'month', 'year', 'dow']),
                          ['date'], 'int', ctx, d)
        if x < 0.88:
            return self.E('case when {0} then 1 else 0 end', ['bool'], 'int', ctx, d)
        if x < 0.91:
            return self.E('mod({0}, %d)' % r.choice([2, 3, 5]), ['int'], 'int', ctx, d)
        return self.leaf(ctx, 'int')

    def e_num(self, ctx, d):
        r = self.r
        x = r.random()
        other = r.choice(['num', 'int'])
        if x < 0.3:
            return self.E('({0} %s {1})' % r.choice(['+', '-', '*']), ['num', other], 'num', ctx, d)
        if x < 0.36:
            return self.E('({0} / nullif({1}, 0))', ['num', other], 'num', ctx, d)
        if x < 0.45:
            return self.E('%s({0})' % r.choice(['abs', 'round', 'floor', 'ceil', 'trunc']), ['num'], 'num', ctx, d)
        if x < 0.5:
            return self.E('round({0}, %d)' % r.choice([0, 1, 2]), ['num'], 'num', ctx, d)
        if x < 0.6:
            return self.case(ctx, 'num', d)
        if x < 0.68:
            return self.E('coalesce({0}, {1})', ['num', other], 'num', ctx, d)
        if x < 0.75:
            return self.E('cast({0} as numeric)', ['int'], 'num', ctx, d)
        if x < 0.8:
            return self.E('cast({0} as numeric(8,1))', ['num'], 'num', ctx, d)
        if x < 0.85:
            return self.E('(- {0})', ['num'], 'num', ctx, d)
        return self.leaf(ctx, 'num')

    def e_float(self, ctx, d):
        r = self.r
        x = r.random()
        if x < 0.3:
            return self.E('({0} %s {1})' % r.choice(['+', '-', '*']), ['float', 'float'], 'float', ctx, d)
        if x < 0.5:
            return self.E('cast({0} as float8)', [r.choice(['int', 'num'])], 'float', ctx, d)
        if x < 0.6:
            return self.case(ctx, 'float', d)
        if x < 0.7:
            return self.E('abs({0})', ['float'], 'float', ctx, d)
        return self.leaf(ctx, 'float')

    def e_text(self, ctx, d):
        r = self.r
        x = r.random()
        if x < 0.2:
            return self.E('({0} || {1})', ['text', 'text'], 'text', ctx, d)
        if x < 0.3:
            return self.E('%s({0})' % r.choice(['upper', 'lower', 'trim', 'ltrim', 'rtrim', 'reverse']), ['text'],
                          'text', ctx, d)
        if x < 0.36:
            return self.E('substr({0}, %d, %d)' % (r.choice([1, 1, 2, 0]), r.choice([1, 2, 3])), ['text'], 'text',
                          ctx, d)
        if x < 0.4:
            return self.E("replace({0}, 'a', 'x')", ['text'], 'text', ctx, d)
        if x < 0.44:
            return self.E('%s({0}, %d)' % (r.choice(['left', 'right']), r.choice([1, 2])), ['text'], 'text', ctx, d)
        if x < 0.55:
            return self.case(ctx, 'text', d)
        if x < 0.63:
            return self.E('coalesce({0}, {1})', ['text', 'text'], 'text', ctx, d)
        if x < 0.68:
            return self.E('cast({0} as text)', [r.choice(['int', 'date', 'bool'])], 'text', ctx, d)
        if x < 0.72:
            return self.E('nullif({0}, {1})', ['text', 'text'], 'text', ctx, d)
        if x < 0.75:
            return self.E('%s({0}, {1})' % r.choice(['greatest', 'least']), ['text', 'text'], 'text', ctx, d)
        return self.leaf(ctx, 'text')

    def e_date(self, ctx, d):
        r = self.r
        x = r.random()
        if x < 0.3:
            return E('({0} %s %d)' % (r.choice(['+', '-']), r.choice([1, 2, 7, 30])),
                     [self.expr(ctx, 'date', d - 1)], 'date')
        if x < 0.45:
            return self.case(ctx, 'date', d)
        if x < 0.6:
            return self.E('coalesce({0}, {1})', ['date', 'date'], 'date', ctx, d)
        if x < 0.68:
            return self.E('%s({0}, {1})' % r.choice(['greatest', 'least']), ['date', 'date'], 'date', ctx, d)
        return self.leaf(ctx, 'date')

    def case(self, ctx, cat, d):
        r = self.r
        if r.random() < 0.25:
            k = self.pick_cat(ctx, ['int', 'text', 'date'])
            return self.E('case {0} when {1} then {2} else {3} end', [k, k, cat, cat], cat, ctx, d)
        if r.random() < 0.2:
            return self.E('case when {0} then {1} end', ['bool', cat], cat, ctx, d)
        if r.random() < 0.2:
            return self.E('case when {0} then {1} when {2} then {3} else {4} end', ['bool', cat, 'bool', cat, cat],
                          cat, ctx, d)
        return self.E('case when {0} then {1} else {2} end', ['bool', cat, cat], cat, ctx, d)

    def e_bool(self, ctx, d):
        r = self.r
        x = r.random()
        if x < 0.28:
            k = self.pick_cat(ctx)
            if k == 'bool' and r.random() < 0.5:
                k = 'int'
            other = k
            if k in NUMERIC_CATS:
                other = r.choice([k, k, 'int', 'num'])
            op = r.choice(['=', '<>', '<', '<=', '>', '>=', '='])
            return self.E('({0} %s {1})' % op, [k, other], 'bool', ctx, d)
        if x < 0.36:
            return self.E('({0} is %s)' % r.choice(['null', 'not null']), [self.pick_cat(ctx)], 'bool', ctx, d)
        if x < 0.41:
            k = self.pick_cat(ctx, ['int', 'num', 'text', 'date'])
            return self.E('({0} %sbetween {1} and {2})' % r.choice(['', 'not ']), [k, k, k], 'bool', ctx, d)
        if x < 0.47:
            k = self.pick_cat(ctx, ['int', 'num', 'text', 'date'])
            n = r.randint(1, 4)
            kids = [self.expr(ctx, k, d - 1)] + [self.lit(k, 0.15) for _ in range(n)]
            fmt = '({0} %sin (%s))' % (r.choice(['', 'not ']), ', '.join('{%d}' % (i + 1) for i in range(n)))
            return E(fmt, kids, 'bool')
        if x < 0.52:
            return E('({0} %s %s)' % (r.choice(['like', 'not like', 'like', 'ilike']), r.choice(LIKE_PATS)),
                     [self.expr(ctx, 'text', d - 1)], 'bool')
        if x < 0.58:
            return self.E('(not {0})', ['bool'], 'bool', ctx, d)
        if x < 0.68:
            return self.E('({0} and {1})', ['bool', 'bool'], 'bool', ctx, d)
        if x < 0.76:
            return self.E('({0} or {1})', ['bool', 'bool'], 'bool', ctx, d)
        if x < 0.79:
            k = self.pick_cat(ctx)
            return self.E('({0} is %sdistinct from {1})' % r.choice(['', 'not ']), [k, k], 'bool', ctx, d)
        if x < 0.81:
            return self.E('({0} is %s)' % r.choice(['true', 'not true', 'false', 'not false', 'unknown']), ['bool'],
                          'bool', ctx, d)
        if not ctx.nosub and ctx.depth < 2 and x < 0.95:
            return self.pred_sub(ctx, d)
        return self.leaf(ctx, 'bool')

    # -- aggregates and windows
    def aggregate(self, ctx, cat, d):
        r = self.r
        a = ctx.agg
        dd = max(0, d - 1)
        filt = ''
        fkids = []
        if r.random() < 0.08:
            filt = ' filter (where {%d})'
            fkids = [self.expr(a, 'bool', 1)]
        if cat == 'int':
            x = r.random()
            if x < 0.35:
                return E('count(*)' + (filt % 0 if filt else ''), fkids, 'int', agg='count')
            if x < 0.6:
                k = self.pick_cat(a)
                dist = r.random() < 0.25
                e = self.expr(a, k, dd)
                return E('count(%s{0})' % ('distinct ' if dist else '') + (filt % 1 if filt else ''), [e] + fkids,
                         'int', agg='countd' if dist else 'count')
            fn = r.choice(['sum', 'min', 'max'])
            dist = fn == 'sum' and r.random() < 0.15
            return E('%s(%s{0})' % (fn, 'distinct ' if dist else '') + (filt % 1 if filt else ''),
                     [self.expr(a, 'int', dd)] + fkids, 'int', agg=fn + ('d' if dist else ''))
        if cat in ('num', 'float'):
            fn = r.choice(['sum', 'avg', 'min', 'max'])
            src = cat if fn != 'avg' or cat == 'float' else r.choice(['int', 'num'])
            return E('%s({0})' % fn + (filt % 1 if filt else ''), [self.expr(a, src, dd)] + fkids, cat, agg=fn)
        if cat == 'text':
            if r.random() < 0.3:
                return E("string_agg({0}, ',' order by {0})", [self.expr(a, 'text', dd)], 'text', agg='string_agg')
            fn = r.choice(['min', 'max'])
            return E('%s({0})' % fn + (filt % 1 if filt else ''), [self.expr(a, 'text', dd)] + fkids, 'text', agg=fn)
        if cat == 'date':
            fn = r.choice(['min', 'max'])
            return E('%s({0})' % fn, [self.expr(a, 'date', dd)], 'date', agg=fn)
        if cat == 'bool':
            fn = r.choice(['bool_and', 'bool_or'])
            return E('%s({0})' % fn, [self.expr(a, 'bool', dd)], 'bool', agg=fn)
        return None

    def window(self, ctx, cat):
        r = self.r
        cols = [c for c in ctx.cols if c[1] != 'float']
        if not cols:
            return None
        part = r.sample(cols, min(len(cols), r.choice([0, 0, 1, 1, 2])))
        ps = ('partition by ' + ', '.join(c[0] for c in part) + ' ') if part else ''
        allord = 'order by ' + ', '.join(c[0] for c in cols)
        o = r.sample(cols, min(len(cols), r.choice([1, 1, 2])))
        os_ = 'order by ' + ', '.join('%s%s' % (c[0], r.choice(['', ' desc', ' nulls first'])) for c in o)
        wctx = Ctx(ctx.cols, nosub=True)
        self_expr = self.expr

        def arg(c):
            e = self_expr(wctx, c, 1)
            if e.lit and c == 'text':
                e = E('cast({0} as text)', [e], 'text')
            return e
        if cat == 'int':
            x = r.random()
            if x < 0.3:
                return E('%s() over (%s%s)' % (r.choice(['rank', 'dense_rank']), ps, os_), [], 'int', win=True)
            if x < 0.45:
                return E('count(*) over (%s)' % ps.strip(), [], 'int', win=True)
            if x < 0.6:
                return E('row_number() over (%s%s)' % (ps, allord), [], 'int', win=True)
            if x < 0.7:
                return E('ntile(%d) over (%s%s)' % (r.choice([2, 3]), ps, allord), [], 'int', win=True)
            fn = r.choice(['lag', 'lead'])
            return E('%s({0}) over (%s%s)' % (fn, ps, allord), [arg('int')], 'int', win=True)
        if cat in ('num', 'int'):
            pass
        if cat == 'num':
            x = r.random()
            if x < 0.4:
                return E('sum({0}) over (%s%s)' % (ps, os_), [arg('num')], 'num', win=True)
            if x < 0.6:
                return E('avg({0}) over (%s)' % ps.strip(), [self.expr(wctx, r.choice(['int', 'num']), 1)], 'num',
                         win=True)
            return E('sum({0}) over (%s%s rows between 1 preceding and current row)' % (ps, allord),
                     [arg('num')], 'num', win=True)
        if cat in ('text', 'date'):
            x = r.random()
            if x < 0.5:
                return E('%s({0}) over (%s%s)' % (r.choice(['min', 'max']), ps, os_), [arg(cat)], cat,
                         win=True)
            return E('first_value({0}) over (%s%s)' % (ps, allord), [arg(cat)], cat, win=True)
        return None

    # -- subqueries
    def sub_ctx_outer(self, ctx):
        return ctx.all_cols()

    def scalar_sub(self, ctx, cat):
        q = self.select(outer=self.sub_ctx_outer(ctx), depth=ctx.depth + 1, cats=[cat], mode='scalar')
        return E('({0})', [q], cat)

    def pred_sub(self, ctx, d):
        r = self.r
        x = r.random()
        outer = self.sub_ctx_outer(ctx)
        if x < 0.4:
            q = self.select(outer=outer, depth=ctx.depth + 1, cats=None, mode='exists')
            return E('(%sexists ({0}))' % r.choice(['', 'not ']), [q], 'bool')
        k = self.pick_cat(ctx, ['int', 'int', 'text', 'num', 'date'])
        q = self.select(outer=outer, depth=ctx.depth + 1, cats=[k], mode='in')
        lhs = self.expr(Ctx(ctx.cols, nosub=True, outer=ctx.outer), k, 1)
        if x < 0.75:
            return E('({1} %sin ({0}))' % r.choice(['', 'not ', '']), [q, lhs], 'bool')
        op = r.choice(['=', '<>', '<', '>=', '<='])
        return E('({1} %s %s ({0}))' % (op, r.choice(['any', 'all', 'some'])), [q, lhs], 'bool')

    # -- FROM
    def base_rel(self, depth, outer, allow_derived=True):
        r = self.r
        names = list(self.rel) + list(self.ctes)
        if allow_derived and depth < 2 and r.random() < 0.12:
            a = self.alias('d')
            q = self.select(outer=[], depth=depth + 1, mode='derived')
            return FD(q, a, False), [('%s.%s' % (a, al), e.cat) for e, al in q.items]
        name = r.choice(names)
        a = self.alias('q')
        cols = self.rel.get(name) or self.ctes[name]
        return FT(name, a), [('%s.%s' % (a, c), cat) for c, cat in cols]

    def join_cond(self, lcols, rcols, equi_only=False):
        r = self.r
        pairs = [(a, b) for a in lcols for b in rcols
                 if a[1] == b[1] or (a[1] in ('int', 'num') and b[1] in ('int', 'num'))]
        if not pairs:
            return None
        n = 1 if r.random() < 0.8 else 2
        conds = []
        for a, b in r.sample(pairs, min(n, len(pairs))):
            conds.append(E('(%s = %s)' % (a[0], b[0]), [], 'bool', fixed=True))
        e = conds[0]
        for c in conds[1:]:
            e = E('({0} and {1})', [e, c], 'bool')
        if not equi_only and r.random() < 0.3:
            extra = self.expr(Ctx(lcols + rcols, depth=2), 'bool', 1)
            e = E('({0} and {1})', [e, extra], 'bool')
        return e

    def from_clause(self, depth, outer, small=False):
        r = self.r
        n = r.choice([1, 1, 1, 2]) if small else r.choice([1, 1, 2, 2, 2, 3, 3])
        item, scope = self.base_rel(depth, outer)
        items = [item]
        last = scope             # the columns of items[-1]: what a JOIN's ON and a LATERAL may name
        for _ in range(n - 1):
            x = r.random()
            if x < 0.12 and depth < 2:
                # LATERAL: correlated to what came before
                a = self.alias('l')
                q = self.select(outer=last + outer, depth=depth + 1, mode='lateral')
                rcols = [('%s.%s' % (a, al), e.cat) for e, al in q.items]
                kind = r.choice(['cross join', 'left join', 'join'])
                on = None if kind == 'cross join' else E('true', [], 'bool', fixed=True)
                items[-1] = FJ(kind, items[-1], FD(q, a, True), on)
                scope = scope + rcols
                last = last + rcols
                continue
            right, rcols = self.base_rel(depth, outer)
            if x < 0.25:
                items.append(right)      # a comma: the condition goes to WHERE
                scope = scope + rcols
                last = rcols
                continue
            kind = r.choice(['join', 'join', 'left join', 'left join', 'right join', 'full join', 'cross join'])
            on = None
            if kind != 'cross join':
                on = self.join_cond(last, rcols, equi_only=(kind == 'full join'))
                if on is None:
                    if kind == 'full join':
                        kind = 'cross join'
                    else:
                        on = self.expr(Ctx(last + rcols, depth=2), 'bool', 1)
            items[-1] = FJ(kind, items[-1], right, on)
            scope = scope + rcols
            last = last + rcols
        return items, scope

    # -- SELECT
    def select(self, outer=None, depth=0, cats=None, mode='top'):
        """mode: top, derived, lateral, scalar (one aggregate or limit 1), exists, in, cte, setrhs."""
        r = self.r
        outer = outer or []
        q = Q()
        if mode == 'top' and r.random() < 0.15 and self.rel:
            name = 'cte%d' % len(self.ctes)
            cq = self.select(depth=1, mode='cte')
            q.ctes.append([name, cq])
            self.ctes[name] = [(al, e.cat) for e, al in cq.items]
        if mode == 'scalar' and r.random() < 0.15:
            frm, scope = [], []
        else:
            frm, scope = self.from_clause(depth, outer, small=mode in ('scalar', 'exists', 'in'))
        q.frm = frm
        rowctx = Ctx(scope, depth=depth, outer=outer)
        q.rowctx = rowctx
        # WHERE, with a correlation for subqueries
        conds = []
        if outer and scope and mode in ('scalar', 'exists', 'in', 'lateral') and r.random() < 0.7:
            c = self.join_cond(scope, outer, equi_only=True)
            if c is not None:
                conds.append(c)
        if r.random() < (0.7 if mode == 'top' else 0.45):
            conds.append(self.expr(rowctx, 'bool', r.choice([1, 2, 2, 3])))
        if conds:
            w = conds[0]
            for c in conds[1:]:
                w = E('({0} and {1})', [w, c], 'bool')
            q.where = w
        want_agg = (mode == 'scalar' and (not frm or r.random() < 0.75))
        grouped = False
        if not want_agg and scope and mode not in ('exists',) and r.random() < 0.22:
            grouped = True
        ncols = len(cats) if cats else r.choice([1, 1, 2, 2, 3, 4])
        if mode == 'exists':
            ncols = 1
        outcats = cats or [self.pick_cat(rowctx) if scope else r.choice(['int', 'text', 'bool']) for _ in range(ncols)]
        if grouped:
            gcols = [c for c in scope if c[1] != 'float']
            keys = r.sample(gcols, min(len(gcols), r.choice([1, 1, 2]))) if gcols else []
            q.group = [E(k[0], [], k[1]) for k in keys]
            gctx = Ctx(keys, agg=Ctx(scope, depth=depth, nosub=True), depth=depth, outer=outer)
            q.grpctx = gctx
            items = []
            for i, cat in enumerate(outcats):
                kk = [k for k in keys if k[1] == cat]
                if kk and r.random() < 0.5:
                    items.append(E(r.choice(kk)[0], [], cat))
                else:
                    e = self.aggregate(gctx, cat, 2) if r.random() < 0.6 else self.expr(gctx, cat, 2)
                    items.append(e or self.lit(cat))
            if r.random() < 0.35:
                q.having = self.expr(gctx, 'bool', 2)
        elif want_agg or (scope and mode in ('top', 'derived', 'cte') and r.random() < 0.08):
            gctx = Ctx([], agg=Ctx(scope, depth=depth, nosub=True), depth=depth, outer=outer)
            q.grpctx = gctx
            items = [self.aggregate(gctx, cat, 2) or self.lit(cat) for cat in outcats]
            if mode != 'scalar' and r.random() < 0.15:
                q.having = self.expr(gctx, 'bool', 1)
        else:
            ictx = Ctx(scope, depth=depth, outer=outer)
            items = []
            for cat in outcats:
                e = None
                if mode in ('top', 'derived', 'cte') and r.random() < 0.08:
                    e = self.window(ictx, cat)
                items.append(e or self.expr(ictx, cat, r.choice([0, 1, 1, 2])))
        q.items = [[e, self.alias('x')] for e in items]
        if mode not in ('scalar', 'exists') and not grouped and r.random() < 0.12:
            q.distinct = True
        # set operations
        if mode in ('top', 'derived', 'in') and depth < 2 and r.random() < 0.1:
            rhs = self.select(outer=outer, depth=depth + 1, cats=[e.cat for e, a in q.items], mode='setrhs')
            q.setop = [r.choice(['union', 'union all', 'intersect', 'intersect all', 'except', 'except all']), rhs]
        # ORDER BY every column; LIMIT, OFFSET
        if mode == 'scalar' and not want_agg:
            q.order = [[i + 1, r.choice(['', ' desc', ' nulls first', ' desc nulls last'])] for i in range(len(q.items))]
            q.limit = 1
        elif mode in ('top', 'derived', 'in', 'lateral') and r.random() < (0.35 if mode == 'top' else 0.12):
            pos = list(range(1, len(q.items) + 1))
            r.shuffle(pos)
            q.order = [[p, r.choice(['', '', ' desc', ' nulls first', ' desc nulls last', ' asc nulls first'])]
                       for p in pos]
            if r.random() < 0.5:
                q.limit = r.choice([0, 1, 2, 3, 5, 10])
                if r.random() < 0.3:
                    q.offset = r.choice([0, 1, 2, 4])
        if mode == 'top':
            self.ctes = {}
        return q


# ---------------------------------------------------------------- checks

INT_OIDS = {20, 21, 23}
NUM_OIDS = {1700}
FLOAT_OIDS = {700, 701}


def col_kinds(a, b):
    n = max(len(a.oids), len(b.oids))
    out = []
    for i in range(n):
        s = set()
        for x in (a, b):
            if i < len(x.oids):
                s.add(x.oids[i])
        if s & FLOAT_OIDS:
            out.append('f')
        elif s & NUM_OIDS:
            out.append('n')
        else:
            out.append(None)
    return out


def norm_val(v, kind, pg):
    if v is None or kind is None:
        return v
    try:
        d = Decimal(v)
    except InvalidOperation:
        return v
    if not d.is_finite():
        return v
    if d == 0:
        return '0'
    if kind == 'f' or pg:
        return '%.12g' % float(d)
    return format(d.normalize(), 'f')


def norm_rows(res, kinds, pg, ordered):
    rows = [tuple(norm_val(v, kinds[i] if i < len(kinds) else None, pg) for i, v in enumerate(row))
            for row in res.rows]
    if not ordered:
        rows.sort(key=lambda row: tuple((0, '') if v is None else (1, v) for v in row))
    return rows


def compare(a, b, ordered, pg=False):
    """None when a and b agree, else a class: wrong, errcode, a-error, b-error,
    crash, hang (a crash or hang of b; the caller checks a's)."""
    if b.kind in ('crash', 'hang'):
        return b.kind
    if a.kind in ('crash', 'hang'):
        return None
    if a.kind == 'rows' and b.kind == 'rows':
        if len(a.oids) != len(b.oids):
            return 'wrong'
        kinds = col_kinds(a, b)
        if norm_rows(a, kinds, pg, ordered) != norm_rows(b, kinds, pg, ordered):
            return 'wrong'
        return None
    if a.kind == 'error' and b.kind == 'error':
        return None if a.code == b.code else 'errcode'
    return 'a-error' if a.kind == 'error' else 'b-error'


def norm_msg(m):
    m = re.sub(r'"[^"]*"', '"_"', m or '')
    m = re.sub(r"'[^']*'", "'_'", m)
    m = re.sub(r'\b\d+\b', 'N', m)
    return m[:120]


# Each check: the configurations it compares (server, connection), and the
# severity order of the report.
LEXDB_CFGS = {
    'on': ('s0', 'on'),
    'off': ('s0', 'off'),
    'rules': ('s0', 'rules'),
    'alt': ('alt', 'on'),
    'force': ('force', 'on'),
    'noidx': ('noidx', 'on'),
}
CHECKS_ALL = ['batch', 'rules', 'alt', 'force', 'noidx', 'tlp', 'norec', 'pg']
CHECK_CFG = {'batch': 'off', 'rules': 'rules', 'alt': 'alt', 'force': 'force', 'noidx': 'noidx'}


def tlp_variants(q, r, setup):
    """[(kind, q_whole, q_parts)] equal multisets (or values) when lexdb is right."""
    if q.setop or q.order or q.limit is not None or q.has_window() or q.rowctx is None or not q.frm:
        return []
    g = Gen(r, setup)
    g.n = 5000
    g.ctes = {n: [(al, e.cat) for e, al in cq.items] for n, cq in q.ctes}
    out = []
    agg = q.is_agg()
    if not agg:
        p = g.expr(q.rowctx, 'bool', r.choice([1, 2, 2, 3]))
        parts = []
        for f in ('({0})', '(not ({0}))', '(({0}) is null)'):
            pq = copy.copy(q)
            pe = E(f, [p], 'bool')
            pq.where = pe if q.where is None else E('({0} and {1})', [q.where, pe], 'bool')
            pq.ctes = []
            parts.append(pq)
        op = ' union ' if q.distinct else ' union all '
        text = op.join('(%s)' % x.sql() for x in parts)
        if q.ctes:
            text = 'with ' + ', '.join('%s as (%s)' % (n, cq.sql()) for n, cq in q.ctes) + ' ' + text
        out.append(('tlp-where', q.sql(), text))
    elif q.group and q.having is None:
        # the group keys alone: union of the partitions' groups
        base = copy.copy(q)
        base.items = [[gk, 'k%d' % i] for i, gk in enumerate(q.group)]
        base.distinct = False
        p = g.expr(q.rowctx, 'bool', r.choice([1, 2]))
        parts = []
        for f in ('({0})', '(not ({0}))', '(({0}) is null)'):
            pq = copy.copy(base)
            pe = E(f, [p], 'bool')
            pq.where = pe if q.where is None else E('({0} and {1})', [q.where, pe], 'bool')
            pq.ctes = []
            parts.append(pq)
        text = ' union '.join('(%s)' % x.sql() for x in parts)
        wq = base.sql()
        if q.ctes:
            pre = 'with ' + ', '.join('%s as (%s)' % (n, cq.sql()) for n, cq in q.ctes) + ' '
            text = pre + text
        out.append(('tlp-group', wq, text))
    if agg and q.group and q.grpctx is not None:
        # HAVING partitioned
        p = g.expr(q.grpctx, 'bool', r.choice([1, 2]))
        parts = []
        for f in ('({0})', '(not ({0}))', '(({0}) is null)'):
            pq = copy.copy(q)
            pe = E(f, [p], 'bool')
            pq.having = pe if q.having is None else E('({0} and {1})', [q.having, pe], 'bool')
            pq.ctes = []
            pq.distinct = False
            parts.append(pq)
        base = copy.copy(q)
        base.distinct = False
        text = ' union all '.join('(%s)' % x.sql() for x in parts)
        if q.ctes:
            text = 'with ' + ', '.join('%s as (%s)' % (n, cq.sql()) for n, cq in q.ctes) + ' ' + text
        out.append(('tlp-having', base.sql(), text))
    if agg and not q.group and q.having is None and not q.distinct:
        # aggregates decomposed over the partitions
        outer = []
        ok = True
        for e, a in q.items:
            if e.agg in ('count',):
                outer.append('sum(%s)' % a)
            elif e.agg in ('sum', 'min', 'max', 'bool_and', 'bool_or'):
                fn = {'bool_and': 'bool_and', 'bool_or': 'bool_or'}.get(e.agg, e.agg)
                outer.append('%s(%s)' % (fn, a))
            else:
                ok = False
        if ok and outer:
            p = g.expr(q.rowctx, 'bool', r.choice([1, 2]))
            parts = []
            for f in ('({0})', '(not ({0}))', '(({0}) is null)'):
                pq = copy.copy(q)
                pe = E(f, [p], 'bool')
                pq.where = pe if q.where is None else E('({0} and {1})', [q.where, pe], 'bool')
                pq.ctes = []
                parts.append(pq)
            text = 'select %s from (%s) as tlp' % (', '.join(outer), ' union all '.join('(%s)' % x.sql() for x in parts))
            if q.ctes:
                text = 'with ' + ', '.join('%s as (%s)' % (n, cq.sql()) for n, cq in q.ctes) + ' ' + text
            # count's sum over no partitions is NULL only when all are empty: the original gives 0
            whole = q.sql()
            out.append(('tlp-agg', whole, text))
    return out


def norec_variant(q, r, setup):
    if q.setop or q.is_agg() or q.rowctx is None or not q.frm:
        return None
    p = q.where
    if p is None:
        g = Gen(r, setup)
        g.n = 6000
        g.ctes = {n: [(al, e.cat) for e, al in cq.items] for n, cq in q.ctes}
        p = g.expr(q.rowctx, 'bool', r.choice([1, 2, 3]))
    pre = ''
    if q.ctes:
        pre = 'with ' + ', '.join('%s as (%s)' % (n, cq.sql()) for n, cq in q.ctes) + ' '
    frm = ', '.join(f.sql() for f in q.frm)
    a = pre + 'select count(*) from %s where %s' % (frm, p.sql())
    b = pre + 'select coalesce(sum(case when %s then 1 else 0 end), 0) from %s' % (p.sql(), frm)
    return a, b


# ---------------------------------------------------------------- the worker

class Worker:
    def __init__(self, wid, args, root):
        self.wid, self.args, self.root = wid, args, root
        os.makedirs(root, exist_ok=True)
        base = args.port + 10 * wid
        b = args.bin
        cfgs = {'on': [], 'off': ['set lexdb_batch = off'], 'rules': ['set lexdb_planner = rules']}
        self.checks = set(args.checks)
        self.servers = {'s0': Lexdb('s0', b, root, base, args.cpus, {}, cfgs)}
        if args.variants:
            if 'alt' in self.checks:
                self.servers['alt'] = Lexdb('alt', b, root, base + 1, args.cpus,
                                            {'LEXDB_FUZZ_UNNEST': '0', 'LEXDB_FUZZ_REWRITES': '0',
                                             'LEXDB_FUZZ_BUSHY': '0', 'LEXDB_FUZZ_KEYORDER': '1'}, {'on': []})
            if 'force' in self.checks:
                self.servers['force'] = Lexdb('force', b, root, base + 2, args.cpus,
                                              {'LEXDB_FUZZ_BUSHY': '2', 'LEXDB_FUZZ_KEYORDER': str(2 + wid % 2)},
                                              {'on': []})
        else:
            self.checks -= {'alt', 'force'}
        if 'noidx' in self.checks:
            self.servers['noidx'] = Lexdb('noidx', b, root, base + 3, args.cpus, {}, {'on': []})
        self.pg = PgClient(args.pg_port, 'fz%d' % wid) if 'pg' in self.checks else None
        for s in self.servers.values():
            s.start()
        self.stats = {'queries': 0, 'stmts': 0, 'seeds': 0, 'fails': {}, 'reduced': 0, 'skipped': 0,
                      'tlp': 0, 'norec': 0, 'lexdb_errors': 0, 'pg_errors': 0, 'start': time.time()}
        self.presig = {}
        self.ncase = 0
        self.cur = None
        self.bad_setup = set()

    # -- loading
    def load(self, sname, setup):
        noidx = sname == 'noidx'
        key = setup.key(noidx)
        if sname == 'pg':
            if self.pg.loaded == key:
                return
            for s in DROPS:
                self.pg.run(s)
            for s in setup.stmts(noidx):
                rr = self.pg.run(s)
                if rr.kind != 'rows':
                    raise SetupError('postgres: %s: %s' % (s, rr.brief()))
            self.pg.loaded = key
            return
        srv = self.servers[sname]
        if srv.loaded == key:
            return
        for attempt in range(3):
            ok = True
            for s in DROPS:
                rr = srv.run('on', s)
                if rr.kind in ('crash', 'hang'):
                    ok = False
                    break
            if ok:
                for s in setup.stmts(noidx):
                    rr = srv.run('on', s)
                    if rr.kind in ('crash', 'hang'):
                        ok = False
                        self.note_setup_crash(sname, s, rr)
                        break
                    if rr.kind == 'error':
                        raise SetupError('lexdb %s: %s: %s' % (sname, s, rr.brief()))
            if ok:
                srv.loaded = key
                return
        raise SetupError('lexdb %s: the setup keeps failing' % sname)

    def note_setup_crash(self, sname, stmt, rr):
        self.save_case({'check': 'setup', 'cls': rr.kind, 'server': sname, 'sql': stmt, 'detail': rr.brief(),
                        'setup': self.cur.js() if self.cur else None})

    def run_cfg(self, cfg, sql, setup):
        sname, conn = LEXDB_CFGS[cfg]
        self.load(sname, setup)
        self.stats['stmts'] += 1
        return self.servers[sname].run(conn, sql)

    def run_pg(self, sql, setup):
        self.load('pg', setup)
        self.stats['stmts'] += 1
        r = self.pg.run(sql)
        if r.kind == 'hang':
            return Res('error', code='57014', msg=r.msg)
        if r.kind == 'error' and r.code == '57014':
            return None
        return r

    # -- one query, every check
    def check_query(self, q, setup, r):
        sql = q.sql()
        ordered = q.ordered()
        res = {'on': self.run_cfg('on', sql, setup)}
        fails = []
        if res['on'].kind in ('crash', 'hang'):
            fails.append(('on', res['on'].kind, sql, None, res))
            return fails
        if res['on'].kind == 'error':
            self.stats['lexdb_errors'] += 1
        for chk, cfg in CHECK_CFG.items():
            if chk not in self.checks or LEXDB_CFGS[cfg][0] not in self.servers:
                continue
            res[cfg] = self.run_cfg(cfg, sql, setup)
            c = compare(res['on'], res[cfg], ordered)
            if c:
                fails.append((chk, c, sql, None, {'on': res['on'], cfg: res[cfg]}))
        if self.pg is not None:
            pr = self.run_pg(sql, setup)
            if pr is not None:
                if pr.kind == 'error':
                    self.stats['pg_errors'] += 1
                c = compare(res['on'], pr, ordered, pg=True)
                if c and c != 'crash':
                    fails.append(('pg', c, sql, None, {'on': res['on'], 'pg': pr}))
        if 'tlp' in self.checks:
            for kind, whole, parts in tlp_variants(q, r, setup):
                self.stats['tlp'] += 1
                a = self.run_cfg('on', whole, setup)
                b = self.run_cfg('on', parts, setup)
                if b.kind in ('crash', 'hang'):
                    fails.append((kind, b.kind, parts, None, {'whole': a, 'parts': b}))
                elif a.kind == 'rows' and b.kind == 'rows' and compare(a, b, False):
                    fails.append((kind, 'wrong', whole, parts, {'whole': a, 'parts': b}))
        if 'norec' in self.checks:
            nv = norec_variant(q, r, setup)
            if nv:
                self.stats['norec'] += 1
                a = self.run_cfg('on', nv[0], setup)
                b = self.run_cfg('on', nv[1], setup)
                for x, s in ((a, nv[0]), (b, nv[1])):
                    if x.kind in ('crash', 'hang'):
                        fails.append(('norec', x.kind, s, None, {'opt': a, 'unopt': b}))
                        break
                else:
                    if a.kind == 'rows' and b.kind == 'rows' and compare(a, b, False):
                        fails.append(('norec', 'wrong', nv[0], nv[1], {'opt': a, 'unopt': b}))
        return fails

    # -- the predicate for reduction: does (check, cls) still fail?
    def still_fails(self, case, setup, sql, sql2):
        chk, cls = case['check'], case['cls']
        try:
            if chk == 'setup':
                return False
            if chk == 'on':
                x = self.run_cfg('on', sql, setup)
                return x.kind == cls
            if chk in CHECK_CFG:
                a = self.run_cfg('on', sql, setup)
                if a.kind in ('crash', 'hang'):
                    return False
                b = self.run_cfg(CHECK_CFG[chk], sql, setup)
                c = compare(a, b, case['ordered'])
                return c == cls and self.same_codes(case, a, b)
            if chk == 'pg':
                a = self.run_cfg('on', sql, setup)
                if a.kind in ('crash', 'hang'):
                    return False
                b = self.run_pg(sql, setup)
                if b is None:
                    return False
                return compare(a, b, case['ordered'], pg=True) == cls and self.same_codes(case, a, b)
            if chk.startswith('tlp') or chk == 'norec':
                if cls in ('crash', 'hang'):
                    return self.run_cfg('on', sql, setup).kind == cls
                a = self.run_cfg('on', sql, setup)
                b = self.run_cfg('on', sql2, setup)
                return a.kind == 'rows' and b.kind == 'rows' and compare(a, b, False) == 'wrong'
        except SetupError:
            return False
        return False

    @staticmethod
    def same_codes(case, a, b):
        if case['cls'] in ('wrong', 'crash', 'hang'):
            return True
        return [a.code, b.code] == case['codes']

    # -- recording
    def save_case(self, case):
        self.ncase += 1
        d = os.path.join(self.root, 'cases')
        os.makedirs(d, exist_ok=True)
        case['id'] = 'w%d-%04d' % (self.wid, self.ncase)
        with open(os.path.join(d, case['id'] + '.json'), 'w') as f:
            json.dump(case, f, indent=1, default=lambda o: o.js())
        return case['id']

    def record(self, fail, q, setup, seed, qi, deadline):
        chk, cls, sql, sql2, res = fail
        self.stats['fails'][chk + ':' + cls] = self.stats['fails'].get(chk + ':' + cls, 0) + 1
        vals = list(res.values())
        codes = [x.code for x in vals]
        case = {'check': chk, 'cls': cls, 'seed': seed, 'qi': qi, 'sql': sql, 'sql2': sql2,
                'ordered': q.ordered() if sql == q.sql() else False, 'codes': codes,
                'results': {k: v.js() for k, v in res.items()}, 'setup': setup.js()}
        # a pre-signature bounds the reductions of one kind of failure
        if cls in ('wrong', 'crash', 'hang'):
            pre = (chk, cls)
            limit = self.args.reduce_wrong
        else:
            pre = (chk, cls, tuple(norm_msg(x.msg) if x.kind == 'error' else 'rows' for x in vals))
            limit = self.args.reduce_err
        n = self.presig.get(pre, 0)
        self.presig[pre] = n + 1
        if n < limit and time.time() < deadline:
            try:
                rq, rs, rsql, rsql2 = reduce_case(self, case, q, setup, sql, sql2, deadline)
                case['min_sql'] = rsql
                case['min_sql2'] = rsql2
                case['min_setup'] = rs.js()
                case['min_setup_sql'] = rs.stmts()
                case['min_results'] = self.rerun(case, rs, rsql, rsql2)
                self.stats['reduced'] += 1
            except SetupError as e:
                case['reduce_error'] = str(e)
        else:
            self.stats['skipped'] += 1
        case['signature'] = signature(case)
        self.save_case(case)

    def rerun(self, case, setup, sql, sql2):
        out = {}
        chk = case['check']
        cfgs = ['on']
        if chk in CHECK_CFG:
            cfgs.append(CHECK_CFG[chk])
        for cfg in cfgs:
            out[cfg] = self.run_cfg(cfg, sql, setup).js()
        if chk == 'pg':
            x = self.run_pg(sql, setup)
            out['pg'] = x.js() if x else None
        if sql2:
            out['second'] = self.run_cfg('on', sql2, setup).js()
        return out

    def write_stats(self):
        self.stats['elapsed'] = time.time() - self.stats['start']
        self.stats['restarts'] = {k: s.starts - 1 for k, s in self.servers.items()}
        with open(os.path.join(self.root, 'stats.json'), 'w') as f:
            json.dump(self.stats, f, indent=1)

    def stop(self):
        for s in self.servers.values():
            s.stop()


class SetupError(Exception):
    pass


# ---------------------------------------------------------------- reduction

def walk(node, setter, out):
    out.append((setter, node))
    if isinstance(node, E):
        for i, k in enumerate(node.kids):
            walk(k, (lambda n, i=i, p=node: p.kids.__setitem__(i, n)), out)
    elif isinstance(node, Q):
        for i, c in enumerate(node.ctes):
            walk(c[1], (lambda n, c=c: c.__setitem__(1, n)), out)
        for it in node.items:
            walk(it[0], (lambda n, it=it: it.__setitem__(0, n)), out)
        for i, f in enumerate(node.frm):
            walk(f, (lambda n, i=i, p=node: p.frm.__setitem__(i, n)), out)
        if node.where is not None:
            walk(node.where, (lambda n, p=node: setattr(p, 'where', n)), out)
        if node.having is not None:
            walk(node.having, (lambda n, p=node: setattr(p, 'having', n)), out)
        if node.setop:
            walk(node.setop[1], (lambda n, s=node.setop: s.__setitem__(1, n)), out)
    elif isinstance(node, FJ):
        walk(node.left, (lambda n, p=node: setattr(p, 'left', n)), out)
        walk(node.right, (lambda n, p=node: setattr(p, 'right', n)), out)
        if node.on is not None:
            walk(node.on, (lambda n, p=node: setattr(p, 'on', n)), out)
    elif isinstance(node, FD):
        walk(node.q, (lambda n, p=node: setattr(p, 'q', n)), out)


def drop_item(q, i):
    n = copy.copy(q)
    n.items = q.items[:i] + q.items[i + 1:]
    order = []
    for p, d in q.order:
        if p == i + 1:
            continue
        order.append([p - 1 if p > i + 1 else p, d])
    n.order = order
    if q.setop:
        n.setop = [q.setop[0], drop_item(q.setop[1], i)]
    return n


def variants(node):
    """Smaller replacements for node."""
    out = []
    if isinstance(node, E):
        if node.win:
            if not node.lit:
                out.append(E(SIMPLE_LIT[node.cat], [], node.cat, lit=True))
            return out
        for k in node.kids:
            if isinstance(k, E) and k.cat == node.cat and not node.fixed:
                out.append(k)
        if not node.lit:
            out.append(E(SIMPLE_LIT[node.cat], [], node.cat, lit=True))
            if node.cat == 'bool':
                out.append(E('false', [], 'bool', lit=True))
            out.append(E(NULLLIT[node.cat], [], node.cat, lit=True))
        elif node.fmt not in (SIMPLE_LIT[node.cat], NULLLIT[node.cat], 'false'):
            out.append(E(SIMPLE_LIT[node.cat], [], node.cat, lit=True))
        return out
    if isinstance(node, Q):
        q = node
        if q.setop:
            n = copy.copy(q)
            n.setop = None
            out.append(n)
            rhs = copy.copy(q.setop[1])
            rhs.ctes = q.ctes
            rhs.order, rhs.limit, rhs.offset = q.order, q.limit, q.offset
            out.append(rhs)
        for i in range(len(q.ctes)):
            n = copy.copy(q)
            n.ctes = q.ctes[:i] + q.ctes[i + 1:]
            out.append(n)
        if len(q.items) > 1:
            for i in range(len(q.items)):
                out.append(drop_item(q, i))
        for i in range(len(q.frm)):
            if len(q.frm) > 1:
                n = copy.copy(q)
                n.frm = q.frm[:i] + q.frm[i + 1:]
                out.append(n)
        if q.where is not None:
            n = copy.copy(q)
            n.where = None
            out.append(n)
        if q.having is not None:
            n = copy.copy(q)
            n.having = None
            out.append(n)
        if q.group:
            n = copy.copy(q)
            n.group, n.having = [], None
            out.append(n)
            if len(q.group) > 1:
                for i in range(len(q.group)):
                    n = copy.copy(q)
                    n.group = q.group[:i] + q.group[i + 1:]
                    out.append(n)
        if q.distinct:
            n = copy.copy(q)
            n.distinct = False
            out.append(n)
        if q.offset is not None:
            n = copy.copy(q)
            n.offset = None
            out.append(n)
        if q.limit is not None:
            n = copy.copy(q)
            n.limit = None
            n.offset = None
            out.append(n)
        if q.order and q.limit is None:
            n = copy.copy(q)
            n.order = []
            out.append(n)
        return out
    if isinstance(node, FJ):
        out.append(node.left)
        out.append(node.right)
        if node.kind != 'join' and node.kind != 'cross join':
            out.append(FJ('join', node.left, node.right, node.on))
        if node.on is not None and node.kind != 'full join' and node.on.fmt != 'true':
            out.append(FJ(node.kind, node.left, node.right, E('true', [], 'bool', lit=True)))
        return out
    return out


def reduce_case(w, case, q, setup, sql, sql2, deadline):
    """Delta reduction of the query (its tree) and the data (rows, columns,
    statements). Returns (q, setup, sql, sql2)."""
    t_end = min(deadline, time.time() + w.args.reduce_secs)
    setup = Setup.from_js(setup.js())
    tlp = sql2 is not None and case['check'].startswith('tlp')
    norec = case['check'] == 'norec'
    if not w.still_fails(case, setup, sql, sql2):
        case['flaky'] = True
        return q, setup, sql, sql2
    # the TLP and NoREC pairs are text: reduce the data, then the base query
    # through regeneration is not possible; only the data
    holder = [copy.deepcopy(q)]

    def pair_sql(qq):
        return qq.sql(), None

    def test_q(qq):
        # ORDER BY may be reduced away: compare in order only when the candidate orders
        case['ordered'] = qq.ordered()
        return w.still_fails(case, setup, qq.sql(), None)

    if not (tlp or norec) and case['check'] != 'setup' and sql == q.sql():
        reduce_tree(holder, test_q, t_end)
        sql = holder[0].sql()

    def test_setup(st):
        if not (tlp or norec):
            case['ordered'] = holder[0].ordered()
        return w.still_fails(case, st, sql, sql2)

    setup = reduce_setup(setup, test_setup, t_end, [sql, sql2 or ''])
    if not (tlp or norec) and case['check'] != 'setup' and time.time() < t_end:
        reduce_tree(holder, test_q, t_end)
        sql = holder[0].sql()
        setup = reduce_setup(setup, test_setup, t_end, [sql])
    if not (tlp or norec):
        case['ordered'] = holder[0].ordered()
    return holder[0], setup, sql, sql2


def reduce_tree(holder, test, t_end):
    progress = True
    while progress and time.time() < t_end:
        progress = False
        nodes = []
        walk(holder[0], (lambda n: holder.__setitem__(0, n)), nodes)
        for setter, node in nodes:
            if time.time() > t_end:
                return
            for v in variants(node):
                setter(v)
                if test(holder[0]):
                    progress = True
                    break
                setter(node)
            if progress:
                break


def ddmin(items, test, t_end):
    """The classic delta debugging over a list: a smaller list that still fails."""
    if items and test([]):
        return []
    n = 2
    while len(items) >= 2 and time.time() < t_end:
        chunk = (len(items) + n - 1) // n
        done = False
        for s in range(0, len(items), chunk):
            comp = items[:s] + items[s + chunk:]
            if test(comp):
                items = comp
                n = max(n - 1, 2)
                done = True
                break
        if not done:
            if n >= len(items):
                break
            n = min(len(items), n * 2)
    return items


def reduce_setup(setup, test, t_end, sqls):
    text = ' '.join(sqls)
    st = Setup.from_js(setup.js())
    # statements after the load
    i = 0
    while i < len(st.post) and time.time() < t_end:
        cand = Setup.from_js(st.js())
        del cand.post[i]
        if test(cand):
            st = cand
        else:
            i += 1
    # tables not named in the query or a view
    for t in list(st.tables):
        used = re.search(r'\b%s\b' % t.name, text) or any(re.search(r'\b%s\b' % t.name, s) for k, s in st.post)
        if not used:
            cand = Setup.from_js(st.js())
            cand.tables = [x for x in cand.tables if x.name != t.name]
            if test(cand):
                st = cand
    # rows: ddmin per table
    for ti in range(len(st.tables)):
        def test_rows(rows, ti=ti):
            cand = Setup.from_js(st.js())
            cand.tables[ti].rows = rows
            return test(cand)
        rows = ddmin(st.tables[ti].rows, test_rows, t_end)
        st = Setup.from_js(st.js())
        st.tables[ti].rows = rows
    # columns not named anywhere
    for ti in range(len(st.tables)):
        j = 0
        while j < len(st.tables[ti].cols) and time.time() < t_end:
            t = st.tables[ti]
            cname = t.cols[j][0]
            used = re.search(r'\b%s\b' % cname, text) or any(re.search(r'\b%s\b' % cname, s) for k, s in st.post)
            if used or len(t.cols) == 1:
                j += 1
                continue
            cand = Setup.from_js(st.js())
            ct = cand.tables[ti]
            del ct.cols[j]
            ct.rows = [r[:j] + r[j + 1:] for r in ct.rows]
            if ct.pk == cname:
                ct.pk = None
            if test(cand):
                st = cand
            else:
                j += 1
    # values made simpler: NULL constraints off
    for ti in range(len(st.tables)):
        for j in range(len(st.tables[ti].cols)):
            if st.tables[ti].cols[j][3] and time.time() < t_end:
                cand = Setup.from_js(st.js())
                cand.tables[ti].cols[j][3] = False
                if test(cand):
                    st = cand
    return st


FEATURES = [
    ('left join', r'\bleft join\b'), ('right join', r'\bright join\b'), ('full join', r'\bfull join\b'),
    ('cross join', r'\bcross join\b'), ('join', r'(?<!left )(?<!right )(?<!full )(?<!cross )\bjoin\b'),
    ('lateral', r'\blateral\b'), ('exists', r'\bexists\b'), ('not exists', r'\bnot exists\b'),
    ('in-subquery', r'\bin \(select\b'), ('not in-subquery', r'\bnot in \(select\b'),
    ('any/all', r'\b(any|all|some) \(select'), ('scalar subquery', r'[(,=<>+*-] *\(select\b'),
    ('derived', r'from \(select|, \(select'), ('cte', r'^with\b'), ('group by', r'\bgroup by\b'),
    ('having', r'\bhaving\b'), ('distinct', r'\bselect distinct\b'), ('count(distinct)', r'\(distinct\b'),
    ('window', r'\bover \('), ('union', r'\bunion\b'), ('intersect', r'\bintersect\b'), ('except', r'\bexcept\b'),
    ('order by', r'\border by\b'), ('limit', r'\blimit\b'), ('offset', r'\boffset\b'), ('case', r'\bcase\b'),
    ('like', r'\blike\b|\bilike\b'), ('between', r'\bbetween\b'), ('filter', r'\bfilter \(where'),
    ('is distinct', r'\bis (not )?distinct from\b'), ('cast', r'\bcast\('), ('in-list', r'\bin \((?!select)'),
    ('not in-list', r'\bnot in \((?!select)'), ('coalesce', r'\bcoalesce\('), ('nullif', r'\bnullif\('),
    ('string_agg', r'\bstring_agg\('), ('avg', r'\bavg\('), ('sum', r'\bsum\('), ('min/max', r'\b(min|max)\('),
    ('count', r'\bcount\('), ('bool_and/or', r'\bbool_(and|or)\('),
]


def features(sql):
    s = (sql or '').lower()
    return sorted(set(n for n, rx in FEATURES if re.search(rx, s)))


def signature(case):
    sql = case.get('min_sql') or case['sql']
    parts = [case['check'], case['cls']]
    res = case.get('min_results') or case.get('results') or {}
    for k in sorted(res):
        v = res[k]
        if isinstance(v, dict) and v.get('kind') == 'error':
            parts.append('%s=%s:%s' % (k, v.get('code'), norm_msg(v.get('msg'))))
    parts.append(','.join(features(sql)))
    return ' | '.join(parts)


# ---------------------------------------------------------------- driving

def worker_main(wid, args, deadline, seed0):
    signal.signal(signal.SIGTERM, lambda *a: sys.exit(0))
    random.seed(seed0 * 1000 + wid)
    root = os.path.join(args.out, 'w%d' % wid)
    w = Worker(wid, args, root)
    seed = seed0 + wid
    last = 0
    try:
        while time.time() < deadline:
            if args.seeds and seed >= seed0 + args.seeds:
                break
            setup = gen_setup(random.Random('setup:%d' % seed))
            w.cur = setup
            try:
                for sname in list(w.servers):
                    w.load(sname, setup)
                if w.pg is not None:
                    w.load('pg', setup)
            except SetupError as e:
                with open(os.path.join(root, 'setup-errors.txt'), 'a') as f:
                    f.write('seed %d: %s\n' % (seed, e))
                seed += args.workers
                continue
            w.stats['seeds'] += 1
            for qi in range(args.queries):
                if time.time() >= deadline:
                    break
                r = random.Random('query:%d:%d' % (seed, qi))
                q = Gen(r, setup).select()
                w.stats['queries'] += 1
                try:
                    fails = w.check_query(q, setup, r)
                    for f in fails:
                        w.record(f, q, setup, seed, qi, deadline)
                        w.cur = setup
                except SetupError as e:
                    with open(os.path.join(root, 'setup-errors.txt'), 'a') as f:
                        f.write('seed %d query %d: %s\n' % (seed, qi, e))
                    break
                if time.time() - last > 30:
                    w.write_stats()
                    last = time.time()
            seed += args.workers
    finally:
        w.stats['last_seed'] = seed
        w.write_stats()
        w.stop()


def cmd_run(args):
    args.bin = os.path.realpath(args.bin)
    os.makedirs(args.out, exist_ok=True)
    args.out = os.path.realpath(args.out)
    args.checks = CHECKS_ALL if args.checks == 'all' else args.checks.split(',')
    pg = None
    if 'pg' in args.checks:
        pg = Postgres(args.pg_root or args.out, args.pg_port, args.cpus)
        pg.start()
        for i in range(args.workers):
            pg.ensure_db('fz%d' % i)
    deadline = time.time() + args.duration
    procs = []
    with open(os.path.join(args.out, 'run.json'), 'w') as f:
        json.dump({'bin': args.bin, 'seed': args.seed, 'workers': args.workers, 'duration': args.duration,
                   'checks': args.checks, 'queries': args.queries, 'start': time.time()}, f)
    try:
        for i in range(args.workers):
            p = multiprocessing.Process(target=worker_main, args=(i, args, deadline, args.seed))
            p.start()
            procs.append(p)
        for p in procs:
            p.join()
    finally:
        for p in procs:
            if p.is_alive():
                p.terminate()
                p.join(30)
        if pg:
            pg.stop()
    cmd_report(argparse.Namespace(dir=args.out, full=False))


def load_cases(d):
    out = []
    for path in sorted(glob.glob(os.path.join(d, 'w*', 'cases', '*.json'))):
        with open(path) as f:
            out.append(json.load(f))
    return out


SEVERITY = {'wrong': 0, 'crash': 1, 'hang': 2, 'errcode': 3, 'a-error': 4, 'b-error': 4}


def cmd_report(args):
    stats = []
    for path in sorted(glob.glob(os.path.join(args.dir, 'w*', 'stats.json'))):
        with open(path) as f:
            stats.append(json.load(f))
    tot = {}
    for s in stats:
        for k in ('queries', 'stmts', 'seeds', 'reduced', 'skipped', 'tlp', 'norec', 'lexdb_errors', 'pg_errors'):
            tot[k] = tot.get(k, 0) + s.get(k, 0)
        for k, v in s.get('fails', {}).items():
            tot.setdefault('fails', {})[k] = tot.setdefault('fails', {}).get(k, 0) + v
    el = max([s.get('elapsed', 0) for s in stats] or [0])
    print('run %s: %d workers, %.0f s, %d seeds, %d queries, %d statements, %d TLP and %d NoREC forms' % (
        args.dir, len(stats), el, tot.get('seeds', 0), tot.get('queries', 0), tot.get('stmts', 0),
        tot.get('tlp', 0), tot.get('norec', 0)))
    print('lexdb errors (on): %d, PostgreSQL errors: %d; failures by check:class: %s' % (
        tot.get('lexdb_errors', 0), tot.get('pg_errors', 0), json.dumps(tot.get('fails', {}), sort_keys=True)))
    cases = load_cases(args.dir)
    groups = {}
    for c in cases:
        if 'min_sql' not in c and c.get('check') != 'setup':
            continue
        groups.setdefault(c['signature'] if 'signature' in c else c['check'], []).append(c)
    rows = []
    for sig, cs in groups.items():
        best = min(cs, key=lambda c: len(c.get('min_sql') or c['sql']) + 10 * sum(
            len(t[3]) for t in (c.get('min_setup') or c['setup'] or {'tables': []})['tables']))
        rows.append((SEVERITY.get(best['cls'], 5), best['check'], sig, len(cs), best))
    rows.sort(key=lambda x: (x[0], x[1], -x[3]))
    for sev, chk, sig, n, c in rows:
        print('\n== %s  (%d cases; e.g. %s)' % (sig, n, c['id']))
        if c.get('min_setup_sql'):
            for s in c['min_setup_sql']:
                print('   ' + s + ';')
        print('   ' + (c.get('min_sql') or c['sql']) + ';')
        if c.get('min_sql2'):
            print('   -- vs ' + c['min_sql2'] + ';')
        for k, v in (c.get('min_results') or c.get('results') or {}).items():
            if v:
                print('   %s: %s' % (k, Res(v['kind'], rows=[tuple(x) for x in v.get('rows', [])], code=v.get('code'),
                                           msg=v.get('msg')).brief(6)))


def cmd_repro(args):
    with open(args.case) as f:
        case = json.load(f)
    setup = Setup.from_js(case.get('min_setup') or case['setup'])
    sql = case.get('min_sql') or case['sql']
    sql2 = case.get('min_sql2') if 'min_sql' in case else case.get('sql2')
    a = argparse.Namespace(bin=os.path.realpath(args.bin), port=args.port, cpus=args.cpus, checks=CHECKS_ALL,
                           variants=args.variants, pg_port=args.pg_port, reduce_wrong=0, reduce_err=0,
                           reduce_secs=0)
    if not args.pg:
        a.checks = [c for c in CHECKS_ALL if c != 'pg']
    root = os.path.join(args.work, 'repro')
    pg = None
    if args.pg:
        pg = Postgres(args.work, args.pg_port, args.cpus)
        pg.start()
        pg.ensure_db('fz9')
    w = Worker(9, a, root)
    try:
        for s in setup.stmts():
            print(s + ';')
        print(sql + ';')
        for cfg in LEXDB_CFGS:
            if LEXDB_CFGS[cfg][0] in w.servers:
                print('%-6s %s' % (cfg, w.run_cfg(cfg, sql, setup).brief()))
        if sql2:
            print('second %s' % w.run_cfg('on', sql2, setup).brief())
        if w.pg is not None:
            x = w.run_pg(sql, setup)
            print('pg     %s' % (x.brief() if x else 'timeout'))
    finally:
        w.stop()
        if pg:
            pg.stop()


VARIANT_CODE = '''
// lexdb_fuzz.py's build: the planner's test switches from the environment
// (LEXDB_FUZZ_UNNEST, _REWRITES, _BUSHY, _KEYORDER; unset: the defaults).
fn fuzzMode(name: &str): int {
    match os.env(&name) {
        Some(v) {
            match strings.parseIntOpt(&v) {
                Some(m) { return m }
                None {}
            }
        }
        None {}
    }
    return -1
}

fn fuzzModes() {
    let u = fuzzMode("LEXDB_FUZZ_UNNEST")
    if u >= 0 { lexdb_plan.setUnnest(u) }
    let w = fuzzMode("LEXDB_FUZZ_REWRITES")
    if w >= 0 { lexdb_plan.setRewrites(w) }
    let b = fuzzMode("LEXDB_FUZZ_BUSHY")
    if b >= 0 { lexdb_plan.setBushy(b) }
    let k = fuzzMode("LEXDB_FUZZ_KEYORDER")
    if k >= 0 { lexdb_plan.setKeyOrder(k) }
}
'''


def cmd_build(args):
    cmd = os.path.join(LEXELL, 'cmd')
    src = open(os.path.join(cmd, 'lexdb.lxl')).read()
    assert 'import "./lexdb_repl"\n' in src and 'fn main() {\n' in src
    src = src.replace('import "./lexdb_repl"\n', 'import "./lexdb_repl"\nimport "./lexdb_plan"\n', 1)
    src = src.replace('fn main() {\n', 'fn main() {\n    fuzzModes()\n', 1) + VARIANT_CODE
    tmp = os.path.join(cmd, 'lexdb_fuzzmain.lxl')
    with open(tmp, 'w') as f:
        f.write(src)
    lxlc = args.lxlc or os.path.join(LEXELL, 'compiler', 'out', 'lxlc')
    out = os.path.realpath(args.out)
    try:
        c = ['flock', '-s', os.path.expanduser('~/tpch/.bench.lock'), 'env', 'LXL_NOCACHE=1', 'taskset', '-c',
             args.build_cpus, lxlc, tmp, '-O', '-o', out]
        print(' '.join(c))
        subprocess.run(c, check=True, cwd=os.path.dirname(LEXELL))
    finally:
        os.unlink(tmp)
    print('built', out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    b = sub.add_parser('build', help='build lexdb with the planner switches read from LEXDB_FUZZ_*')
    b.add_argument('--out', default=os.path.expanduser('~/tpch-w/fuzz/lexdb-fuzz-O'))
    b.add_argument('--lxlc', default=None)
    b.add_argument('--build-cpus', default='4-7,12-15')
    for name in ('run', 'repro'):
        p = sub.add_parser(name)
        p.add_argument('--bin', required=True, help='a lexdb binary (from build for the alt and force checks)')
        p.add_argument('--port', type=int, default=55700, help='worker i uses PORT+10i .. +3')
        p.add_argument('--pg-port', type=int, default=55690)
        p.add_argument('--cpus', default='8-11', help='CPUs for every server (taskset), nice 15')
        p.add_argument('--no-variants', dest='variants', action='store_false',
                       help='the binary does not read LEXDB_FUZZ_*: no alt and force checks')
        if name == 'run':
            p.add_argument('--out', default=os.path.expanduser('~/tpch-w/fuzz/run'))
            p.add_argument('--seed', type=int, default=1, help='worker i takes seeds SEED+i, SEED+i+W, ...')
            p.add_argument('--seeds', type=int, default=0, help='stop after this many seeds (0: run until --duration)')
            p.add_argument('--workers', type=int, default=3)
            p.add_argument('--duration', type=float, default=600, help='seconds')
            p.add_argument('--queries', type=int, default=150, help='queries per seed (schema and data)')
            p.add_argument('--checks', default='all', help='comma list of ' + ','.join(CHECKS_ALL))
            p.add_argument('--pg-root', default=None, help="PostgreSQL's directory (default: --out)")
            p.add_argument('--reduce-wrong', type=int, default=25,
                           help='reductions per worker of each check:class of wrong results, crashes, hangs')
            p.add_argument('--reduce-err', type=int, default=2,
                           help='reductions per worker of each error-message pair')
            p.add_argument('--reduce-secs', type=float, default=120, help='time limit of one reduction')
        else:
            p.add_argument('case')
            p.add_argument('--work', default=os.path.expanduser('~/tpch-w/fuzz/repro'))
            p.add_argument('--pg', action='store_true', help='also run it on a PostgreSQL started in --work')
    r = sub.add_parser('report')
    r.add_argument('dir')
    r.add_argument('--full', action='store_true')
    args = ap.parse_args()
    {'build': cmd_build, 'run': cmd_run, 'report': cmd_report, 'repro': cmd_repro}[args.cmd](args)


if __name__ == '__main__':
    main()
