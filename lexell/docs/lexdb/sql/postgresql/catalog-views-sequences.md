# Catalog: views and sequences

`pg_views`, `information_schema.views`, `pg_matviews`, `pg_rewrite`, `pg_sequence`, `pg_sequences`,
`information_schema.sequences` and `pg_depend`.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
SELECT ... FROM [ pg_catalog. ] pg_views
SELECT ... FROM information_schema.views
SELECT ... FROM [ pg_catalog. ] pg_matviews
SELECT ... FROM [ pg_catalog. ] pg_rewrite
SELECT ... FROM [ pg_catalog. ] pg_sequence
SELECT ... FROM [ pg_catalog. ] pg_sequences
SELECT ... FROM information_schema.sequences
SELECT ... FROM [ pg_catalog. ] pg_depend
```

## Views

Each relation has all of PostgreSQL 18's columns. The columns below are the ones lexdb fills in; the others are
NULL, zero, false or empty.

`pg_views`: one row per view
: `schemaname`, `viewname`, `viewowner`, `definition`.

`information_schema.views`: one row per view
: `table_catalog`, `table_schema`, `table_name`, `view_definition`, `check_option` (`NONE`), and `is_updatable`,
  `is_insertable_into` and the `is_trigger_` columns, all `NO`.

`pg_matviews`: one row per materialized view
: `schemaname`, `matviewname`, `matviewowner`, `tablespace` (NULL), `hasindexes`, `ispopulated`, `definition`.

`pg_rewrite`
: No rows: lexdb has no rules.

`pg_sequence`: one row per sequence
: `seqrelid`, `seqtypid`, `seqstart`, `seqincrement`, `seqmax`, `seqmin`, `seqcache`, `seqcycle`.

`pg_sequences`: one row per sequence
: `schemaname`, `sequencename`, `sequenceowner`, `data_type`, `start_value`, `min_value`, `max_value`,
  `increment_by`, `cycle`, `cache_size`, `last_value` (NULL until `nextval` is first called).

`information_schema.sequences`
: `sequence_catalog`, `sequence_schema`, `sequence_name`, `data_type`, `numeric_precision`,
  `numeric_precision_radix`, `numeric_scale`, `start_value`, `minimum_value`, `maximum_value`, `increment`,
  `cycle_option`.

`pg_depend`
: A row for each sequence owned by a column: `classid` and `refclassid` (1259, `pg_class`), `objid` (the
  sequence), `refobjid` and `refobjsubid` (the table and column), `deptype` (`a` for a `serial` column, `i` for an
  identity column).

## Remarks

- psql's `\dv` and `\ds` list views and sequences from these relations.
- `pg_get_serial_sequence` finds a column's sequence through `pg_depend`.

## Differences from PostgreSQL

- A view's definition is its text as written, with its `;`, not PostgreSQL's rewritten query.
- `pg_rewrite` has no rows, though `pg_class.relhasrules` is true for a view.
- `information_schema.sequences` leaves out the sequences of identity columns (PostgreSQL lists them).
- `pg_depend` holds only the column-to-sequence rows: view, constraint and type dependencies are not there.

## Examples

<!--setup: postgresql
CREATE TABLE orders (no serial PRIMARY KEY, code int GENERATED ALWAYS AS IDENTITY, total numeric(10,2));
CREATE VIEW big_orders AS SELECT no, total FROM orders WHERE total > 100;
CREATE SEQUENCE ticket START 10 INCREMENT 5 MAXVALUE 1000 CYCLE;
-->

The examples use these objects:

```sql
CREATE TABLE orders (no serial PRIMARY KEY, code int GENERATED ALWAYS AS IDENTITY, total numeric(10,2));
CREATE VIEW big_orders AS SELECT no, total FROM orders WHERE total > 100;
CREATE SEQUENCE ticket START 10 INCREMENT 5 MAXVALUE 1000 CYCLE;
```

### A. Views

<!-- example: postgresql -->
```sql
SELECT viewname, viewowner, definition FROM pg_views WHERE schemaname = 'public';
SELECT table_name, check_option, is_updatable FROM information_schema.views WHERE table_schema = 'public';
SELECT count(*) AS matviews FROM pg_matviews;
```

```text
  viewname  | viewowner |                   definition
------------+-----------+-------------------------------------------------
 big_orders | postgres  | SELECT no, total FROM orders WHERE total > 100;
(1 row)

 table_name | check_option | is_updatable
------------+--------------+--------------
 big_orders | NONE         | NO
(1 row)

 matviews
----------
        0
(1 row)
```

### B. pg_sequences

<!-- example: postgresql -->
```sql
SELECT nextval('ticket');
SELECT sequencename, data_type, start_value, increment_by, max_value, cycle, last_value
FROM pg_sequences ORDER BY sequencename;
```

```text
 nextval
---------
      10
(1 row)

  sequencename   | data_type | start_value | increment_by | max_value  | cycle | last_value
-----------------+-----------+-------------+--------------+------------+-------+------------
 orders_code_seq | integer   |           1 |            1 | 2147483647 | f     |
 orders_no_seq   | integer   |           1 |            1 | 2147483647 | f     |
 ticket          | bigint    |          10 |            5 |       1000 | t     |         10
(3 rows)
```

### C. pg_sequence and information_schema.sequences

<!-- example: postgresql -->
```sql
SELECT seqrelid::regclass AS seq, seqtypid::regtype AS type, seqstart, seqincrement, seqcycle
FROM pg_sequence ORDER BY 1;
SELECT sequence_name, data_type, start_value, increment, cycle_option FROM information_schema.sequences
ORDER BY sequence_name;
```

```text
       seq       |  type   | seqstart | seqincrement | seqcycle
-----------------+---------+----------+--------------+----------
 ticket          | bigint  |       10 |            5 | t
 orders_code_seq | integer |        1 |            1 | f
 orders_no_seq   | integer |        1 |            1 | f
(3 rows)

 sequence_name | data_type | start_value | increment | cycle_option
---------------+-----------+-------------+-----------+--------------
 orders_no_seq | integer   | 1           | 1         | NO
 ticket        | bigint    | 10          | 5         | YES
(2 rows)
```

### D. Which column owns a sequence

<!-- example: postgresql -->
```sql
SELECT objid::regclass AS seq, refobjid::regclass AS "table", a.attname AS "column", d.deptype
FROM pg_depend d JOIN pg_attribute a ON a.attrelid = d.refobjid AND a.attnum = d.refobjsubid ORDER BY 1;
```

```text
       seq       | table  | column | deptype
-----------------+--------+--------+---------
 orders_code_seq | orders | code   | i
 orders_no_seq   | orders | no     | a
(2 rows)
```

### E. psql's lists

<!-- example: postgresql -->
```sql
\dv
\ds
```

```text
             List of views
 Schema |    Name    | Type |  Owner
--------+------------+------+----------
 public | big_orders | view | postgres
(1 row)

               List of sequences
 Schema |      Name       |   Type   |  Owner
--------+-----------------+----------+----------
 public | orders_code_seq | sequence | postgres
 public | orders_no_seq   | sequence | postgres
 public | ticket          | sequence | postgres
(3 rows)
```

## See also

[CREATE VIEW](create-view.md) · [CREATE SEQUENCE](create-sequence.md) · [Sequence functions](functions-sequence.md) ·
[Catalog: tables and columns](catalog-tables.md)
