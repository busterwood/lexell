# Bulk loading

Each door has its product's way of loading many rows at once:

| Door | Mechanism | Clients |
|---|---|---|
| PostgreSQL | `COPY ... FROM STDIN`, `COPY ... TO STDOUT` | psql `\copy`, pgjdbc `CopyManager`, psycopg `copy`, any driver with the COPY sub-protocol |
| SQL Server | bulk copy: `INSERT BULK` and the BULK_LOAD message | bcp, `SqlBulkCopy`, mssql-jdbc `SQLServerBulkCopy`, Lexell `bulkInsert` |
| Oracle | array DML: one statement with an array of binds | JDBC `executeBatch`, python-oracledb `executemany` |

All three insert through the same path as `INSERT`: defaults, identity columns and sequences, `NOT NULL`, `CHECK`,
unique keys, foreign keys and indexes are kept. A load is one statement, in the session's transaction when one is
open, else in its own; it goes in whole or not at all, except with `COPY ... WITH (batch_rows n)` and Oracle array
DML (below).

As a guide to speed: a million rows of twelve columns load in about 3 s by `COPY` or by bcp, about as fast as SQL
Server 2022 loads them by bcp on the same machine (design/lexdb-tds.md, section 14).

## PostgreSQL: COPY

### Syntax

```
COPY table_name [ ( column_name [, ...] ) ] FROM STDIN [ [ WITH ] ( option [, ...] ) ]
COPY { table_name [ ( column_name [, ...] ) ] | ( query ) } TO STDOUT [ [ WITH ] ( option [, ...] ) ]

option:
    FORMAT { text | csv }
    DELIMITER 'delimiter_character'
    NULL 'null_string'
    HEADER [ boolean ]
    QUOTE 'quote_character'
    ESCAPE 'escape_character'
    FORCE_QUOTE { ( column_name [, ...] ) | * }
    FORCE_NOT_NULL ( column_name [, ...] )
    FORCE_NULL ( column_name [, ...] )
    ENCODING 'UTF8'
    FREEZE [ boolean ]
    batch_rows n                        -- lexdb's own

-- the older form, also taken
COPY ... [ WITH ] [ BINARY ] [ DELIMITER [ AS ] 'c' ] [ NULL [ AS ] 's' ]
         [ CSV [ HEADER ] [ QUOTE [ AS ] 'c' ] [ ESCAPE [ AS ] 'c' ]
               [ FORCE QUOTE { column [, ...] | * } ] [ FORCE NOT NULL column [, ...] ] ]
```

- **text** (the default): fields separated by a tab, `\N` for NULL, backslash escapes (`\t`, `\n`, `\\`, `\ooo`,
  `\xhh`), a line `\.` ends the data.
- **csv**: fields separated by commas, quoted with `"` when needed, an unquoted empty field for NULL; `HEADER` skips
  (or writes) a first line of names.
- `FORCE_QUOTE` quotes a column's values on the way out; `FORCE_NOT_NULL` never reads a column as NULL;
  `FORCE_NULL` reads a quoted NULL string as NULL.
- **`batch_rows n`** (lexdb's own, `COPY FROM` only): commit every n rows. A very large load then needs memory for n
  rows' writes only. It is not all or nothing: a failure keeps the batches committed before it, and the error says
  how many rows were committed. Not allowed inside a transaction block (25001).
- Data is read as it arrives, so the input's size does not matter; `COPY TO` sends rows as they are made.

lexdb reads and writes the client's data only. `COPY ... FROM 'file'`, `TO 'file'` and `PROGRAM` are refused
(0A000): use psql's `\copy`, which reads and writes files on the client.

### Examples

<!-- example: postgresql -->
```sql
CREATE TABLE city (id int PRIMARY KEY, name text NOT NULL, pop bigint, founded date);
COPY city FROM STDIN;
1	Lisbon	545000	1179-01-01
2	Porto	232000	1123-01-01
3	Braga	\N	0016-01-01
\.
COPY city (id, name) FROM STDIN WITH (FORMAT csv, HEADER true);
id,name
4,"Coimbra, the old capital"
5,Faro
\.
COPY (SELECT id, name, pop FROM city ORDER BY id) TO STDOUT WITH (FORMAT csv, HEADER, FORCE_QUOTE (name));
```

```text
CREATE TABLE
COPY 3
COPY 2
id,name,pop
1,"Lisbon",545000
2,"Porto",232000
3,"Braga",
4,"Coimbra, the old capital",
5,"Faro",
```

A bad line stops the load, and the error names it. No row of that `COPY` is kept:

<!-- example: postgresql -->
```sql
COPY city FROM STDIN WITH (FORMAT csv);
6,Aveiro,80000,1203-01-01
7,Viseu,lots,1100-01-01
\.
SELECT count(*) FROM city;
```

```text
ERROR:  invalid input syntax for type bigint: "lots"
CONTEXT:  COPY city, line 2, column pop: "lots"
 count
-------
     5
(1 row)
```

With `batch_rows` the batches before the bad one stay:

<!-- example: postgresql -->
```sql
COPY city FROM STDIN WITH (FORMAT csv, batch_rows 2);
6,Aveiro,80000,1203-01-01
7,Viseu,99000,1100-01-01
8,Leiria,128000,1100-01-01
8,Leiria again,1,1100-01-01
\.
SELECT id, name FROM city WHERE id > 5 ORDER BY id;
```

```text
ERROR:  duplicate key value violates unique constraint "city_pkey"
DETAIL:  Key (id)=(8) already exists.
CONTEXT:  COPY city, line 4
 id |  name
----+--------
  6 | Aveiro
  7 | Viseu
(2 rows)
```

### From psql

`\copy` runs `COPY ... FROM STDIN` or `TO STDOUT` and reads or writes a file on the client:

```sh
psql -h 127.0.0.1 -p 5433 -U postgres lexdb -c "\copy city FROM 'cities.csv' WITH (FORMAT csv, HEADER)"
psql -h 127.0.0.1 -p 5433 -U postgres lexdb -c "\copy (SELECT * FROM city) TO 'out.csv' WITH (FORMAT csv)"
```

### From Java

pgjdbc's `CopyManager` sends `COPY FROM STDIN` and `TO STDOUT`. [PgCopy.java](connect/examples/java/PgCopy.java)
loads [cities.csv](connect/examples/java/cities.csv), then 10,000 rows made by the program, then copies a query out:

```sh
javac -cp postgresql-42.7.14.jar -d out docs/lexdb/connect/examples/java/PgCopy.java
java -cp out:postgresql-42.7.14.jar PgCopy 'jdbc:postgresql://127.0.0.1:5433/lexdb?binaryTransfer=false' postgres x cities.csv
```

```
copied in: 4 rows
copied in: 10000 rows
id,name,pop
1,Lisbon,545000
2,Porto,232000
3,Braga,193000
4,Coimbra,140000
copied out: 4 rows
```

Lexell's `postgres` module has no COPY.

### Differences from PostgreSQL

- No binary format (0A000), no server files or programs (0A000).
- No `WHERE`, `ON_ERROR`, `REJECT_LIMIT`, `LOG_VERBOSITY`, `DEFAULT` or `HEADER MATCH` (0A000).
- `COPY (query)` takes a `SELECT` (or `WITH ... SELECT`), not `INSERT/UPDATE/DELETE ... RETURNING`.
- Both `\n` and `\r\n` line ends are read in one input; PostgreSQL fixes the line end from the first line.
- `ENCODING` must be UTF8.
- `batch_rows` is lexdb's own.

## SQL Server: bulk copy

The SQL Server door takes the bulk copy protocol that bcp, .NET's `SqlBulkCopy` and Microsoft's JDBC driver use: an
`INSERT BULK` statement naming the table and its columns, then a BULK_LOAD message of rows in TDS's binary form.
Programs do not write `INSERT BULK` themselves; the client library sends it.

What a load does:

- Each value arrives in the type the client declared and is converted to the column's type as an `INSERT` would.
- A column left out gets its default, or the next identity value. An identity column that is named keeps the values
  given (as `bcp -E` and `SqlBulkCopyOptions.KeepIdentity` ask), and the identity goes on after the largest.
- Without `KEEP_NULLS`, a NULL for a column with a default takes the default.
- `CHECK` and `FOREIGN KEY` constraints are always checked. SQL Server checks them only with `CHECK_CONSTRAINTS`.
- `TABLOCK`, `ORDER`, `ROWS_PER_BATCH`, `KILOBYTES_PER_BATCH` and `FIRE_TRIGGERS` are read and ignored.
- An error (2627 duplicate key, 515 NULL, 547 constraint, 2628 too long) loads nothing of that message; the session
  goes on. bcp with `-b n` sends a message per n rows, so earlier batches stay.
- The answer is `(n rows affected)`, even under `SET NOCOUNT ON`.

### bcp

```sh
bcp dbo.city in cities.tsv -S 127.0.0.1,1433 -U sa -P x -d lexdb -c -u    # -c: character data, tab separated
bcp dbo.city in cities.tsv -S 127.0.0.1,1433 -U sa -P x -d lexdb -c -u -E -b 10000
bcp "SELECT * FROM dbo.city" queryout out.tsv -S 127.0.0.1,1433 -U sa -P x -d lexdb -c -u
```

`-u` trusts the server's certificate (mssql-tools18). These were checked with mssql-tools18 during development
(design/lexdb-tds.md, section 14); bcp is not installed where these pages were checked.

### From Java: SQLServerBulkCopy

[TdsBulk.java](connect/examples/java/TdsBulk.java) loads [cities.csv](connect/examples/java/cities.csv) with
`SQLServerBulkCopy`, then sends a JDBC batch of 5,000 rows as bulk copy (`useBulkCopyForBatchInsert=true`). It counts
the rows on a new connection: on the connection that ran the bulk copy, lexdb leaves `SET FMTONLY ON` in effect, so
later queries there give no rows until `SET FMTONLY OFF` ([known issues](KNOWN-ISSUES.md)):

```sh
javac -cp mssql-jdbc-13.6.2.jre11.jar -d out docs/lexdb/connect/examples/java/TdsBulk.java
java -cp out:mssql-jdbc-13.6.2.jre11.jar TdsBulk \
  'jdbc:sqlserver://127.0.0.1:1433;databaseName=lexdb;encrypt=false;user=sa;password=x' cities.csv
```

```
from the file: 4 rows, population 1110000
batch: 5000 rows sent
after the batch: 5004 rows
```

### From .NET: SqlBulkCopy

```csharp
using var conn = new SqlConnection("Server=127.0.0.1,1433;Database=lexdb;User Id=sa;Password=x;Encrypt=False");
conn.Open();
using var bulk = new SqlBulkCopy(conn, SqlBulkCopyOptions.KeepNulls | SqlBulkCopyOptions.CheckConstraints, null);
bulk.DestinationTableName = "dbo.city";
bulk.WriteToServer(table);          // a DataTable, a DataReader or DataRow[]
```

Checked with Microsoft.Data.SqlClient 6 during development; not run for these pages.

### From Lexell: bulkInsert and bulkStream

lib/sqlserver's `bulkInsert(table, columns, rows, options)` loads rows held in memory, and `bulkStream` loads rows a
batch at a time from a function, so a load of any size needs memory for one batch.
[tds_hello.lxl](connect/examples/lexell/tds_hello.lxl) uses `bulkInsert`:

```
let more: [][]V = [[V.Int(3), V.Text("plum"), V.Dec(2.40m)], [V.Int(4), V.Text("quince"), V.Dec(3.00m)]]
let n = try c.bulkInsert("dbo.tds_fruit", &["id", "name", "price"], &more, &sqlserver.bulkOptions())
```

### Differences from SQL Server

- Constraints are always checked; triggers do not exist.
- A malformed message is error 50000 with lexdb's text (SQL Server: 4804, 4815); a type lexdb does not take
  (`sql_variant`, CLR types) is 4816.
- `datetime2(7)` keeps microseconds (the last digit is rounded); a `datetimeoffset` keeps its instant, not its offset.
- `BULK INSERT` (the T-SQL statement that reads a file on the server) and `OPENROWSET(BULK ...)` are not supported.

## Oracle: array DML

Oracle clients load many rows by executing one `INSERT` with arrays of bind values: one round trip for the whole
array. lexdb's Oracle door takes it as Oracle does:

- Each row of the array runs under its own savepoint, in the session's transaction (begun first if none is open).
- Without batch errors, the first row that fails ends the call with its error, and the rows before it stay (they are
  in the transaction, to commit or roll back), as in Oracle.
- With batch errors (python-oracledb's `batcherrors=True`), every row is tried; the failures are reported with their
  offsets and the others stay.
- Row counts per row (`arraydmlrowcounts`, JDBC's `executeBatch` result) are given.

### From Java: executeBatch

[OraHello.java](connect/examples/java/OraHello.java) inserts with `addBatch` and `executeBatch`, which ojdbc sends as
one array DML call:

```java
try (PreparedStatement p = c.prepareStatement("INSERT INTO jora_fruit VALUES (?, ?, ?)")) {
    for (...) { p.setInt(1, id); p.setString(2, name); p.setBigDecimal(3, price); p.addBatch(); }
    int[] counts = p.executeBatch();
}
```

### From Python: executemany

```python
import oracledb
conn = oracledb.connect(user="sa", password="sa", dsn="127.0.0.1:1521/lexdb")
cur = conn.cursor()
cur.executemany("INSERT INTO city (id, name) VALUES (:1, :2)", rows, batcherrors=True)
for e in cur.getbatcherrors():
    print(e.offset, e.message)
conn.commit()
```

Checked with python-oracledb 26.1 (thin) during development; not run for these pages.

### In the server: INSERT ... SELECT

PL/SQL's `FORALL` and `BULK COLLECT` need collections, which lexdb's PL/SQL does not have (PLS-00103). To make many
rows in the server, use one `INSERT ... SELECT`; a row generator is `CONNECT BY LEVEL`:

<!-- example: oracle -->
```sql
CREATE TABLE town (id NUMBER PRIMARY KEY, name VARCHAR2(40));
INSERT INTO town SELECT LEVEL, 'town ' || LEVEL FROM dual CONNECT BY LEVEL <= 1000;
SELECT count(*), max(name) FROM town;
```

```text
Table created.

1000 rows created.

COUNT(*) MAX(NAME)
-------- ---------
    1000 town 999

1 row selected.
```

### Differences from Oracle

- SQL\*Loader and the direct-path load interface (OCI) are not available: they need the thick client.
- `INSERT ALL` and `INSERT /*+ APPEND */` direct-path inserts are not supported (the hint is a comment).
- External tables are not supported.
- `FORALL` and `BULK COLLECT` are not supported: lexdb's PL/SQL has no collections.

## See also

[INSERT (PostgreSQL)](sql/postgresql/insert.md) · [INSERT (T-SQL)](sql/tsql/insert.md) ·
[INSERT (Oracle)](sql/oracle/insert.md) · [Transactions](transactions.md)
