# Boolean type

`boolean`: true, false, or unknown (NULL).

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
boolean | bool
```

## Remarks

- The constants are `TRUE` and `FALSE`. As text, `true`, `yes`, `on`, `1` and their prefixes (`t`, `y`) are true;
  `false`, `no`, `off`, `0` (`f`, `n`) are false. Case and surrounding spaces do not matter. Other text is 22P02.
- psql shows the values as `t` and `f`; cast to text they are `true` and `false`.
- `AND`, `OR` and `NOT` follow three-valued logic: `true AND NULL` is NULL, `false AND NULL` is false.
- `IS TRUE`, `IS FALSE`, `IS UNKNOWN` and their `NOT` forms never give NULL.
- An integer casts to `boolean` (0 is false, anything else true), and a `boolean` to an integer (1 or 0).
- `false` sorts before `true`. `bool_and`, `bool_or` and `every` are the aggregates.

## Differences from PostgreSQL

None known.

## Examples

### A. Constants and text

<!-- example: postgresql -->
```sql
SELECT true AS a, 'yes'::bool AS b, 'off'::bool AS c, ' TRUE '::bool AS d, 'n'::bool AS e, true::text AS f;
```

```text
 a | b | c | d | e |  f
---+---+---+---+---+------
 t | t | f | t | f | true
(1 row)
```

### B. A boolean column

<!-- example: postgresql -->
```sql
CREATE TABLE task (name text, done boolean DEFAULT false);
INSERT INTO task VALUES ('write', true), ('check', false), ('ship', NULL);
SELECT name FROM task WHERE done;
SELECT name, done IS NOT TRUE AS open FROM task ORDER BY name;
```

```text
CREATE TABLE
INSERT 0 3
 name
-------
 write
(1 row)

 name  | open
-------+------
 check | t
 ship  | t
 write | f
(3 rows)
```

### C. Three-valued logic

<!-- example: postgresql -->
```sql
SELECT true AND NULL AS a, false AND NULL AS b, true OR NULL AS c, NOT NULL::bool AS d, NULL::bool IS UNKNOWN AS e;
```

```text
 a | b | c | d | e
---+---+---+---+---
   | f | t |   | t
(1 row)
```

### D. Integers and aggregates

<!-- example: postgresql -->
```sql
SELECT 1::boolean AS one, 0::bool AS zero, true::int AS t;
SELECT bool_and(done) AS all_done, bool_or(done) AS any_done, count(*) FILTER (WHERE done) AS n_done FROM task;
```

```text
 one | zero | t
-----+------+---
 t   | f    | 1
(1 row)

 all_done | any_done | n_done
----------+----------+--------
 f        | t        |      1
(1 row)
```

### E. Errors

<!-- example: postgresql -->
```sql
SELECT 'maybe'::bool;
```

```text
ERROR:  invalid input syntax for type boolean: "maybe"
```

## See also

[Aggregate functions](functions-aggregate.md) · [Operators](operators.md) · [Type conversion](type-conversion.md)
