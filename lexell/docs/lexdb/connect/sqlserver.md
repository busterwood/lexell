# Connecting through the SQL Server door

The SQL Server door speaks TDS 7.4, the protocol of SQL Server 2012 and later, and T-SQL. It is opened with
`--tds HOST:PORT`. At login lexdb reports itself as SQL Server 2022 (16.0.4315), because drivers choose features by
the version; `@@VERSION` says it is lexdb. For T-SQL lexdb follows SQL Server 2022 and 2025.

## Listening

```sh
lexdb ./data --tds 127.0.0.1:1433
lexdb ./data --tds 127.0.0.1:1433 --tds 10.0.0.5:1433     # more than one address
```

TCP only: there is no named-pipe or shared-memory transport, and no SQL Browser (give the port, not an instance
name).

## The protocol

- **PRELOGIN and LOGIN7**, with the encryption agreed in PRELOGIN (below).
- **SQL batches**: T-SQL, with variables, control flow, several result sets and messages per batch. `GO` is a client
  command (sqlcmd, SSMS); lexdb never sees it.
- **RPC**: `sp_executesql` with parameters, `sp_prepare`, `sp_execute`, `sp_prepexec`, `sp_unprepare`, by id or by
  name, OUTPUT parameters and return status; procedure calls by name; table-valued parameters.
- **Transaction Manager requests**: begin, commit, rollback and save, as drivers send for `setAutoCommit(false)` and
  `BeginTransaction`.
- **RESETCONNECTION** (connection pools), **ATTENTION** (cancel), and **bulk load** (`INSERT BULK` and the
  BULK_LOAD message: bcp, SqlBulkCopy): see [bulk loading](../bulk-load.md#sql-server-bulk-copy).
- **Result types.** A column's TDS type comes from its lexdb type: `int`, `bigint`, `smallint`, `bit`, `float`,
  `real`, `decimal(38, s)`, `nvarchar(4000)` or `nvarchar(max)`, `varbinary`, `uniqueidentifier`, `date`, `time(6)`,
  `datetime2(6)`, `datetimeoffset(6)`. A table's declared types are given where drivers ask for them (`SET FMTONLY
  ON`, `sp_describe_first_result_set`).
- **Errors** are ERROR tokens with SQL Server's error number and severity for the same failure (208 for a missing
  table, 2627 for a duplicate key, 547 for a constraint), else 50000, with the line of the batch it happened on.
  Many messages are SQL Server's text; some are still lexdb's own (see [known issues](../KNOWN-ISSUES.md)).

## Logins

- **SQL authentication only.** Integrated (Windows, Kerberos) and Microsoft Entra logins are refused.
- Under `--auth trust` (the default) any user name and any password log in. Under `--auth scram-sha-256` the password
  is checked against the role's stored password. The door has no `CREATE LOGIN`: set the password in the
  PostgreSQL door (`CREATE ROLE name LOGIN PASSWORD '...'`) or the Oracle door (`CREATE USER name IDENTIFIED BY ...`).
- **Database.** `lexdb` or `master`, or none: they are the one database. Another name is refused, as SQL Server
  refuses a database that does not exist.
- The default schema is `dbo`, which is the PostgreSQL door's `public`. Tables that an Oracle login made are in the
  login's schema, with upper-case names: `sa.CITY` (see the [Oracle door's schemas](oracle.md#schemas)).

## Encryption

| Server | Client `Encrypt=` | Result |
|---|---|---|
| no `--tls-cert` | `no` / `false` / `optional` | No TLS. |
| no `--tls-cert` | `yes` / `mandatory` (the default of current drivers) | Refused, as SQL Server without a certificate refuses it. |
| `--tls-cert` | `no` | TLS for the login packet only, as SQL Server does. |
| `--tls-cert` | `yes` | TLS for the whole session (TLS 1.2, carried in PRELOGIN as SQL Server does). |
| `--tls-cert --require-tls` | any | TLS for the whole session. |
| any | `strict` (TDS 8.0) | Refused. |

With a self-signed certificate the client needs `TrustServerCertificate=yes` (or the certificate in its trust store).

## Connection strings

| Client | Example |
|---|---|
| ADO.NET, Microsoft.Data.SqlClient | `Server=127.0.0.1,1433;Database=lexdb;User Id=sa;Password=x;Encrypt=False` |
| ODBC, sqlcmd | `sqlcmd -S 127.0.0.1,1433 -U sa -P x -d lexdb -C` (`-C` trusts the certificate) |
| mssql-jdbc | `jdbc:sqlserver://127.0.0.1:1433;databaseName=lexdb;encrypt=false;user=sa;password=x` |
| Lexell `sqlserver` | `Server=127.0.0.1,1433;Database=lexdb;UID=sa;PWD=x;Encrypt=no` |

`ApplicationIntent=ReadOnly` routes the session to a replica: see [replicas](../replicas.md#sql-server).

## Clients known to work

Checked for this documentation (2026-11-23), against a lexdb built from the same tree:

- **mssql-jdbc 13.6.2** (Microsoft's JDBC driver).
- **Lexell's `sqlserver` module** (lib/sqlserver), including its bulk copy.

Checked while lexdb was developed (design/lexdb-tds.md): sqlcmd and bcp of mssql-tools18 (ODBC Driver 18),
Microsoft.Data.SqlClient 6 (.NET), and VS Code's SQL Server extension (connect, browse, completion). sqlcmd and bcp
are not installed on the machine these pages were checked on, so their command lines here are not run by the
checker.

## A first session

<!-- example: tsql -->
```sql
SELECT DB_NAME() AS db, SCHEMA_NAME() AS default_schema, SUSER_SNAME() AS login;
SELECT SERVERPROPERTY('ProductVersion') AS version, SERVERPROPERTY('Edition') AS edition;
```

```text
db    default_schema login
----- -------------- -----
lexdb dbo            sa

(1 row affected)

version     edition
----------- --------------------------
16.0.4315.2 Developer Edition (64-bit)

(1 row affected)
```

## Java: mssql-jdbc

[TdsHello.java](examples/java/TdsHello.java) makes a table, inserts rows with a batch of prepared statements, reads
them back, and shows a transaction rolled back by a CHECK constraint.

```sh
javac -d out docs/lexdb/connect/examples/java/TdsHello.java
java -cp out:mssql-jdbc-13.6.2.jre11.jar TdsHello \
  'jdbc:sqlserver://127.0.0.1:1433;databaseName=lexdb;encrypt=false;user=sa;password=x'
```

```
server: Microsoft SQL Server 16.00.4315
batch: 3 rows
transaction: rolled back, error 547
1 apple 1.20
2 pear 0.85
3 plum 2.40
```

The driver is on Maven Central as `com.microsoft.sqlserver:mssql-jdbc`
(`https://repo1.maven.org/maven2/com/microsoft/sqlserver/mssql-jdbc/13.6.2.jre11/mssql-jdbc-13.6.2.jre11.jar`).
`encrypt=false` is needed unless lexdb has `--tls-cert`: the driver's default is `encrypt=true`. With a certificate,
use `encrypt=true;trustServerCertificate=true` (or a trust store).

## Lexell: lib/sqlserver

[tds_hello.lxl](examples/lexell/tds_hello.lxl) does the same with Lexell's own client, and adds rows by bulk copy
(`bulkInsert`, the protocol bcp uses):

```sh
lexell/compiler/out/lxlc lexell/docs/lexdb/connect/examples/lexell/tds_hello.lxl -o tds_hello
./tds_hello "Server=127.0.0.1,1433;Database=lexdb;UID=sa;PWD=x;Encrypt=no"
```

```
server: lexdb (SQL Server protocol, TDS 7.4; reports itself as Microsoft SQL Server 16.0.4315)
bulk copy: 2 rows
transaction: rolled back, error 547
1 apple 1.20
2 pear 0.85
3 plum 2.40
4 quince 3.00
```

## See also

- [The T-SQL reference](../sql/tsql/README.md)
- [Bulk copy](../bulk-load.md#sql-server-bulk-copy)
- [Read replicas](../replicas.md#sql-server)
