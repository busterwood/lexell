# ALTER SEQUENCE

Changes a sequence's options, restarts it, or renames or moves it.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
ALTER SEQUENCE [ IF EXISTS ] name
    [ AS data_type ]
    [ INCREMENT [ BY ] increment ]
    [ MINVALUE minvalue | NO MINVALUE ] [ MAXVALUE maxvalue | NO MAXVALUE ]
    [ START [ WITH ] start ]
    [ RESTART [ [ WITH ] restart ] ]
    [ CACHE cache ] [ [ NO ] CYCLE ]
    [ OWNED BY { table_name.column_name | NONE } ]
ALTER SEQUENCE [ IF EXISTS ] name RENAME TO new_name
ALTER SEQUENCE [ IF EXISTS ] name SET SCHEMA new_schema
ALTER SEQUENCE [ IF EXISTS ] name OWNER TO { new_owner | CURRENT_USER | SESSION_USER }
```

## Arguments

`IF EXISTS`
: If the sequence does not exist, does nothing and gives a notice.

`AS`, `INCREMENT`, `MINVALUE`, `MAXVALUE`, `CACHE`, `CYCLE`, `OWNED BY`
: As in [CREATE SEQUENCE](create-sequence.md). Options not given keep their values.

`START WITH` *start*
: The value a later `RESTART` without a value goes back to. It does not change the current value.

`RESTART [ WITH` *restart* `]`
: The next `nextval` gives *restart*, or the start value.

`RENAME TO`, `SET SCHEMA`, `OWNER TO`
: Renames the sequence, moves it to another schema, or gives it to another role.

## Remarks

- A column's default that names the sequence (`nextval('s')`) goes on working after `RENAME TO`.
- The sequence of an identity column is changed with `ALTER TABLE ... ALTER COLUMN ... RESTART` or `SET` options
  (see [ALTER TABLE](alter-table.md)).

## Differences from PostgreSQL

- `RESTART` takes effect at once and is not rolled back with the transaction (lexdb-gaps.md 2.2).
- `SET LOGGED` and `SET UNLOGGED` are refused (0A000).

## Examples

<!--setup: postgresql
CREATE SEQUENCE order_no;
SELECT nextval('order_no'), nextval('order_no');
-->

The examples start from a sequence that has given 1 and 2:

```sql
CREATE SEQUENCE order_no;
SELECT nextval('order_no'), nextval('order_no');
```

### A. Restart

<!-- example: postgresql -->
```sql
ALTER SEQUENCE order_no RESTART WITH 50;
SELECT nextval('order_no');
ALTER SEQUENCE order_no RESTART;
SELECT nextval('order_no');
```

```text
ALTER SEQUENCE
 nextval
---------
      50
(1 row)

ALTER SEQUENCE
 nextval
---------
       1
(1 row)
```

### B. Options

<!-- example: postgresql -->
```sql
ALTER SEQUENCE order_no INCREMENT BY 5 MAXVALUE 20 START WITH 10;
SELECT nextval('order_no'), nextval('order_no');
ALTER SEQUENCE order_no RESTART;
SELECT nextval('order_no');
SELECT start_value, increment_by, max_value FROM pg_sequences WHERE sequencename = 'order_no';
```

```text
ALTER SEQUENCE
 nextval | nextval
---------+---------
       6 |      11
(1 row)

ALTER SEQUENCE
 nextval
---------
      10
(1 row)

 start_value | increment_by | max_value
-------------+--------------+-----------
          10 |            5 |        20
(1 row)
```

### C. RESTART is not rolled back

<!-- example: postgresql -->
```sql
BEGIN;
ALTER SEQUENCE order_no RESTART WITH 1;
ROLLBACK;
SELECT nextval('order_no');
```

```text
BEGIN
ALTER SEQUENCE
ROLLBACK
 nextval
---------
       1
(1 row)
```

### D. Rename

<!-- example: postgresql -->
```sql
CREATE TABLE invoice (no int DEFAULT nextval('order_no'), total numeric(8,2));
ALTER SEQUENCE order_no RENAME TO invoice_no;
INSERT INTO invoice (total) VALUES (9.50) RETURNING no;
ALTER SEQUENCE IF EXISTS order_no RESTART;
ALTER SEQUENCE invoice_no SET LOGGED;
```

```text
CREATE TABLE
ALTER SEQUENCE
 no
----
  6
(1 row)

INSERT 0 1
NOTICE:  relation "order_no" does not exist, skipping
ALTER SEQUENCE
ERROR:  lexdb: ALTER SEQUENCE takes its options (RESTART, INCREMENT, ...), RENAME TO, SET SCHEMA and OWNER TO, not SET LOGGED or UNLOGGED
```

## See also

[CREATE SEQUENCE](create-sequence.md) · [DROP SEQUENCE](drop-sequence.md) · [ALTER TABLE](alter-table.md)
