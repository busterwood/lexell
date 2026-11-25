# COPY

Loads rows from the client into a table, or sends a table's or a query's rows to the client, in text, CSV or (on the way out) JSON.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
COPY table_name [ ( column_name [, ...] ) ] FROM STDIN [ [ WITH ] ( option [, ...] ) ]
COPY { table_name [ ( column_name [, ...] ) ] | ( query ) } TO STDOUT [ [ WITH ] ( option [, ...] ) ]
```

The options (`FORMAT text | csv | json`, `DELIMITER`, `NULL`, `HEADER`, `QUOTE`, `ESCAPE`, `FORCE_QUOTE`,
`FORCE_NOT_NULL`, `FORCE_NULL`, `FORCE_ARRAY`, `ON_ERROR`, `REJECT_LIMIT`, `LOG_VERBOSITY`, `ENCODING`, `FREEZE` and
lexdb's `batch_rows n`) and the older form of the statement are described in [Bulk
loading](../../bulk-load.md#postgresql-copy).

## Arguments

*table_name*, *column_name*
: The table, and the columns the data's fields go to (or come from), in order.

`FROM STDIN`
: The data comes from the client, after the statement: psql sends the lines that follow it, up to `\.`.

*query*, `TO STDOUT`
: The rows go to the client.

`FORMAT json` (`COPY TO` only)
: One JSON object a row, its keys the column names, its values as `to_json` writes them (numbers, booleans and null
  as JSON's, arrays as arrays, everything else as strings). `FORCE_ARRAY` writes the objects as one array: `[` on a
  line, each row on a line after a space or a comma, `]`. Without rows it writes `[` and `]`. `HEADER`, `QUOTE`,
  `ESCAPE` and the `FORCE_` options are 0A000 with JSON, `DELIMITER` and `NULL` 42601, and `FORCE_ARRAY` with
  another format 22023. `COPY FROM` with `FORMAT json` is 22023, as in PostgreSQL 18 and 19.

`ON_ERROR ignore` (`COPY FROM` only)
: A row with a value its column's type does not take is skipped, and the load goes on. Any other error (a missing
  or an extra field, a constraint, a duplicate key) still ends the `COPY`, and none of its rows are kept. At the end
  a NOTICE says how many rows were skipped. `ON_ERROR stop`, the default, ends the `COPY` at the first bad row.

`REJECT_LIMIT` *n*
: With `ON_ERROR ignore`: the `COPY` fails (22P02) when more than *n* rows have been skipped. *n* below 1, a use
  without `ON_ERROR ignore`, and a use with `COPY TO` are 22023.

`LOG_VERBOSITY` { `default` | `verbose` | `silent` }
: With `ON_ERROR ignore`: `verbose` also gives a NOTICE for each row skipped, naming the line, the column and the
  value; `silent` gives no NOTICE at all.

## Remarks

- See [Bulk loading](../../bulk-load.md#postgresql-copy) for the formats, the options, the speed, and loading from
  psql, Java and other clients.
- A `COPY FROM` is one statement: all its rows go in, or none do, unless `batch_rows` commits it in parts.
- The command tag is `COPY n`.
- An error in the statement itself (an unknown table or column, an option that is not valid or is given twice) comes
  before any data is sent. psql then skips the lines of the script up to a line `\.`, with lexdb as with PostgreSQL:
  put one right after a `COPY ... FROM STDIN` whose options may be wrong (example F).

## Differences from PostgreSQL

- `COPY ... FROM 'file'`, `TO 'file'` and `PROGRAM` are refused (0A000): lexdb reads and writes the client's data
  only. Use psql's `\copy` for files on the client.
- The binary format is not supported (0A000).
- `WITH (batch_rows n)` is lexdb's own.
- `ON_ERROR set_null` (PostgreSQL 19) is 0A000.
- A view as the target of `COPY ... FROM STDIN` is refused before the client is asked for the data; PostgreSQL
  refuses it after. The other errors of the table, the columns and the options come first in both.

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

### D. JSON out

<!-- example: postgresql -->
```sql
COPY (SELECT id, name, pop, id > 1 AS later, ARRAY[id, id * 2] AS ids FROM city ORDER BY id) TO STDOUT WITH (FORMAT json);
COPY (SELECT id, name FROM city ORDER BY id) TO STDOUT WITH (FORMAT json, FORCE_ARRAY);
COPY (SELECT id FROM city WHERE id > 100) TO STDOUT WITH (FORMAT json, FORCE_ARRAY true);
```

```text
{"id":1,"name":"Lisbon","pop":545000,"later":false,"ids":[1,2]}
{"id":2,"name":"Porto","pop":null,"later":true,"ids":[2,4]}
{"id":3,"name":"Braga, the old one","pop":null,"later":true,"ids":[3,6]}
[
 {"id":1,"name":"Lisbon"}
,{"id":2,"name":"Porto"}
,{"id":3,"name":"Braga, the old one"}
]
[
]
```

### E. Skip the rows that do not fit

<!-- example: postgresql -->
```sql
CREATE TABLE reading (sensor text, taken date, val int);
COPY reading FROM STDIN WITH (ON_ERROR ignore);
a	2026-01-01	10
a	2026-01-02	eleven
b	2026-13-45	12
b	2026-01-04	13
\.
COPY reading FROM STDIN WITH (ON_ERROR ignore, LOG_VERBOSITY verbose);
c	2026-02-01	20
c	2026-02-02	x
\.
COPY reading FROM STDIN WITH (ON_ERROR ignore, LOG_VERBOSITY silent);
d	2026-03-01	30
d	2026-03-02	y
\.
COPY reading FROM STDIN WITH (ON_ERROR ignore, REJECT_LIMIT 1);
e	2026-04-01	40
e	2026-04-02	p
e	2026-04-03	q
e	2026-04-04	50
\.
COPY reading FROM STDIN WITH (ON_ERROR ignore);
f	2026-05-01
\.
SELECT * FROM reading ORDER BY sensor, taken;
```

```text
CREATE TABLE
NOTICE:  2 rows were skipped due to data type incompatibility
COPY 2
NOTICE:  skipping row due to data type incompatibility at line 2 for column "val": "x"
NOTICE:  1 row was skipped due to data type incompatibility
COPY 1
COPY 1
ERROR:  skipped more than REJECT_LIMIT (1) rows due to data type incompatibility
CONTEXT:  COPY reading, line 3: "e	2026-04-03	q"
ERROR:  missing data for column "val"
CONTEXT:  COPY reading, line 1: "f	2026-05-01"
 sensor |   taken    | val
--------+------------+-----
 a      | 2026-01-01 |  10
 b      | 2026-01-04 |  13
 c      | 2026-02-01 |  20
 d      | 2026-03-01 |  30
(4 rows)
```

### F. Option errors

Put the end marker right after a statement whose options may be wrong: psql skips the script's lines up to it when
the `COPY` fails.

<!-- example: postgresql -->
```sql
COPY reading FROM STDIN WITH (REJECT_LIMIT 3);
\.
COPY reading FROM STDIN WITH (ON_ERROR ignore, REJECT_LIMIT 0);
\.
COPY reading FROM STDIN WITH (ON_ERROR bogus);
\.
COPY reading FROM STDIN WITH (FORMAT json);
\.
COPY reading FROM STDIN WITH (ON_ERROR set_null);
\.
COPY reading FROM STDIN WITH (FORMAT csv, FORMAT text);
\.
COPY reading FROM STDIN WITH (FORMAT csv, FORCE_NULL (nosuch));
\.
COPY reading (sensor) FROM STDIN WITH (FORMAT csv, FORCE_NULL (val));
\.
COPY reading FROM STDIN WITH (HEADER 2);
\.
COPY reading TO STDOUT WITH (FORMAT json, HEADER);
COPY reading TO STDOUT WITH (FORCE_ARRAY);
COPY reading TO STDOUT WITH (ON_ERROR ignore);
```

```text
ERROR:  COPY REJECT_LIMIT requires ON_ERROR to be set to IGNORE
ERROR:  REJECT_LIMIT (0) must be greater than zero
ERROR:  COPY ON_ERROR "bogus" not recognized
ERROR:  COPY FORMAT JSON is not supported for COPY FROM
ERROR:  lexdb: COPY's ON_ERROR set_null is not supported
ERROR:  conflicting or redundant options
ERROR:  column "nosuch" of relation "reading" does not exist
ERROR:  FORCE_NULL column "val" not referenced by COPY
ERROR:  header requires a Boolean value or "match"
ERROR:  cannot specify HEADER in JSON mode
ERROR:  COPY FORCE_ARRAY requires JSON mode
ERROR:  COPY ON_ERROR cannot be used with COPY TO
```

## See also

[Bulk loading](../../bulk-load.md) · [INSERT](insert.md)
