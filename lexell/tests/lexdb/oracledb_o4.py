#!/usr/bin/env python3
"""python-oracledb (thin) against lexdb's TNS door: the catalog queries that drivers and tools
send on connect and when browsing (python-oracledb's own, JDBC's DatabaseMetaData with the old
(+) outer joins, SQL Developer's, SQLcl's, DBeaver's and ODP.NET's, as far as they are known),
with binds (design/lexdb-oracle.md, O4).

    python3 lexell/tests/lexdb/oracledb_o4.py [--lexdb PATH] [--tns-port 15213] [--pg-port 15313]

Needs python-oracledb (pip install oracledb). Starts its own lexdb (a built cmd/lexdb.lxl) in a
temporary directory. The answers of the same queries in tns_catalog.lxl are Oracle's."""
import argparse, shutil, subprocess, sys, tempfile, time
import oracledb

ap = argparse.ArgumentParser()
ap.add_argument('--lexdb', default='lexdb')
ap.add_argument('--tns-port', type=int, default=15213)
ap.add_argument('--pg-port', type=int, default=15313)
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


try:
    conn = oracledb.connect(user='app', password='app', dsn='127.0.0.1:%d/freepdb1' % a.tns_port)
    cur = conn.cursor()

    def ex(sql, p=None):
        cur.execute(sql, p) if p is not None else cur.execute(sql)
        return cur.fetchall() if cur.description else cur.rowcount

    check('version', conn.version[:2], '23')
    ex('create table dept (deptno number(4) primary key, dname varchar2(30) not null, loc varchar2(20))')
    ex('create table emp (empno number(6) primary key, ename varchar2(50) not null, sal number(8,2), hired date, '
       'deptno number(4) references dept (deptno))')
    ex('create index emp_ename_ix on emp (ename)')
    ex('create sequence emp_seq')
    ex('create view emp_v as select empno, ename from emp')
    # python-oracledb: Connection.current_schema, the service name, a hint
    check('current_schema', ex("select sys_context('userenv', 'current_schema') from dual"), [('APP',)])
    check('service', ex("select sys_context('userenv', 'service_name') from dual")[0][0].upper(), 'FREEPDB1')
    check('hint', ex('select /*+ RESULT_CACHE */ 1 from dual'), [(1,)])
    # SQL Developer / SQLcl on connect
    check('banner', ex("select banner from v$version where banner like 'Oracle%'")[0][0][:6], 'Oracle')
    check('instance', len(ex('select instance_name, host_name, version, status from v$instance')), 1)
    check('db_name', ex("select name from v$database"), [('LEXDB',)])
    check('session', ex("select username, schemaname from v$session where sid = sys_context('userenv', 'sid')"), [('APP', 'APP')])
    check('parameter', ex("select value from v$parameter where name = 'db_block_size'"), [('8192',)])
    check('nls', ex("select value from nls_database_parameters where parameter = 'NLS_CHARACTERSET'"), [('AL32UTF8',)])
    check('nls session', ex("select value from nls_session_parameters where parameter = :1", ['NLS_DATE_FORMAT']), [('DD-MON-RR',)])
    check('has app', ('APP',) in ex('select username from all_users'), True)
    # DBeaver / JDBC browsing, with binds
    check('tables', ex('select table_name from all_tables where owner = :1 order by table_name', ['APP']), [('DEPT',), ('EMP',)])
    check('objects', ex('select object_name, object_type from all_objects where owner = :o and object_type in (:a, :b) order by object_type, object_name',
                        {'o': 'APP', 'a': 'TABLE', 'b': 'VIEW'}), [('DEPT', 'TABLE'), ('EMP', 'TABLE'), ('EMP_V', 'VIEW')])
    check('columns', ex('select column_name, data_type, data_length, nullable from all_tab_cols where owner = :1 and table_name = :2 order by column_id',
                        ['APP', 'DEPT']), [('DEPTNO', 'NUMBER', 22, 'N'), ('DNAME', 'VARCHAR2', 30, 'N'), ('LOC', 'VARCHAR2', 20, 'Y')])
    check('indexes', ex("select index_name from all_indexes where table_owner = 'APP' and table_name = 'EMP' order by 1")[0], ('EMP_ENAME_IX',))
    check('ind columns', ex("select column_name from all_ind_columns where index_name = 'EMP_ENAME_IX' order by column_position"), [('ENAME',)])
    check('pk', [r[0] for r in ex("select c.column_name from all_cons_columns c, all_constraints k where k.constraint_type = 'P' and k.table_name = :1 "
                                  "and k.owner = c.owner and k.constraint_name = c.constraint_name order by c.position", ['DEPT'])], ['DEPTNO'])
    check('fk', ex("select r_constraint_name is not null from user_constraints where table_name = 'EMP' and constraint_type = 'R'")[0][0] in (1, True), True)
    check('sequences', ex('select sequence_name from user_sequences'), [('EMP_SEQ',)])
    check('views', ex('select view_name from all_views where owner = :1', ['APP']), [('EMP_V',)])
    check('synonyms', ex('select count(*) from all_synonyms where owner = :1', ['PUBLIC'])[0][0] >= 0, True)
    check('source', ex("select count(*) from all_source where owner = 'APP'"), [(0,)])
    check('dictionary', ex("select count(*) from dictionary where table_name = 'ALL_TABLES'"), [(1,)])
    check('description', [d[0] for d in (cur.execute('select * from user_tables where 1 = 0'), cur.description)[1]][:3], ['TABLE_NAME', 'TABLESPACE_NAME', 'CLUSTER_NAME'])
    try:
        ex('select * from user_nothing')
        check('missing', 'no error', 'ORA-00942')
    except oracledb.DatabaseError as e:
        check('missing', str(e)[:9], 'ORA-00942')
    conn.close()
finally:
    srv.terminate()
    srv.wait()
    shutil.rmtree(tmp, ignore_errors=True)
print('FAILED' if failed else 'all ok', failed)
sys.exit(1 if failed else 0)
