# Quick start

This page builds lexdb, starts it with all three doors, and uses one table from PostgreSQL, SQL Server and Oracle
clients.

## Build

lexdb is a Lexell program. Build the compiler once (see the [repository README](../../../README.md#quick-start)),
then lexdb, from the repository root:

```sh
lexell/compiler/build.sh
lexell/compiler/out/lxlc lexell/cmd/lexdb.lxl -O -o lexdb
```

The result is one executable, `lexdb`, with no runtime dependencies beyond Linux.

## Start

```sh
./lexdb ./data 127.0.0.1:5433 --tds 127.0.0.1:1433 --tns 127.0.0.1:1521
```

```
lexdb: listening on 127.0.0.1:5433, data in ./data
lexdb: TDS (SQL Server) on 127.0.0.1:1433
lexdb: TNS (Oracle) on 127.0.0.1:1521
```

- `./data` is the data directory. lexdb makes it when it is not there.
- `127.0.0.1:5433` is the PostgreSQL door. Without any address lexdb listens there.
- `--tds` and `--tns` open the SQL Server and Oracle doors. Leave them out to serve PostgreSQL clients only.
- Logins are not checked (`--auth trust`, the default). Keep the listeners on loopback until you have set passwords;
  see [security](security.md).

Ctrl-C (or `SIGTERM`) stops the server. The data stays in `./data` for the next start. All the options are in
[server options](server-options.md).

## Connect with psql

Any user name and database name are accepted. The database is always `lexdb`.

```sh
psql -h 127.0.0.1 -p 5433 -U postgres lexdb
```

Make a table and put rows in it:

<!-- example: postgresql -->
```sql
CREATE TABLE fruit (id int PRIMARY KEY, name text NOT NULL, price numeric(10,2));
INSERT INTO fruit VALUES (1, 'apple', 1.20), (2, 'pear', 0.85), (3, 'plum', 2.40);
SELECT * FROM fruit WHERE price < 2 ORDER BY id;
```

```text
CREATE TABLE
INSERT 0 3
 id | name  | price
----+-------+-------
  1 | apple |  1.20
  2 | pear  |  0.85
(2 rows)
```

## The same table from a SQL Server client

The SQL Server door's default schema, `dbo`, is the PostgreSQL door's `public`, so the table is `fruit` or
`dbo.fruit` there. With `sqlcmd` (any password under `trust`):

```sh
sqlcmd -S 127.0.0.1,1433 -U sa -P x -d lexdb -C
```

<!-- example: tsql -->
```sql
SELECT TOP (2) id, UPPER(name) AS name, price FROM dbo.fruit ORDER BY price DESC;
INSERT INTO fruit VALUES (4, N'quince', 3.00);
GO
```

```text
id name  price
-- ----- -----
3  PLUM  2.40
1  APPLE 1.20

(2 rows affected)

(1 row affected)
```

## The same table from an Oracle client

In the Oracle door a user is a schema, made at the login's first connection. A bare name is looked for in the login's
own schema, then in the PostgreSQL door's `public` schema, so `fruit` finds the table above (and the tables the login
makes there are in its own schema: see [Schemas](connect/oracle.md#schemas)). Under
`trust` an Oracle login with no password set uses its own user name as the password, as the driver sends it (JDBC
and SQLcl send it upper-cased):

```sh
sql sa/SA@127.0.0.1:1521/lexdb
```

<!-- example: oracle -->
```sql
SELECT id, name, price FROM fruit ORDER BY id;
```

```text
ID NAME   PRICE
-- ------ -----
 1 apple    1.2
 2 pear    0.85
 3 plum     2.4
 4 quince     3

4 rows selected.
```

## Next

- [Overview](overview.md): what lexdb is and how it differs.
- Connecting: [PostgreSQL](connect/postgresql.md), [SQL Server](connect/sqlserver.md), [Oracle](connect/oracle.md),
  with Java and Lexell programs.
- [Bulk loading](bulk-load.md) and [read replicas](replicas.md).
- The SQL reference per door: [PostgreSQL](sql/postgresql/README.md), [T-SQL](sql/tsql/README.md),
  [Oracle](sql/oracle/README.md).
