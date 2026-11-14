#!/usr/bin/env python3
"""python-oracledb (thin) against lexdb's TNS door: ALTER SESSION (NLS_*, TIME_ZONE, CURRENT_SCHEMA),
TO_CHAR/TO_DATE following the session, the ORA- errors, DESCRIBE's types, CLOB/BLOB (LONG fetch and
LOB locators), cancel, CREATE USER / GRANT / REVOKE / DROP USER (design/lexdb-oracle.md, O5).

    python3 lexell/tests/lexdb/oracledb_o5.py [--lexdb PATH] [--tns-port 15214]

Answers checked against Oracle Database Free 23ai on 2026-11-13, except that a table that can be
read but not changed is ORA-01031 here (23ai says ORA-41900), a locked account is ORA-01045 here
(ORA-28000 there). Needs python-oracledb. Starts its own lexdb (a built cmd/lexdb.lxl) in a temporary directory."""
import argparse, datetime, decimal, shutil, subprocess, sys, tempfile, threading, time
import oracledb

ap = argparse.ArgumentParser()
ap.add_argument('--lexdb', default='lexdb')
ap.add_argument('--tns-port', type=int, default=15214)
ap.add_argument('--pg-port', type=int, default=15216)
a = ap.parse_args()
tmp = tempfile.mkdtemp()
srv = subprocess.Popen([a.lexdb, tmp + '/data', '127.0.0.1:%d' % a.pg_port, '--tns', '127.0.0.1:%d' % a.tns_port],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(2)
failed = 0


def check(name, got, want):
    global failed
    if got != want:
        failed += 1
        print('FAIL', name, 'got', repr(got)[:300], 'want', repr(want)[:300])
    else:
        print('ok  ', name)


def code(f):
    try:
        f()
        return None
    except oracledb.Error as e:
        return e.args[0].code


try:
    dsn = '127.0.0.1:%d/lexdb' % a.tns_port
    conn = oracledb.connect(user='sa', password='sa', dsn=dsn)
    cur = conn.cursor()

    def ex(sql, p=None):
        cur.execute(sql, p) if p is not None else cur.execute(sql)
        return cur.fetchall() if cur.description else cur.rowcount

    # ---- NLS
    ex("create table ev (id number(10) primary key, d date, ts timestamp(6), name varchar2(30), amt number(10,2))")
    ex("insert into ev values (1, to_date('2024-03-05 13:14:15', 'YYYY-MM-DD HH24:MI:SS'), "
       "to_timestamp('2024-03-05 13:14:15.250000', 'YYYY-MM-DD HH24:MI:SS.FF6'), 'one', 12.5)")
    conn.commit()
    check('default to_char', ex("select to_char(d), to_char(ts) from ev"), [('05-MAR-24', '05-MAR-24 01.14.15.250000 PM')])
    ex("alter session set nls_date_format = 'YYYY-MM-DD HH24:MI:SS'")
    check('nls_date_format', ex("select to_char(d) from ev"), [('2024-03-05 13:14:15',)])
    check('to_date follows', ex("select to_date('2025-01-02 03:04:05') from dual"), [(datetime.datetime(2025, 1, 2, 3, 4, 5),)])
    ex("alter session set nls_timestamp_format = 'DD/MM/YYYY HH24:MI:SS.FF3'")
    check('nls_timestamp_format', ex("select to_char(ts) from ev"), [('05/03/2024 13:14:15.250',)])
    check('explicit format wins', ex("select to_char(d, 'DD.MM.YYYY') from ev"), [('05.03.2024',)])
    check('bad date format', code(lambda: ex("alter session set nls_date_format = 'ZZZZ'")), 1821)
    ex("alter session set nls_territory = 'GERMANY'")
    check('bad territory', code(lambda: ex("alter session set nls_territory = 'ATLANTIS'")), 12705)
    check('bad language', code(lambda: ex("alter session set nls_language = 'KLINGON'")), 12705)
    ex("alter session set nls_language = 'GERMAN'")
    check('bad option', code(lambda: ex("alter session set no_such_parameter = 1")), 2248)
    check('in the settings', ex("select current_setting('oracle.nls_territory'), current_setting('oracle.nls_language')"), [('GERMANY', 'GERMAN')])
    # ---- time zone
    ex("alter session set time_zone = '+05:30'")
    check('time zone offset', ex("select current_setting('TimeZone')"), [('<+05:30>-05:30',)])
    ex("alter session set time_zone = 'Europe/Paris'")
    check('time zone region', ex("select current_setting('TimeZone')"), [('Europe/Paris',)])
    check('bad time zone', code(lambda: ex("alter session set time_zone = 'Mars/Olympus'")), 1882)
    ex("alter session set time_zone = 'LOCAL'")
    conn.rollback()
    # ---- errors
    ex("create table nn (a number(3), b number(5,2), c varchar2(3), id number generated always as identity)")
    check('01438', code(lambda: ex("insert into nn (a) values (12345)")), 1438)
    check('01438 scale', code(lambda: ex("insert into nn (b) values (123456.7)")), 1438)
    check('12899', code(lambda: ex("insert into nn (c) values ('abcdef')")), 12899)
    check('32795', code(lambda: ex("insert into nn (a, id) values (1, 5)")), 32795)
    check('00942', code(lambda: ex("select * from nope")), 942)
    check('00001', code(lambda: ex("insert into ev (id) values (1)")), 1)
    check('00904', code(lambda: ex("select nope from ev")), 904)
    check('01476', code(lambda: ex("select 1/0 from dual")), 1476)
    check('01722', code(lambda: ex("select to_number('x') from dual")), 1722)
    check('00955', code(lambda: ex("create table ev (a int)")), 955)
    conn.rollback()
    # ---- describe
    cur.execute("select id, d, ts, name, amt from ev")
    d = [(c[0], c[1], c[2], c[3], c[4], c[5], c[6]) for c in cur.description]
    check('describe types', [c[1] for c in d], [oracledb.DB_TYPE_NUMBER, oracledb.DB_TYPE_DATE, oracledb.DB_TYPE_TIMESTAMP,
                                                 oracledb.DB_TYPE_VARCHAR, oracledb.DB_TYPE_NUMBER])
    check('describe precision', [(c[4], c[5]) for c in d], [(10, 0), (None, None), (0, 6), (None, None), (10, 2)])
    check('describe length', d[3][3], 30)
    cur.execute("select sysdate, to_date('2020-01-01', 'YYYY-MM-DD'), systimestamp from dual")
    check('date expressions', [c[1] for c in cur.description][:2], [oracledb.DB_TYPE_DATE, oracledb.DB_TYPE_DATE])
    cur.fetchall()
    # ---- LOBs
    ex("create table docs (id number(5) primary key, body clob, img blob)")
    big = 'caf\u00e9 ' * 20000
    raw = bytes(range(256)) * 300
    ex("insert into docs values (:1, :2, :3)", [1, big, raw])
    ex("insert into docs values (:1, :2, :3)", [2, 'small', b'\x01\x02'])
    ex("insert into docs values (:1, :2, :3)", [3, None, None])
    conn.commit()
    cur.execute("select id, body, img from docs order by id")
    check('lob types', [c[1] for c in cur.description], [oracledb.DB_TYPE_NUMBER, oracledb.DB_TYPE_CLOB, oracledb.DB_TYPE_BLOB])
    rows = cur.fetchall()
    check('fetch_lobs: CLOB', [type(r[1]).__name__ for r in rows], ['LOB', 'LOB', 'NoneType'])
    check('CLOB read', rows[0][1].read(), big)
    check('CLOB size', rows[0][1].size(), len(big))
    check('CLOB part', rows[0][1].read(2, 4), 'af\u00e9 '[0:4])
    check('BLOB read', rows[0][2].read(), raw)
    check('BLOB part', rows[1][2].read(2, 1), b'\x02')
    check('small CLOB', rows[1][1].read(), 'small')
    oracledb.defaults.fetch_lobs = False
    cur.execute("select id, body, img from docs order by 1")
    rows = cur.fetchall()
    check('LONG fetch', [(r[0], r[1] == big if r[0] == 1 else r[1], r[2] == raw if r[0] == 1 else r[2]) for r in rows],
          [(1, True, True), (2, 'small', b'\x01\x02'), (3, None, None)])
    cur.execute("select id, body from docs where id = :1", [2])
    check('LONG fetch again', cur.fetchall(), [(2, 'small')])
    oracledb.defaults.fetch_lobs = True
    lob = conn.createlob(oracledb.DB_TYPE_CLOB)
    lob.write('temp \u20ac clob')
    ex("insert into docs (id, body) values (:1, :2)", [4, lob])
    cur.execute("select body from docs where id = 4")
    check('temp LOB bound', cur.fetchone()[0].read(), 'temp \u20ac clob')
    ex("delete from docs where id = 4")
    conn.commit()
    # ---- cancel
    # (lexdb cannot stop a statement in flight: the break is answered when the call ends, with ORA-01013)
    threading.Timer(0.2, conn.cancel).start()
    check('cancel', code(lambda: ex("select count(*) from generate_series(1, 2000000)")), 1013)
    check('usable after cancel', ex("select 1 from dual"), [(1,)])
    conn.cancel()
    check('cancel when idle', code(lambda: ex("select 2 from dual")), 1013)
    check('and then', ex("select 3 from dual"), [(3,)])
    # ---- users
    ex("create user app1 identified by pw1")
    check('user exists', code(lambda: ex("create user APP1 identified by pw2")), 1920)
    check('no create session', code(lambda: oracledb.connect(user='app1', password='pw1', dsn=dsn)), 1045)
    ex("grant create session to app1")
    ex("grant create table, unlimited tablespace to app1")
    check('wrong password', code(lambda: oracledb.connect(user='app1', password='bad', dsn=dsn)), 1017)
    c2 = oracledb.connect(user='app1', password='pw1', dsn=dsn)
    cu2 = c2.cursor()
    cu2.execute("select user, sys_context('userenv', 'current_schema') from dual") if False else None
    cu2.execute("create table mine (a number)")
    cu2.execute("insert into mine values (1)")
    c2.commit()
    check('own schema', ex("select table_name from information_schema.tables where table_schema = 'app1'"), [('MINE',)])
    ex("create table pub (a number)")
    ex("insert into pub values (7)")
    conn.commit()
    check('no privilege', code(lambda: cu2.execute("select * from pub").fetchall()), 942)
    ex("grant select on pub to app1")
    check('granted', cu2.execute("select * from pub").fetchall(), [(7,)])
    check('not insert', code(lambda: cu2.execute("insert into pub values (8)")), 1031)
    ex("grant insert on pub to app1")
    cu2.execute("insert into pub values (8)")
    c2.commit()
    ex("revoke insert on pub from app1")
    check('revoked', code(lambda: cu2.execute("insert into pub values (9)")), 1031)
    ex("alter session set current_schema = app1")
    check('current_schema', ex("select * from mine"), [(1,)])
    check('bad current_schema', code(lambda: ex("alter session set current_schema = nobody")), 1435)
    ex("alter session set current_schema = sa")
    c2.close()
    ex("alter user app1 identified by pw3")
    c3 = oracledb.connect(user='app1', password='pw3', dsn=dsn)
    c3.close()
    ex("alter user app1 account lock")
    check('locked', code(lambda: oracledb.connect(user='app1', password='pw3', dsn=dsn)), 1045)
    check('drop needs cascade', code(lambda: ex("drop user app1")), 1922)
    ex("drop user app1 cascade")
    check('dropped', code(lambda: oracledb.connect(user='app1', password='pw3', dsn=dsn)), 1017)
    check('no such user', code(lambda: ex("drop user app1")), 1918)
    check('grant to nobody', code(lambda: ex("grant create session to nobody")), 1917)
    conn.close()
finally:
    srv.terminate()
    srv.wait()
    shutil.rmtree(tmp, ignore_errors=True)
print('FAILED' if failed else 'all passed')
sys.exit(1 if failed else 0)
