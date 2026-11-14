#!/usr/bin/env python3
"""Regenerates cmd/lexdb_oradata.lxl: Oracle's catalog views as lexdb_oracat serves them
(design/lexdb-oracle.md, O4), recorded from a real Oracle Database Free
(tools/oracle_container.sh, or any container: pass --dsn).

    python3 lexell/tools/gen_oracle_catalog.py --system-dsn USER/PASSWORD@HOST:PORT/FREEPDB1 [--out cmd/lexdb_oradata.lxl]

Needs python-oracledb (pip install oracledb). It makes a demo schema in the account
APP (the DSN's user must be able to: the container's APP user), reads from it and
SYSTEM, and drops the demo tables again.

What it records, for each view lexdb serves: its columns (name, Oracle type, length,
precision, scale, nullable), from SYS's own definition; its "full" rows where lexdb
gives Oracle's as they are (V$VERSION, NLS_*_PARAMETERS, V$OPTION, ...); its "template"
rows (one for each kind of object: the demo schema's rows of ALL_TABLES, ALL_TAB_COLUMNS
of each type, ALL_INDEXES, ALL_CONSTRAINTS of each type, ...) which lexdb_exec fills in
with the names and numbers of lexdb's own objects; and the PUBLIC synonyms of those views.
"""
import argparse, datetime, os, sys
import oracledb

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# Views of the ALL_/USER_/DBA_ families lexdb builds from its own catalog (the base's name), and those
# it serves empty (Oracle's shape, no rows).
BUILT = ['TABLES', 'TAB_COLUMNS', 'TAB_COLS', 'INDEXES', 'IND_COLUMNS', 'CONSTRAINTS', 'CONS_COLUMNS', 'OBJECTS',
         'SEQUENCES', 'VIEWS', 'TAB_COMMENTS', 'COL_COMMENTS', 'TAB_IDENTITY_COLS', 'CATALOG']
EMPTY = ['SYNONYMS', 'SOURCE', 'TRIGGERS', 'PROCEDURES', 'ARGUMENTS', 'DB_LINKS', 'MVIEWS', 'TYPES', 'LOBS',
         'IND_EXPRESSIONS', 'TAB_PRIVS', 'RECYCLEBIN', 'ERRORS', 'DEPENDENCIES', 'DIRECTORIES', 'SEGMENTS',
         'TAB_PARTITIONS', 'PART_TABLES', 'OBJECT_TABLES', 'XML_TABLES', 'COL_PRIVS', 'TAB_STATISTICS', 'TAB_MODIFICATIONS',
         'TYPE_ATTRS', 'TYPE_METHODS', 'NESTED_TABLES', 'PLSQL_OBJECT_SETTINGS', 'SCHEDULER_JOBS', 'ENCRYPTED_COLUMNS',
         'REFS', 'LOG_GROUPS', 'POLICIES', 'JOBS', 'QUEUES', 'DIMENSIONS', 'CLUSTERS', 'SNAPSHOTS', 'MVIEW_LOGS',
         'SUBPART_KEY_COLUMNS', 'PART_KEY_COLUMNS', 'PART_INDEXES', 'IND_PARTITIONS', 'TAB_SUBPARTITIONS',
         'EXTERNAL_TABLES', 'VIEWS_AE']
# Views whose rows (all of them) are Oracle's, each: the real view's name, then the WHERE that picks them.
FULL = {
    'V_$VERSION': '', 'V_$OPTION': '', 'V_$NLS_PARAMETERS': '', 'NLS_DATABASE_PARAMETERS': '', 'NLS_INSTANCE_PARAMETERS': '',
    'NLS_SESSION_PARAMETERS': '', 'PRODUCT_COMPONENT_VERSION': '', 'DATABASE_PROPERTIES': "WHERE property_name NOT LIKE 'RECO_%' AND property_name NOT LIKE '%VERIFIER%'",
    'DBA_TABLESPACES': '', 'USER_TABLESPACES': '', 'ALL_EDITIONS': '', 'DBA_EDITIONS': '', 'SESSION_ROLES': '',
    'SESSION_PRIVS': '', 'USER_ROLE_PRIVS': '', 'USER_SYS_PRIVS': '', 'USER_TS_QUOTAS': '', 'V_$NLS_VALID_VALUES': 'WHERE ROWNUM <= 0',
    'V_$CONTAINERS': 'WHERE ROWNUM <= 0',
}
APP_FULL = ['SESSION_ROLES', 'SESSION_PRIVS', 'USER_ROLE_PRIVS', 'USER_SYS_PRIVS', 'USER_TS_QUOTAS', 'USER_TABLESPACES']
# Views lexdb fills in from one real row (the session's, the instance's).
TEMPLATE = {'V_$INSTANCE': '', 'V_$DATABASE': '', 'USER_USERS': ''}
# Views served empty that are not in the families (Oracle's shape).
EMPTY_PLAIN = ['V_$SQL', 'V_$SQLAREA', 'V_$MYSTAT', 'V_$STATNAME', 'V_$OPEN_CURSOR', 'V_$TRANSACTION', 'V_$LOCK', 'V_$SESSTAT',
               'V_$PROCESS', 'V_$SYSSTAT', 'V_$SESSION_LONGOPS', 'V_$SQL_PLAN', 'V_$SQLTEXT', 'V_$LOCKED_OBJECT',
               'V_$DATAFILE', 'V_$TABLESPACE', 'V_$SGA', 'V_$PGASTAT', 'V_$DIAG_INFO', 'V_$TIMEZONE_NAMES',
               'ALL_DB_LINKS', 'USER_DB_LINKS', 'DBA_DB_LINKS', 'DBA_ROLE_PRIVS', 'DBA_SYS_PRIVS', 'DBA_TAB_PRIVS', 'DBA_ROLES',
               'DBA_PROFILES', 'DBA_DATA_FILES', 'DBA_FREE_SPACE', 'DBA_TEMP_FILES', 'DBA_JOBS', 'DBA_SCHEDULER_JOBS',
               'DBA_DIRECTORIES', 'ALL_DIRECTORIES', 'DBA_ROLE_PRIVS', 'DBA_USERS_WITH_DEFPWD', 'USER_RECYCLEBIN', 'DBA_RECYCLEBIN']
USERS = ['ALL_USERS', 'DBA_USERS']
# Real views of dictionary kind to list in DICTIONARY (TABLE_NAME, COMMENTS) when lexdb serves them.
SPARSE_PARAMS = ['nls_language', 'nls_territory', 'nls_sort', 'nls_comp', 'nls_calendar', 'nls_date_format', 'nls_date_language',
    'nls_length_semantics', 'nls_numeric_characters', 'nls_time_format', 'nls_timestamp_format', 'nls_time_tz_format',
    'nls_timestamp_tz_format', 'nls_currency', 'nls_iso_currency', 'nls_dual_currency', 'nls_nchar_conv_excp',
    'db_name', 'db_domain', 'db_block_size', 'db_unique_name', 'compatible', 'instance_name', 'service_names', 'processes',
    'sessions', 'open_cursors', 'cursor_sharing', 'optimizer_mode', 'undo_management', 'undo_tablespace', 'max_string_size',
    'sga_target', 'sga_max_size', 'pga_aggregate_target', 'memory_target', 'cpu_count', 'control_files', 'db_files',
    'job_queue_processes', 'local_listener', 'remote_login_passwordfile', 'audit_trail', 'diagnostic_dest', 'open_links',
    'transactions', 'shared_pool_size', 'result_cache_mode', 'statistics_level', 'time_zone', 'enable_pluggable_database',
    'local_undo_enabled', 'resource_limit', 'db_create_file_dest', 'recyclebin', 'plsql_code_type', 'plsql_optimize_level',
    'parallel_max_servers', 'log_buffer', 'fast_start_mttr_target', 'sql_trace', 'timed_statistics', 'user_dump_dest',
    'background_dump_dest', 'core_dump_dest', 'spfile', 'cluster_database', 'db_recovery_file_dest', 'nls_nchar_characterset',
    'nls_characterset', 'case_sensitive_logon', 'max_pdbs', 'pdb_file_name_convert', 'uniform_log_timezone', 'deferred_segment_creation']
# the GV$ and the like: no
DEMO = """
create table dept (deptno number(4) primary key, dname varchar2(30) not null, loc varchar2(20))
create table emp (empno number(6) not null, ename varchar2(50) not null, job varchar2(20) default 'CLERK', sal number(8,2), comm number, hired date, mgr number(6), deptno number(4), constraint emp_pk primary key (empno), constraint emp_dept_fk foreign key (deptno) references dept (deptno) on delete cascade, constraint emp_sal_ck check (sal > 0), constraint emp_ename_uq unique (ename))
create index emp_job_ix on emp (job, sal desc)
create unique index emp_hired_ix on emp (hired)
create sequence emp_seq start with 100 increment by 5 cache 20
create view emp_v as select empno, ename from emp where sal > 100
create table idt (id number generated always as identity, v varchar2(10))
create table tys (a varchar2(10), b char(4), c nvarchar2(5), d nchar(3), e number, f number(10), g number(10,2), h float, i integer, j binary_float, k binary_double, l date, m timestamp(6), n timestamp(3) with time zone, o timestamp with local time zone, p interval day(2) to second(6), q interval year(2) to month, r raw(16), s clob, t blob, u nclob, v rowid, w long, x boolean)
comment on table emp is 'Employees'
comment on column emp.ename is 'Employee name'
"""
DEMO_DROP = ['drop table tys purge', 'drop table idt purge', 'drop view emp_v', 'drop sequence emp_seq', 'drop table emp purge', 'drop table dept purge']


def lxl_str(s):
    out = []
    for ch in s:
        if ch == '\\': out.append('\\\\')
        elif ch == '"': out.append('\\"')
        elif ch == '\t': out.append('\\x09')
        elif ch == '\n': out.append('\\n')
        elif ch == '\r': out.append('\\r')
        elif ch == '\x1e': out.append('\\x1e')
        elif ch == '\x1f': out.append('\\x1f')
        elif ch == '\x00': out.append('\\x00')
        elif ord(ch) < 32: out.append('\\x%02x' % ord(ch))
        else: out.append(ch)
    return ''.join(out)


def val(v):
    if v is None: return '\x00'
    if isinstance(v, datetime.datetime): return v.strftime('%Y-%m-%d %H:%M:%S')
    if isinstance(v, bytes): return v.hex().upper()
    if isinstance(v, float) and v == int(v): return str(int(v))
    if hasattr(v, 'read'): v = v.read()
    return (str(v).replace('Oracle AI Database 26ai', 'Oracle Database 23ai').replace('Release 23.26.3.0.0', 'Release 23.0.0.0.0')
            .replace('23.26.3.0.0', '23.4.0.24.05'))


def cols_of(cur, real):
    cur.execute("select column_name, data_type, data_length, data_precision, data_scale, nullable from dba_tab_columns "
                "where owner = 'SYS' and table_name = :1 order by column_id", [real])
    out = []
    for n, t, l, p, s, nl in cur.fetchall():
        out.append(':'.join([n, t, str(l or 0), str(p if p is not None else -1), str(s if s is not None else -1), '1' if nl == 'Y' else '0']))
    return out


def rows_of(cur, sql):
    cur.execute(sql)
    out = []
    for r in cur.fetchall():
        out.append('\x1f'.join(val(v) for v in r))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--system-dsn', required=True, help='system/PASSWORD@host:port/FREEPDB1 (needs DBA_ views)')
    ap.add_argument('--app-dsn', required=True, help='app/PASSWORD@host:port/FREEPDB1 (the demo schema)')
    ap.add_argument('--out', default=os.path.join(ROOT, 'cmd', 'lexdb_oradata.lxl'))
    a = ap.parse_args()

    def conn(d):
        u, rest = d.split('/', 1)
        p, dsn = rest.rsplit('@', 1)
        return oracledb.connect(user=u, password=p, dsn=dsn)
    sysc = conn(a.system_dsn)
    app = conn(a.app_dsn)
    sc = sysc.cursor()
    ac = app.cursor()
    for s in DEMO_DROP:
        try: ac.execute(s)
        except Exception: pass
    for s in [x.strip() for x in DEMO.strip().split('\n') if x.strip()]:
        ac.execute(s)

    views = {}        # lexdb's name -> (real name, columns)
    def add(name, real=None):
        real = real or name
        c = cols_of(sc, real)
        if not c:
            print('no such view', name, file=sys.stderr)
            return False
        views[name] = c
        return True

    names = []
    for base in BUILT + EMPTY:
        for pre in ('ALL_', 'USER_', 'DBA_'):
            n = pre + base
            if n in ('ALL_TAB_MODIFICATIONS', 'USER_CATALOG_X'): continue
            if add(n): names.append(n)
    for n in USERS: add(n)
    for n in list(FULL) + list(TEMPLATE) + EMPTY_PLAIN:
        if n not in views: add(n)
    add('DICTIONARY')
    add('DICT_COLUMNS')
    add('V_$PARAMETER')
    add('V_$SESSION')
    rows = []    # (name, kind, [rows])

    for n, where in FULL.items():
        if n in views: rows.append((n, 'full', rows_of(ac if n in APP_FULL else sc, f"select * from {n.replace('V_$', 'V$')} {where}" + ('' if n == 'V_$VERSION' else ' order by 1'))))
    for n, where in TEMPLATE.items():
        if n == 'USER_USERS':
            rows.append((n, 'template', rows_of(ac, 'select * from user_users')))
        elif n == 'V_$INSTANCE':
            rows.append((n, 'template', rows_of(sc, 'select * from v$instance')))
        else:
            rows.append((n, 'template', rows_of(sc, 'select * from v$database')))
    # the session's own row
    sc.execute("select * from v$session where sid = sys_context('USERENV', 'SID')")
    rows.append(('V_$SESSION', 'template', ['\x1f'.join(val(v) for v in r) for r in sc.fetchall()]))
    rows.append(('V_$PARAMETER', 'full', rows_of(sc, "select * from v$parameter where name in (%s) order by name" %
                                                  ','.join("'%s'" % p for p in SPARSE_PARAMS))))
    # users: the fixed ones (SYS, SYSTEM) and a template (APP)
    rows.append(('ALL_USERS', 'full', rows_of(sc, "select * from all_users where username in ('SYS', 'SYSTEM', 'PDBADMIN', 'AUDSYS', 'XDB', 'DBSNMP', 'OUTLN') order by user_id")))
    rows.append(('ALL_USERS', 'template', rows_of(sc, "select * from all_users where username = 'APP'")))
    rows.append(('DBA_USERS', 'full', rows_of(sc, "select * from dba_users where username in ('SYS', 'SYSTEM') order by user_id")))
    rows.append(('DBA_USERS', 'template', rows_of(sc, "select * from dba_users where username = 'APP'")))

    # templates from the demo schema
    own = {'TABLES': 'owner', 'TAB_COLUMNS': 'owner', 'TAB_COLS': 'owner', 'INDEXES': 'owner', 'IND_COLUMNS': 'index_owner',
           'CONSTRAINTS': 'owner', 'CONS_COLUMNS': 'owner', 'OBJECTS': 'owner', 'SEQUENCES': 'sequence_owner', 'VIEWS': 'owner',
           'TAB_COMMENTS': 'owner', 'COL_COMMENTS': 'owner', 'TAB_IDENTITY_COLS': 'owner', 'CATALOG': 'owner'}
    for base, oc in own.items():
        n = 'ALL_' + base
        if n not in views: continue
        w = f"where {oc} = 'APP'"
        if base == 'OBJECTS': w += " and object_name in ('DEPT','EMP','EMP_V','EMP_SEQ','EMP_PK','IDT','EMP_JOB_IX')"
        order = ''
        rs = rows_of(ac, f'select * from {n} {w}')
        # keep one row per kind: the discriminating column's distinct values (or the first)
        disc = {'TAB_COLUMNS': 'DATA_TYPE', 'TAB_COLS': 'DATA_TYPE', 'INDEXES': 'UNIQUENESS', 'CONSTRAINTS': 'CONSTRAINT_TYPE',
                'OBJECTS': 'OBJECT_TYPE', 'CATALOG': 'TABLE_TYPE', 'TAB_COMMENTS': 'TABLE_TYPE'}.get(base)
        names_ = [c.split(':')[0] for c in views[n]]
        keep, seen = [], set()
        for r in rs:
            f = r.split('\x1f')
            k = f[names_.index(disc)] if disc else ''
            if k in seen: continue
            seen.add(k)
            keep.append(r)
        rows.append((n, 'template', keep))
    # DICTIONARY and DICT_COLUMNS: the dictionary views lexdb serves
    served = sorted(views.keys())
    rows.append(('DICTIONARY', 'full', rows_of(sc, "select table_name, comments from dictionary where table_name in (%s) order by table_name" %
                                             ','.join("'%s'" % n.replace('V_$', 'V$') for n in served))))
    # public synonyms of the views
    syn = []
    sc.execute("select synonym_name, table_name from dba_synonyms where owner = 'PUBLIC' and table_owner = 'SYS'")
    for s, t in sc.fetchall():
        if t in views: syn.append(s + '\t' + t)
    syn.sort()
    sc.execute("select table_name, comments from dictionary where table_name = 'DICTIONARY'")
    for s in DEMO_DROP:
        try: ac.execute(s)
        except Exception as e: print('drop', e, file=sys.stderr)

    with open(a.out, 'w', encoding='utf-8') as f:
        f.write('// GENERATED by tools/gen_oracle_catalog.py from Oracle Database Free: do not edit.\n')
        f.write('// Oracle\'s catalog views as lexdb_oracat gives them (design/lexdb-oracle.md, O4).\n\n')
        f.write('// Each view: its (real) name, then its columns as name:type:length:precision:scale:nullable\n')
        f.write('// (precision and scale -1 for none), tab-separated. V$X is V_$X here.\n')
        f.write('pub const VIEWS: []str = [\n')
        for n in sorted(views):
            f.write('    "' + lxl_str(n + '\t' + '\t'.join(views[n])) + '",\n')
        f.write(']\n\n')
        f.write('// Rows Oracle has: a view\'s name, "full" (every row lexdb gives) or "template" (a row of\n')
        f.write('// each kind of object, lexdb_exec fills in), then its rows (\\x1e between them; \\x1f between\n')
        f.write('// values; NULL \\x00), tab-separated.\n')
        f.write('pub const ROWS: []str = [\n')
        for n, kind, rs in rows:
            f.write('    "' + lxl_str(n + '\t' + kind + '\t' + '\x1e'.join(rs)) + '",\n')
        f.write(']\n\n')
        f.write('// PUBLIC synonyms: its name, the view\'s, tab-separated.\n')
        f.write('pub const SYNONYMS: []str = [\n')
        for s in syn:
            f.write('    "' + lxl_str(s) + '",\n')
        f.write(']\n')
    print('wrote', a.out, len(views), 'views')


if __name__ == '__main__':
    main()
