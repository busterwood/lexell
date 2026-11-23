# Sequence functions

`nextval`, `currval`, `setval` and `lastval`: take and set the values of a sequence.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
nextval ( 'sequence' ) → bigint
currval ( 'sequence' ) → bigint
setval ( 'sequence', value [, is_called ] ) → bigint
lastval ( ) → bigint
```

## Functions

`nextval`
: Moves the sequence on by its increment and returns the new value. Past its maximum (or minimum) it wraps with
  `CYCLE`, and is 2200H without.

`currval`
: The value `nextval` last gave this session for the sequence. Before any `nextval` in the session it is 55000.

`setval`
: Sets the sequence's value and returns it. With *is_called* true (the default) the next `nextval` gives *value*
  plus the increment; with false it gives *value* itself.

`lastval`
: The value `nextval` last gave this session, of any sequence. Before any it is 55000.

## Remarks

- *sequence* is the sequence's name as text, optionally schema-qualified (`'app.order_no'`), or a `regclass`
  (`'order_no'::regclass`).
- `nextval` and `setval` are not rolled back: a value taken in a transaction that rolls back is not given again.
- A `serial` or identity column takes its values with `nextval` of its own sequence; `pg_get_serial_sequence`
  names it (see [catalog functions](functions-catalog.md)).
- See [CREATE SEQUENCE](create-sequence.md) for the options.

## Differences from PostgreSQL

- `DROP SEQUENCE` is not refused while a column default uses the sequence (see [DROP SEQUENCE](drop-sequence.md)).

## Examples

<!--setup: postgresql
CREATE SEQUENCE order_no START 1000;
-->

The examples use this sequence:

```sql
CREATE SEQUENCE order_no START 1000;
```

### A. nextval and currval

<!-- example: postgresql -->
```sql
SELECT nextval('order_no') AS first, nextval('order_no') AS second, currval('order_no') AS current;
```

```text
 first | second | current
-------+--------+---------
  1000 |   1001 |    1001
(1 row)
```

### B. setval

<!-- example: postgresql -->
```sql
SELECT setval('order_no', 2000) AS set_to, nextval('order_no') AS next;
SELECT setval('order_no', 3000, false) AS set_to, nextval('order_no') AS next;
```

```text
 set_to | next
--------+------
   2000 | 2001
(1 row)

 set_to | next
--------+------
   3000 | 3000
(1 row)
```

### C. lastval

<!-- example: postgresql -->
```sql
CREATE SEQUENCE ticket_no;
SELECT nextval('ticket_no') AS ticket, lastval() AS last, nextval('order_no') AS order_no, lastval() AS last2;
```

```text
CREATE SEQUENCE
 ticket | last | order_no | last2
--------+------+----------+-------
      1 |    1 |     3001 |  3001
(1 row)
```

### D. Not rolled back

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
    3002
(1 row)

ROLLBACK
 nextval
---------
    3003
(1 row)
```

### E. As a column default

<!-- example: postgresql -->
```sql
CREATE TABLE orders (no bigint DEFAULT nextval('order_no') PRIMARY KEY, item text);
INSERT INTO orders (item) VALUES ('pen'), ('ink') RETURNING no, item;
```

```text
CREATE TABLE
  no  | item
------+------
 3004 | pen
 3005 | ink
(2 rows)

INSERT 0 2
```

### F. Errors

<!-- example: postgresql -->
```sql
CREATE SEQUENCE fresh;
SELECT currval('fresh');
SELECT nextval('nosuch');
CREATE SEQUENCE tiny MAXVALUE 2;
SELECT nextval('tiny'), nextval('tiny');
SELECT nextval('tiny');
```

```text
CREATE SEQUENCE
ERROR:  currval of sequence "fresh" is not yet defined in this session
ERROR:  relation "nosuch" does not exist
CREATE SEQUENCE
 nextval | nextval
---------+---------
       1 |       2
(1 row)

ERROR:  nextval: reached maximum value of sequence "tiny" (2)
```

## See also

[CREATE SEQUENCE](create-sequence.md) · [ALTER SEQUENCE](alter-sequence.md) · [DROP SEQUENCE](drop-sequence.md) ·
[Catalog functions](functions-catalog.md)
