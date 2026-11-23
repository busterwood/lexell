# CREATE SEQUENCE

Makes a sequence: a counter that gives a new number each time it is asked.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
CREATE [ { TEMPORARY | TEMP } ] SEQUENCE [ IF NOT EXISTS ] name
    [ AS data_type ]
    [ INCREMENT [ BY ] increment ]
    [ MINVALUE minvalue | NO MINVALUE ] [ MAXVALUE maxvalue | NO MAXVALUE ]
    [ START [ WITH ] start ] [ CACHE cache ] [ [ NO ] CYCLE ]
    [ OWNED BY { table_name.column_name | NONE } ]
```

## Arguments

`TEMPORARY` or `TEMP`
: The sequence belongs to the session and is dropped when it ends.

`IF NOT EXISTS`
: If a relation of the name exists, does nothing and gives a notice.

*name*
: The sequence's name, optionally schema-qualified.

`AS` *data_type*
: `smallint`, `integer` or `bigint` (the default), which sets the default bounds.

`INCREMENT BY` *increment*
: Added at each step; negative for a sequence that counts down. 1 by default.

`MINVALUE`, `MAXVALUE`
: The bounds. By default 1 and the type's largest for an ascending sequence; the type's smallest and -1 for a
  descending one.

`START WITH` *start*
: The first value: `MINVALUE` by default going up, `MAXVALUE` going down. It must be within the bounds.

`CACHE` *cache*
: Accepted (at least 1) and shown in `pg_sequences`.

`CYCLE`, `NO CYCLE`
: Whether the sequence goes back to the other bound after the last value. Without `CYCLE`, a step past the bound is
  an error (2200H).

`OWNED BY` *table*.*column*
: Ties the sequence to a column: dropping the column or its table drops the sequence.

## Remarks

- The functions are `nextval('name')`, `currval('name')` (the session's last value of it), `lastval()` (the
  session's last value of any) and `setval('name', n [, is_called])`. A sequence is also read as a one-row table
  (`SELECT * FROM s`: `last_value`, `log_cnt`, `is_called`).
- `nextval` is not rolled back: a value taken in a transaction that rolls back is not given again.
- A column's default `nextval('s')`, `serial` and identity columns use sequences.
- `pg_sequences`, `pg_sequence` and `information_schema.sequences` list them.

## Differences from PostgreSQL

- `log_cnt` follows PostgreSQL's for the first 32 values only (lexdb-gaps.md 2.2).
- `CREATE UNLOGGED SEQUENCE` is a syntax error.

## Examples

### A. A sequence and its functions

<!-- example: postgresql -->
```sql
CREATE SEQUENCE order_no;
SELECT nextval('order_no'), nextval('order_no'), currval('order_no');
SELECT setval('order_no', 100), nextval('order_no');
SELECT * FROM order_no;
```

```text
CREATE SEQUENCE
 nextval | nextval | currval
---------+---------+---------
       1 |       2 |       2
(1 row)

 setval | nextval
--------+---------
    100 |     101
(1 row)

 last_value | log_cnt | is_called
------------+---------+-----------
        101 |      32 | t
(1 row)
```

### B. Options

<!-- example: postgresql -->
```sql
CREATE SEQUENCE ring START WITH 100 INCREMENT BY 10 MINVALUE 50 MAXVALUE 120 CYCLE;
SELECT nextval('ring'), nextval('ring'), nextval('ring'), nextval('ring');
CREATE SEQUENCE down INCREMENT -1;
SELECT nextval('down'), nextval('down');
CREATE SEQUENCE tiny AS smallint MAXVALUE 2;
SELECT nextval('tiny'), nextval('tiny');
SELECT nextval('tiny');
```

```text
CREATE SEQUENCE
 nextval | nextval | nextval | nextval
---------+---------+---------+---------
     100 |     110 |     120 |      50
(1 row)

CREATE SEQUENCE
 nextval | nextval
---------+---------
      -1 |      -2
(1 row)

CREATE SEQUENCE
 nextval | nextval
---------+---------
       1 |       2
(1 row)

ERROR:  nextval: reached maximum value of sequence "tiny" (2)
```

### C. Not rolled back

<!-- example: postgresql -->
```sql
BEGIN;
SELECT nextval('order_no');
ROLLBACK;
SELECT nextval('order_no');
```

```text
BEGIN
 nextval
---------
     102
(1 row)

ROLLBACK
 nextval
---------
     103
(1 row)
```

### D. A sequence for a column's default

<!-- example: postgresql -->
```sql
CREATE SEQUENCE invoice_no START WITH 1000;
CREATE TABLE invoice (no int DEFAULT nextval('invoice_no') PRIMARY KEY, total numeric(8,2));
ALTER SEQUENCE invoice_no OWNED BY invoice.no;
INSERT INTO invoice (total) VALUES (9.50), (12.00) RETURNING no;
SELECT sequencename, start_value, increment_by, last_value FROM pg_sequences ORDER BY sequencename;
```

```text
CREATE SEQUENCE
CREATE TABLE
ALTER SEQUENCE
  no
------
 1000
 1001
(2 rows)

INSERT 0 2
 sequencename | start_value | increment_by | last_value
--------------+-------------+--------------+------------
 down         |          -1 |           -1 |         -2
 invoice_no   |        1000 |            1 |       1001
 order_no     |           1 |            1 |        103
 ring         |         100 |           10 |         50
 tiny         |           1 |            1 |          2
(5 rows)
```

### E. Errors

<!-- example: postgresql -->
```sql
CREATE SEQUENCE order_no;
CREATE SEQUENCE IF NOT EXISTS order_no;
CREATE SEQUENCE bad START 5 MINVALUE 10;
CREATE SEQUENCE bad AS numeric;
SELECT nextval('nosuch');
```

```text
ERROR:  relation "order_no" already exists
NOTICE:  relation "order_no" already exists, skipping
CREATE SEQUENCE
ERROR:  START value (5) cannot be less than MINVALUE (10)
ERROR:  sequence type must be smallint, integer, or bigint
ERROR:  relation "nosuch" does not exist
```

## See also

[ALTER SEQUENCE](alter-sequence.md) · [DROP SEQUENCE](drop-sequence.md) · [CREATE TABLE](create-table.md)
