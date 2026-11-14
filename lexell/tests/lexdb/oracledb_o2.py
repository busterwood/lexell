#!/usr/bin/env python3
"""python-oracledb (thin) against lexdb's TNS door: binds (:1, :name, every type,
NULL), executemany (array DML, arraydmlrowcounts, batcherrors), RETURNING INTO,
statement reuse (re-execute), fetchmany, a pool, TCPS (design/lexdb-oracle.md, O2).

    python3 lexell/tests/lexdb/oracledb_o2.py [--lexdb PATH] [--tns-port 15211] [--tcps-port 15221]

Needs python-oracledb (pip install oracledb) and openssl. Starts its own lexdb
(a built cmd/lexdb.lxl) in a temporary directory."""
import argparse, datetime, decimal, shutil, ssl, subprocess, sys, tempfile, time
import oracledb

ap = argparse.ArgumentParser()
ap.add_argument('--lexdb', default='lexdb')
ap.add_argument('--tns-port', type=int, default=15211)
ap.add_argument('--tcps-port', type=int, default=15221)
ap.add_argument('--pg-port', type=int, default=15311)
a = ap.parse_args()
tmp = tempfile.mkdtemp()
subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', tmp + '/k.pem', '-out', tmp + '/c.pem',
                '-days', '2', '-subj', '/CN=localhost', '-addext', 'subjectAltName=DNS:localhost,IP:127.0.0.1'],
               check=True, capture_output=True)
srv = subprocess.Popen([a.lexdb, tmp + '/data', '127.0.0.1:%d' % a.pg_port, '--tns', '127.0.0.1:%d' % a.tns_port,
                        '--tcps', '127.0.0.1:%d' % a.tcps_port, '--tls-cert', tmp + '/c.pem', '--tls-key', tmp + '/k.pem'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(2)
failed = 0


def check(name, got, want):
    global failed
    if got != want:
        failed += 1
        print('FAIL', name, 'got', repr(got)[:200], 'want', repr(want)[:200])
    else:
        print('ok  ', name)


try:
    dsn = '127.0.0.1:%d/lexdb' % a.tns_port
    conn = oracledb.connect(user='sa', password='sa', dsn=dsn)
    cur = conn.cursor()

    def ex(sql, p=None):
        cur.execute(sql, p) if p is not None else cur.execute(sql)
        return cur.fetchall() if cur.description else cur.rowcount

    ex('create table t (id int primary key, n numeric(12,3), s text)')
    check('positional', ex('insert into t (id, n, s) values (:1, :2, :3)', [1, decimal.Decimal('12.345'), 'one']), 1)
    check('named', ex('insert into t (id, n, s) values (:id, :n, :s)', {'id': 2, 'n': 2, 's': 'two'}), 1)
    check('select', ex('select id, n, s from t where id = :1 or id = :2 order by id', [1, 2]), [(1, 12.345, 'one'), (2, 2, 'two')])
    check('name twice', ex('select :x, :x + 1 from dual', {'x': 5}), [(5, 6)])
    check('null', ex('select :1 from dual', [None]), [(None,)])
    check('types', ex('select :1, :2, :3, :4, :5 from dual', [b'\x01\x02', True, 2.5, 'txt', datetime.datetime(2020, 1, 2, 3, 4, 5)]),
          [(b'\x01\x02', True, 2.5, 'txt', datetime.datetime(2020, 1, 2, 3, 4, 5))])
    check('long text', ex('select length(:1) from dual', ['y' * 7000]), [(7000,)])
    cur.executemany('insert into t (id, n, s) values (:1, :2, :3)', [(10 + i, i, 'r%d' % i) for i in range(2000)])
    check('executemany', cur.rowcount, 2000)
    cur.executemany('update t set n = n + :1 where id = :2', [(1, 10), (1, 11), (1, 99999)], arraydmlrowcounts=True)
    check('rowcounts', cur.getarraydmlrowcounts(), [1, 1, 0])
    o1, o2 = cur.var(int), cur.var(str)
    cur.execute('insert into t (id, n, s) values (:1, :2, :3) returning id, s into :a, :b', [5000, 7, 'ret', o1, o2])
    check('returning', (o1.getvalue(), o2.getvalue()), ([5000], ['ret']))
    o3 = cur.var(int)
    cur.execute('delete from t where id >= :1 and id < :2 returning id into :o', [10, 13, o3])
    check('returning many', o3.getvalue(), [10, 11, 12])
    conn.commit()
    try:
        cur.executemany('insert into t (id) values (:1)', [(7001,), (7002,), (1,), (7003,)])
        check('array error', None, 'error')
    except oracledb.Error as e:
        check('array error', e.args[0].code, 1)
    check('rows before the error stay', ex('select id from t where id > 7000 order by id'), [(7001,), (7002,)])
    conn.rollback()
    cur.executemany('insert into t (id) values (:1)', [(8001,), (8002,), (1,), (8003,), (2,)], batcherrors=True)
    check('batcherrors', [(e.offset, e.code) for e in cur.getbatcherrors()], [(2, 1), (4, 1)])
    check('batch rows', ex('select id from t where id > 8000 order by id'), [(8001,), (8002,), (8003,)])
    out = []
    for i in range(4):
        cur.execute('select s from t where id = :1', [13 + i])
        out.append(cur.fetchone())
    check('statement reused', out, [('r3',), ('r4',), ('r5',), ('r6',)])
    cur.execute('select id from t where id >= :1 and id < :2 order by id', [20, 30])
    check('fetchmany', (cur.fetchmany(3), len(cur.fetchall())), ([(20,), (21,), (22,)], 7))
    try:
        ex('select * from nope where a = :1', [1])
        check('error', None, 'error')
    except oracledb.Error as e:
        check('error in a transaction', e.args[0].code, 942)
    check('after the error', ex('select :1 from dual', [7]), [(7,)])
    conn.commit()
    pool = oracledb.create_pool(user='sa', password='sa', dsn=dsn, min=1, max=3)
    got = []
    for i in range(3):
        with pool.acquire() as c:
            cc = c.cursor()
            cc.execute('select count(*) from t where id < :1', [100 + i])
            got.append(cc.fetchone()[0] > 0)
    check('pool', got, [True, True, True])
    conn.close()
    ctx = ssl.create_default_context(cafile=tmp + '/c.pem')
    tc = oracledb.connect(user='sa', password='sa', dsn='tcps://127.0.0.1:%d/lexdb' % a.tcps_port, ssl_context=ctx,
                          ssl_server_dn_match=False)
    check('tcps', tc.cursor().execute('select :1 from dual', ['over tls']).fetchall(), [('over tls',)])
    tc.close()
finally:
    srv.terminate()
    srv.wait()
    shutil.rmtree(tmp, ignore_errors=True)
print('FAILED' if failed else 'all passed')
sys.exit(1 if failed else 0)
