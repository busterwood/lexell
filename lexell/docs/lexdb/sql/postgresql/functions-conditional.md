# Conditional expressions

`CASE`, `coalesce`, `nullif`, `greatest`, `least` and `error_on_null`.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18 (and 19's `error_on_null`).

## Syntax

```
CASE WHEN condition THEN result [ WHEN ... ] [ ELSE result ] END
CASE expression WHEN value THEN result [ WHEN ... ] [ ELSE result ] END
coalesce ( value [, ...] ) → common type
nullif ( value1, value2 ) → type of value1
greatest ( value [, ...] ) → common type
least ( value [, ...] ) → common type
error_on_null ( value ) → type of value
```

## Functions

`CASE WHEN`
: The *result* of the first *condition* that is true; else the `ELSE` result, or NULL without `ELSE`.

`CASE expression WHEN`
: The *result* of the first *value* equal to *expression*. NULL equals nothing, so `WHEN NULL` never matches.

`coalesce`
: The first argument that is not NULL, or NULL. Later arguments are not computed once one is found.

`nullif`
: NULL if the two values are equal, else *value1*.

`greatest`, `least`
: The largest or smallest of the values, NULLs left out; NULL only if all are NULL.

`error_on_null`
: The value, or error 22004 if it is NULL (PostgreSQL 19).

## Remarks

- `CASE` computes only the branch it takes: `CASE WHEN x = 0 THEN 0 ELSE 1 / x END` does not divide by zero.
- The results of `CASE`, and the arguments of `coalesce`, `greatest` and `least`, are converted to one type (see
  [type conversion](type-conversion.md)). Types that cannot meet (a number and a boolean) are 42804. `greatest` and
  `least` of enum values go by the list's order (see [enum types](data-types-enum.md)).

## Differences from PostgreSQL

None known.

## Examples

<!--setup: postgresql
CREATE TABLE stock (item text, qty int, reorder_at int, nickname text);
INSERT INTO stock VALUES ('pen', 0, 10, NULL), ('ink', 5, 10, 'blue'), ('pad', 50, NULL, NULL);
-->

The examples use this table:

```sql
CREATE TABLE stock (item text, qty int, reorder_at int, nickname text);
INSERT INTO stock VALUES ('pen', 0, 10, NULL), ('ink', 5, 10, 'blue'), ('pad', 50, NULL, NULL);
```

### A. CASE with conditions

<!-- example: postgresql -->
```sql
SELECT item, CASE WHEN qty = 0 THEN 'out' WHEN qty < reorder_at THEN 'low' ELSE 'ok' END AS state
FROM stock ORDER BY item;
```

```text
 item | state
------+-------
 ink  | low
 pad  | ok
 pen  | out
(3 rows)
```

### B. CASE with values

<!-- example: postgresql -->
```sql
SELECT item, CASE item WHEN 'pen' THEN 'writing' WHEN 'ink' THEN 'writing' END AS kind FROM stock ORDER BY item;
```

```text
 item |  kind
------+---------
 ink  | writing
 pad  |
 pen  | writing
(3 rows)
```

### C. coalesce and nullif

<!-- example: postgresql -->
```sql
SELECT item, coalesce(nickname, item, 'none') AS shown, coalesce(reorder_at, 0) AS reorder,
       100 / nullif(qty, 0) AS per_unit FROM stock ORDER BY item;
```

```text
 item | shown | reorder | per_unit
------+-------+---------+----------
 ink  | blue  |      10 |       20
 pad  | pad   |       0 |        2
 pen  | pen   |      10 |
(3 rows)
```

### D. greatest and least

<!-- example: postgresql -->
```sql
SELECT greatest(3, 7, 5) AS g, least(3, 7, 5) AS l, greatest(1, NULL, 2) AS g_null, least('b', 'a', 'c') AS l_text,
       greatest(DATE '2026-01-01', DATE '2026-03-01') AS g_date;
```

```text
 g | l | g_null | l_text |   g_date
---+---+--------+--------+------------
 7 | 3 |      2 | a      | 2026-03-01
(1 row)
```

### E. CASE computes one branch

<!-- example: postgresql -->
```sql
SELECT item, CASE WHEN qty = 0 THEN NULL ELSE 100 / qty END AS ratio FROM stock ORDER BY item;
```

```text
 item | ratio
------+-------
 ink  |    20
 pad  |     2
 pen  |
(3 rows)
```

### F. error_on_null

<!-- example: postgresql -->
```sql
SELECT error_on_null(qty) AS qty FROM stock WHERE item = 'pen';
SELECT error_on_null(reorder_at) FROM stock WHERE item = 'pad';
```

```text
 qty
-----
   0
(1 row)

ERROR:  null value not allowed
```

### G. Types that cannot meet

<!-- example: postgresql -->
```sql
SELECT CASE WHEN false THEN 1 ELSE false END;
SELECT coalesce(1, true);
SELECT greatest(1, true);
SELECT coalesce(qty, 'a') FROM stock;
```

```text
ERROR:  CASE types boolean and integer cannot be matched
ERROR:  COALESCE types integer and boolean cannot be matched
ERROR:  GREATEST types integer and boolean cannot be matched
ERROR:  invalid input syntax for type integer: "a"
```

## See also

[Type conversion](type-conversion.md) · [Operators](operators.md) · [SELECT](select.md)
