# Known issues

Bugs and gaps found while writing and checking these pages (lexdb built from main at 4fba817b, 2026-11-23). They
are not fixed here: the pages describe what lexdb does. Each "Differences" section of the reference lists the
smaller differences of its statement.

## All doors

- **Replicas: temporary objects not built yet.** The pages describe a replica's T-SQL `#temp` tables and table
  variables, and Oracle DML on global temporary tables, as working, per design/lexdb.md 9.137 phase 5. Until that
  phase lands, a replica refuses them as it refuses any write (3906, ORA-16000). The replica examples for them in
  [replicas](replicas.md) show no output for that reason.

## PostgreSQL door

- **pgjdbc fails with its default settings.** lexdb takes binary parameters only for `int2`, `int4`, `int8`,
  `bool`, `float4`, `float8` and text types, and sends no binary results. pgjdbc 42.7 sends `BigDecimal`, `UUID` and
  `byte[]` parameters in binary ("a binary parameter of type 1700 is not supported"), and after a prepared statement
  has run five times (`prepareThreshold`) it asks for binary results, so the sixth run fails ("results in binary are
  not supported"). `binaryTransfer=false` in the URL avoids both, except for `setBytes`, which is always binary.
  ([connect/postgresql.md](connect/postgresql.md#java-pgjdbc))
- **Cancel requests are ignored.** psql's Ctrl-C, JDBC's `Statement.cancel()` and libpq's `PQcancel` do not stop a
  running statement. `statement_timeout` does.
- **`inet_server_port()`** and the other `inet_*` functions do not exist (42883).

## SQL Server door

- **Error text.** Many errors carry SQL Server's number and severity with lexdb's (PostgreSQL's) text, for example
  2714 `relation "t1" already exists` where SQL Server says `There is already an object named 't1' in the database.`,
  and 2627 `duplicate key value violates unique constraint "t1_pkey"`.
- **`SET FMTONLY ON` stays on after mssql-jdbc's `SQLServerBulkCopy`.** After `writeToServer`, every later query on
  that connection returns its columns and no rows, until the program runs `SET FMTONLY OFF` (checked with mssql-jdbc
  13.6.2; the rows are loaded). The same happens after an `executeBatch` sent as bulk copy
  (`useBulkCopyForBatchInsert=true`). The driver's metadata batch (`SET FMTONLY ON ... SET FMTONLY OFF`) leaves the
  option on in lexdb. bcp and SqlBulkCopy were not affected when checked during development (design/lexdb-tds.md
  section 14). ([bulk loading](bulk-load.md#from-java-sqlserverbulkcopy))
- **Error line numbers** are always 1 (`Msg 2627, Level 14, State 1, Line 1`), whatever line of the batch failed.

## Oracle door

- **A bare name finds a table of the PostgreSQL door's `public` schema, and blocks `CREATE TABLE` of that name.**
  With a table `city` made in the PostgreSQL door, `CREATE TABLE city (...)` in the Oracle door (user `SA`) fails with
  ORA-00955 "name is already used by an existing object", and `SELECT * FROM city` reads `public.city`. In Oracle a
  public synonym does not stop a user from making an object of the same name in its own schema.
- **ojdbc does not follow the read-only redirect.** A JDBC thin connection to the master with the read-only service
  (`lexdb_ro`) fails in the driver with `ORA-18951: NL exception was generated: TNS-04605: Invalid syntax error:
  Unexpected char or LITERAL " " before or at ( DESCRIPTION ...`: ojdbc 23.26 cannot parse the REDIRECT packet's data.
  python-oracledb and Lexell's `oracle` module follow it (design/lexdb.md 9.137). Connecting to a replica's own
  listener works with ojdbc.
