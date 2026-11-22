#!/usr/bin/env python3
"""Checks an exec_* test written as exec_leftovers is (a SETUP constant of statements, a line each, and a QS constant of
`label<TAB>sql` lines; expect lines `label: rows, same: true`, rows joined by ";", columns by "|", NULL as NULL) against a
PostgreSQL server: runs the setup in a new database, each query in a transaction rolled back, and prints every answer that
differs from the test's expect line (an error as ERROR and its SQLSTATE). It writes nothing.

    python3 lexell/tests/lexdb/check_pg.py "host=127.0.0.1 port=55442 user=me" exec_recursion [...]

The scratch PostgreSQL 18 of ~/Work/lexdb-bench/saved/README.md is the one used. Needs psql.
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def unescape(s):
    return re.sub(r'\\(.)', lambda m: {'n': '\n', 't': '\t', 'r': '\r'}.get(m.group(1), m.group(1)), s)


def psql(conn, db, *cmds):
    args = ['psql', conn + ' dbname=' + db, '-X', '-A', '-t', '-F', '|', '-P', 'null=NULL', '-v', 'VERBOSITY=sqlstate']
    for c in cmds:
        args += ['-c', c]
    return subprocess.run(args, capture_output=True, text=True)


def check(conn, name):
    text = open(os.path.join(HERE, 'run', name + '.lxl'), encoding='utf-8').read()
    consts = {m.group(1): unescape(m.group(2)) for m in re.finditer(r'^const (\w+) = "((?:[^"\\]|\\.)*)"$', text, re.M)}
    exp = {}
    for l in text.split('\n'):
        if l.startswith('// expect: '):
            label, _, rest = l[len('// expect: '):].partition(': ')
            exp[label] = rest.rsplit(', same: ', 1)[0]
    db = 'lexdb_check_' + name
    psql(conn, 'postgres', 'drop database if exists ' + db)
    psql(conn, 'postgres', 'create database ' + db)
    for s in consts['SETUP'].split('\n'):
        r = psql(conn, db, s)
        if 'ERROR' in r.stderr:
            print('%s: setup %r: %s' % (name, s[:80], r.stderr.strip()))
    bad = 0
    n = 0
    for line in consts['QS'].split('\n'):
        label, sql = line.split('\t', 1)
        r = psql(conn, db, "set statement_timeout = '20s'", 'begin', sql, 'rollback')
        err = [l for l in r.stderr.split('\n') if l.startswith('ERROR')]
        if err:
            got = 'ERROR ' + err[0].split()[-1]
        else:
            rows = [l for l in r.stdout.split('\n') if l not in ('SET', 'BEGIN', 'ROLLBACK', '')]
            got = ';'.join(rows)
        n += 1
        if exp.get(label) != got:
            bad += 1
            print('DIFF %s: %s\n  lexdb:      %s\n  PostgreSQL: %s' % (name, label, exp.get(label), got))
    psql(conn, 'postgres', 'drop database ' + db)
    print('%s: %d answers checked, %d differences' % (name, n, bad))
    return bad


def main():
    conn = sys.argv[1]
    bad = 0
    for name in sys.argv[2:]:
        bad += check(conn, name)
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
