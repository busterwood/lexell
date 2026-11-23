# COPY

Loads rows from the client into a table, or sends a table's or a query's rows to the client, in text or CSV.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
COPY table_name [ ( column_name [, ...] ) ] FROM STDIN [ [ WITH ] ( option [, ...] ) ]
COPY { table_name [ ( column_name [, ...] ) ] | ( query ) } TO STDOUT [ [ WITH ] ( option [, ...] ) ]
```

The options (`FORMAT text | csv`, `DELIMITER`, `NULL`, `HEADER`, `QUOTE`, `ESCAPE`, `FORCE_QUOTE`,
`FORCE_NOT_NULL`, `FORCE_NULL`, `ENCODING`, `FREEZE` and lexdb's `batch_rows n`) and the older form of the
statement are described in [Bulk loading](../../bulk-load.md#postgresql-copy).

## Arguments

*table_name*, *column_name*
: The table, and the columns the data's fields go to (or come from), in order.

`FROM STDIN`
: The data comes from the client, after the statement: psql sends the lines that follow it, up to `\.`.

*query*, `TO STDOUT`
: The rows go to the client.

## Remarks

- See [Bulk loading](../../bulk-load.md#postgresql-copy) for the formats, the options, the speed, and loading from
  psql, Java and other clients.
- A `COPY FROM` is one statement: all its rows go in, or none do, unless `batch_rows` commits it in parts.
- The command tag is `COPY n`.

## Differences from PostgreSQL

- `COPY ... FROM 'file'`, `TO 'file'` and `PROGRAM` are refused (0A000): lexdb reads and writes the client's data
  only. Use psql's `\copy` for files on the client.
- The binary format is not supported (0A000).
- `WITH (batch_rows n)` is lexdb's own.

## Examples

<!--setup: postgresql
CREATE TABLE city (id int PRIMARY KEY, name text NOT NULL, pop bigint);
-->

The examples use one table:

```sql
CREATE TABLE city (id int PRIMARY KEY, name text NOT NULL, pop bigint);
```

### A. Load text and CSV

<!-- example: postgresql -->
```sql
COPY city FROM STDIN;
1	Lisbon	545000
2	Porto	\N
\.
COPY city (id, name) FROM STDIN WITH (FORMAT csv);
3,"Braga, the old one"
\.
SELECT * FROM city ORDER BY id;
```

```text
COPY 2
COPY 1
 id |        name        |  pop
----+--------------------+--------
  1 | Lisbon             | 545000
  2 | Porto              |
  3 | Braga, the old one |
(3 rows)
```

### B. Send a query's rows

<!-- example: postgresql -->
```sql
COPY (SELECT id, name FROM city ORDER BY id) TO STDOUT WITH (FORMAT csv, HEADER);
```

```text
id,name
1,Lisbon
2,Porto
3,"Braga, the old one"
```

### C. Files on the server

<!-- example: postgresql -->
```sql
COPY city FROM '/tmp/city.csv';
COPY city TO '/tmp/city.csv';
```

```text
ERROR:  lexdb: COPY FROM reads only STDIN (a file on the server: use psql's \copy)
ERROR:  lexdb: COPY TO writes only STDOUT (a file on the server: use psql's \copy)
```

## See also

[Bulk loading](../../bulk-load.md) · [INSERT](insert.md)
