#!/usr/bin/env python3
"""Generates lexell/cmd/lexdb_sysdata.lxl, the shapes of SQL Server's
catalog views (sys.*) and the rows lexdb takes from SQL Server as they are,
from a running SQL Server: the oracle container (tools/mssql_container.sh).
design/lexdb-tds.md, section 13.

    python3 lexell/tools/gen_sqlserver_syscat.py

For each view in VIEWS: its object_id and its columns as sys.all_columns
gives them (name, type, max_length, precision, scale, nullable,
collation), in order. For the views in FULL, every row the oracle has
(sys.types, the system databases, the fixed principals, ...). For those in
TEMPLATE, one row of an object of the demo schema (DEMO, made in a database
of its own, then dropped): lexdb_exec fills a view's row from it, setting
the columns that describe lexdb's own object, so that the columns lexdb has
nothing to say about hold what SQL Server says for such an object.

Rows are read as JSON (FOR JSON PATH, INCLUDE_NULL_VALUES): values are
written as text, NULL as \\x00; bit as 1 or 0, binary as hex, datetime as
SQL Server writes it (2026-11-13 11:14:22.123).
"""
import base64, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, 'cmd', 'lexdb_sysdata.lxl')
DB = 'lexdb_syscat_gen'

# The views lexdb has: those VS Code's SQL Server extension (SQL Tools
# Service, SMO) reads (tests/lexdb/vscode_queries.txt), and a few more of
# the same kind.
VIEWS = '''all_columns all_objects all_parameters all_views assemblies assembly_types asymmetric_keys certificates
change_tracking_databases check_constraints column_encryption_keys columns computed_columns configurations credentials
data_spaces database_files database_filestream_options database_permissions database_principals database_recovery_status
database_scoped_configurations databases default_constraints dm_exec_sessions dm_hadr_cluster dm_os_host_info
extended_properties filetable_system_defined_objects foreign_key_columns foreign_keys fulltext_indexes fulltext_languages
hash_indexes identity_columns index_columns index_resumable_operations indexes key_constraints objects schemas
selective_xml_index_paths sensitivity_classifications server_principals server_sql_modules server_triggers
spatial_index_tessellations spatial_indexes sql_modules stats synonyms syslanguages system_sql_modules table_types tables
triggers types xml_indexes xml_schema_collections
views procedures sequences parameters system_objects system_views system_columns sql_expression_dependencies'''.split()

# Views whose rows are SQL Server's own, every one (WHERE, ORDER BY).
FULL = {
    'types': 'order by user_type_id',
    'databases': "where name in ('master', 'tempdb', 'model', 'msdb') order by database_id",
    'database_principals': 'where principal_id < 5 or principal_id >= 16384 order by principal_id',
    'server_principals': "where type = 'R' order by principal_id",
    'schemas': 'order by schema_id',
    'configurations': 'order by configuration_id',
    'syslanguages': 'order by langid',
    'fulltext_languages': 'order by lcid',
    'database_scoped_configurations': 'order by configuration_id',
    'data_spaces': 'order by data_space_id',
    'database_files': 'order by file_id',
    'dm_os_host_info': '',
    'database_recovery_status': "where database_id <= 4 order by database_id",
    'database_filestream_options': "where database_id <= 4 order by database_id",
    'database_permissions': "where class = 0 order by grantee_principal_id, type",
}

# Views whose rows lexdb makes, from one of the oracle's (WHERE).
TEMPLATE = {
    'objects': "where object_id = object_id('dbo.customers')",
    'all_objects': "where object_id = object_id('dbo.customers')",
    'system_objects': "where object_id = object_id('sys.tables')",
    'tables': "where object_id = object_id('dbo.customers')",
    'views': "where object_id = object_id('dbo.big_orders')",
    'all_views': "where object_id = object_id('dbo.big_orders')",
    'system_views': "where object_id = object_id('sys.tables')",
    'columns': "where object_id = object_id('dbo.customers') and column_id = 1",
    'all_columns': "where object_id = object_id('dbo.customers') and column_id = 1",
    'system_columns': "where object_id = object_id('sys.tables') and column_id = 1",
    'indexes': "where object_id = object_id('dbo.customers') and index_id = 1",
    'index_columns': "where object_id = object_id('dbo.customers') and index_id = 1",
    'key_constraints': "where parent_object_id = object_id('dbo.customers') and type = 'PK'",
    'foreign_keys': "where parent_object_id = object_id('dbo.orders')",
    'foreign_key_columns': "where parent_object_id = object_id('dbo.orders')",
    'check_constraints': "where parent_object_id = object_id('dbo.orders')",
    'default_constraints': "where parent_object_id = object_id('dbo.customers')",
    'identity_columns': "where object_id = object_id('dbo.customers')",
    'stats': "where object_id = object_id('dbo.customers') and stats_id = 1",
    'sql_modules': "where object_id = object_id('dbo.big_orders')",
    'sequences': "where object_id = object_id('dbo.seq1')",
    'dm_exec_sessions': 'where session_id = @@spid',
    'databases': "where name = db_name()",
    'server_principals': "where name = 'lexdb_syscat_login'",
    'database_principals': "where name = 'lexdb_syscat_user'",
    'database_recovery_status': "where database_id = db_id()",
    'database_filestream_options': "where database_id = db_id()",
}

# SERVERPROPERTY's, DATABASEPROPERTYEX's (of a user database) and
# FULLTEXTSERVICEPROPERTY's values lexdb gives as SQL Server's (lexdb_tsqlfn).
SERVER_PROPS = '''BuildClrVersion Collation CollationID ComparisonStyle ComputerNamePhysicalNetBIOS Edition EditionID EngineEdition
ErrorLogFileName HadrManagerStatus InstanceDefaultBackupPath InstanceDefaultDataPath InstanceDefaultLogPath InstanceName IsAdvancedAnalyticsInstalled
IsBigDataCluster IsClustered IsExternalAuthenticationOnly IsFullTextInstalled IsHadrEnabled IsIntegratedSecurityOnly IsLocalDB
IsPolyBaseInstalled IsSingleUser IsTempDbMetadataMemoryOptimized IsXTPSupported LCID LicenseType MachineName NumLicenses ProcessID
ProductBuild ProductBuildType ProductLevel ProductMajorVersion ProductMinorVersion ProductUpdateLevel ProductUpdateReference
ProductVersion ResourceLastUpdateDateTime ResourceVersion ServerName SqlCharSet SqlCharSetName SqlSortOrder SqlSortOrderName
FilestreamShareName FilestreamConfiguredLevel FilestreamEffectiveLevel'''.split()
DATABASE_PROPS = '''Collation ComparisonStyle Edition IsAnsiNullDefault IsAnsiNullsEnabled IsAnsiPaddingEnabled IsAnsiWarningsEnabled
IsArithmeticAbortEnabled IsAutoClose IsAutoCreateStatistics IsAutoCreateStatisticsIncremental IsAutoShrink IsAutoUpdateStatistics
IsClone IsCloseCursorsOnCommitEnabled IsFulltextEnabled IsInStandBy IsLocalCursorsDefault IsMemoryOptimizedElevateToSnapshotEnabled
IsMergePublished IsNullConcat IsNumericRoundAbortEnabled IsParameterizationForced IsQuotedIdentifiersEnabled IsPublished
IsRecursiveTriggersEnabled IsSubscribed IsSyncWithBackup IsTornPageDetectionEnabled IsVerifiedClone IsXTPSupported
LastGoodCheckDbTime LCID MaxSizeInBytes Recovery ServiceObjective ServiceObjectiveId SQLSortOrder Status Updateability
UserAccess Version'''.split()
GLOBALS = ['@@MICROSOFTVERSION', '@@MAX_PRECISION', '@@SERVICENAME', '@@LANGID', '@@DATEFIRST', '@@TEXTSIZE',
           '@@LOCK_TIMEOUT', '@@MAX_CONNECTIONS']

DEMO = f'''
IF DB_ID('{DB}') IS NOT NULL BEGIN ALTER DATABASE {DB} SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE {DB} END
CREATE DATABASE {DB}
GO
USE {DB}
GO
CREATE TABLE dbo.customers (id int IDENTITY(1,1) PRIMARY KEY, name nvarchar(100) NOT NULL, email varchar(200) NULL UNIQUE, created_at datetime2 NOT NULL DEFAULT SYSUTCDATETIME());
CREATE TABLE dbo.orders (id bigint PRIMARY KEY, customer_id int NOT NULL REFERENCES dbo.customers(id), amount decimal(10,2) NOT NULL CHECK (amount >= 0), placed date NOT NULL, note nvarchar(max) NULL, ref uniqueidentifier NULL, paid bit NOT NULL DEFAULT 0);
CREATE INDEX ix_orders_placed ON dbo.orders(placed) INCLUDE (amount);
CREATE SEQUENCE dbo.seq1;
GO
CREATE VIEW dbo.big_orders AS SELECT id, customer_id, amount FROM dbo.orders WHERE amount > 100;
GO
IF SUSER_ID('lexdb_syscat_login') IS NULL CREATE LOGIN lexdb_syscat_login WITH PASSWORD = 'Lexdb-syscat-2026', CHECK_POLICY = OFF;
CREATE USER lexdb_syscat_user FOR LOGIN lexdb_syscat_login;
GO
'''

DROP = f'''
USE master
GO
ALTER DATABASE {DB} SET SINGLE_USER WITH ROLLBACK IMMEDIATE; DROP DATABASE {DB}
DROP LOGIN lexdb_syscat_login
GO
'''


def sqlcmd(text, db='master'):
    sa = open(os.path.expanduser('~/.obo-mssql-sa')).read().strip()
    env = dict(os.environ, SQLCMDPASSWORD=sa)
    if not env.get('XDG_RUNTIME_DIR') or not os.access(env['XDG_RUNTIME_DIR'], os.W_OK):
        env['XDG_RUNTIME_DIR'] = '/tmp/lxl-podman-%d' % os.getuid()
    p = subprocess.run(['podman', 'exec', '-i', '-e', 'SQLCMDPASSWORD', 'lxl-mssql', '/opt/mssql-tools18/bin/sqlcmd',
                        '-S', 'localhost', '-U', 'sa', '-C', '-d', db, '-y', '0', '-f', '65001', '-I', '-i', '/dev/stdin'],
                       input=text.encode('utf-8'), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
    out = p.stdout.decode('utf-8')
    if p.returncode != 0 or re.search(r'^Msg \d+', out, re.M):
        sys.exit('the oracle refused:\n' + text[:500] + '\n' + out[:2000])
    return out


def query_json(q):
    out = sqlcmd("SET NOCOUNT ON; DECLARE @j nvarchar(max) = (" + q + " FOR JSON PATH, INCLUDE_NULL_VALUES); "
                 "SELECT N'<<<' + ISNULL(@j, N'[]') + N'>>>'", DB)
    m = re.search(r'<<<(.*)>>>', out, re.S)
    return json.loads(m.group(1))


def lxl_str(s):
    out = []
    for ch in s:
        o = ord(ch)
        if ch == '\\': out.append('\\\\')
        elif ch == '"': out.append('\\"')
        elif o < 0x20: out.append('\\x%02x' % o)
        else: out.append(ch)
    return ''.join(out)


def value_text(v, typ):
    if v is None: return '\x00'
    if isinstance(v, bool): return '1' if v else '0'
    if typ in ('varbinary', 'binary', 'timestamp', 'image'):
        return '0x' + base64.b64decode(v).hex().upper()
    if typ in ('datetime', 'smalldatetime', 'datetime2') and isinstance(v, str):
        return v.replace('T', ' ')
    return str(v)


def main():
    sqlcmd(DEMO)
    names = "', '".join(VIEWS)
    cols = query_json("SELECT o.name AS v, o.object_id AS id, c.name AS c, type_name(c.user_type_id) AS t, c.max_length AS l, "
                      "c.precision AS p, c.scale AS s, c.is_nullable AS n, c.collation_name AS k "
                      "FROM sys.all_objects o JOIN sys.all_columns c ON c.object_id = o.object_id "
                      f"WHERE o.schema_id = 4 AND o.name IN ('{names}') ORDER BY o.name, c.column_id")
    views = {}
    for c in cols:
        v = views.setdefault(c['v'], {'id': c['id'], 'cols': []})
        v['cols'].append(c)
    missing = [v for v in VIEWS if v not in views]
    if missing:
        sys.exit('not in the oracle: ' + ', '.join(missing))
    lines = []
    for name in sorted(views):
        v = views[name]
        spec = [name, str(v['id'])]
        for c in v['cols']:
            spec.append(':'.join([c['c'], c['t'], str(c['l']), str(c['p']), str(c['s']), '1' if c['n'] else '0', c['k'] or '']))
        lines.append('\t'.join(spec))
    rows = []
    for name, kind, where in sorted([(k, 'full', w) for k, w in FULL.items()] + [(k, 'template', w) for k, w in TEMPLATE.items()]):
        types = {c['c']: c['t'] for c in views[name]['cols']}
        got = query_json(f"SELECT * FROM sys.{name} {where}")
        if kind == 'template' and len(got) != 1:
            sys.exit(f'{name}: {len(got)} template rows')
        rs = []
        for r in got:
            rs.append('\x1f'.join(value_text(r.get(c['c']), c['t']) for c in views[name]['cols']))
        rows.append((name, kind, '\x1e'.join(rs)))
    props = []
    def prop(kind, name, expr):
        r = query_json(f"SELECT CAST(SQL_VARIANT_PROPERTY({expr}, 'BaseType') AS nvarchar(30)) AS t, "
                       f"CAST({expr} AS nvarchar(4000)) AS v, CONVERT(nvarchar(30), {expr}, 121) AS d")
        t, v = r[0]['t'], r[0]['v']
        if t in ('datetime', 'datetime2', 'smalldatetime'): v = r[0]['d']
        props.append('\t'.join([kind, name, t or '', '\x00' if v is None else v]))
    for n in SERVER_PROPS: prop('server', n, f"SERVERPROPERTY('{n}')")
    for n in DATABASE_PROPS: prop('database', n, f"DATABASEPROPERTYEX(DB_NAME(), '{n}')")
    prop('fulltext', 'IsFullTextInstalled', "FULLTEXTSERVICEPROPERTY('IsFullTextInstalled')")
    for n in GLOBALS: prop('global', n.lower(), f"CAST({n} AS sql_variant)")
    sqlcmd(DROP)
    with open(OUT, 'w', encoding='utf-8') as f:
        f.write('// GENERATED by tools/gen_sqlserver_syscat.py from SQL Server 2022 (16.0.4315): do not edit.\n')
        f.write('// SQL Server\'s catalog views as lexdb_syscat gives them (design/lexdb-tds.md, section 13).\n\n')
        f.write('// Each view: its name, object_id, then its columns as\n')
        f.write('// name:type:max_length:precision:scale:nullable:collation, tab-separated.\n')
        f.write('pub const VIEWS: []str = [\n')
        for l in lines:
            f.write('    "' + lxl_str(l) + '",\n')
        f.write(']\n\n')
        f.write('// Rows SQL Server has: a view\'s name, "full" (every row) or "template" (one\n')
        f.write('// row lexdb_exec fills in), then its rows (\\x1e between them; \\x1f between\n')
        f.write('// values; NULL \\x00), tab-separated.\n')
        f.write('pub const ROWS: []str = [\n')
        for name, kind, rs in rows:
            f.write('    "' + lxl_str(name + '\t' + kind + '\t' + rs) + '",\n')
        f.write(']\n\n')
        f.write('// SERVERPROPERTY ("server"), DATABASEPROPERTYEX ("database", of a user\n')
        f.write('// database), FULLTEXTSERVICEPROPERTY ("fulltext") and @@ values ("global"):\n')
        f.write('// kind, name, the value\'s type (SQL_VARIANT_PROPERTY\'s BaseType), the value\n')
        f.write('// (NULL \\x00), tab-separated.\n')
        f.write('pub const PROPS: []str = [\n')
        for p in props:
            f.write('    "' + lxl_str(p) + '",\n')
        f.write(']\n')
    print('%s: %d views, %d columns, %d row sets' % (OUT, len(views), len(cols), len(rows)))


if __name__ == '__main__':
    main()
