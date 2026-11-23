# Type conversion

Casts, typed constants, and how lexdb picks the type of an expression whose parts differ.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
CAST ( expression AS type )
expression :: type
type_keyword 'string'

type_keyword:
    DATE | TIME | TIMESTAMP | TIMESTAMPTZ | TIMESTAMP WITH TIME ZONE | TIMESTAMP WITHOUT TIME ZONE | INTERVAL
```

## Arguments

*expression*
: The value to convert.

*type*
: Any type lexdb has, with its modifiers (`numeric(10,2)`, `varchar(5)`, `int[]`), optionally qualified with
  `pg_catalog.`.

*type_keyword* `'string'`
: A constant of a date or time type, read from the string.

## Remarks

- `CAST (x AS t)` and `x::t` are the same. `::` binds tighter than any operator: `-2.5::int` is `-(2.5::int)`.
- A string constant has no type of its own until it meets one: in `id = '42'`, `'42'` is read as the column's
  type, and in `'1' + 1` as an integer.
- In arithmetic and comparison, integers widen to `bigint`, then `numeric`, then `double precision`, whichever
  side needs it.
- The branches of `CASE`, the arguments of `coalesce`, `greatest` and `least`, the rows of `VALUES` and the arms of
  `UNION` are converted to one common type, as in PostgreSQL. In `VALUES`, types that cannot meet (`integer` and
  `boolean`) are 42804.
- On `INSERT` and `UPDATE` a value is converted to its column's type as an assignment: a number is rounded to the
  column's scale, and text too long for `varchar(n)` is 22001.
- Every type casts to and from `text`. Text that does not read as the target type is 22P02 (or 22007, 22008 for
  dates and times).
- `||` with a non-text operand converts it to text: `1 || 'a'` is `1a`.

## Differences from PostgreSQL

- Typed constants are taken only for the date and time types. `text '1'`, `int '42'`, `numeric '1.5'`, `bool 'yes'`,
  `uuid '...'` and `bytea '...'` are syntax errors; use a cast (`'42'::int`).
- Comparing a number with text that is not a number gives `operator does not exist: 1 compared with a` (42883);
  PostgreSQL reads the text as a number and gives 22P02.
- `CASE`, `coalesce` and `UNION` do not check that their types can meet: `CASE WHEN false THEN 1 ELSE false END`
  gives `f`, and `SELECT 1 UNION SELECT true` gives the rows `1` and `t` (PostgreSQL: 42804).
- Bit-string constants (`B'101'`, `X'1F'`) are syntax errors; there is no `bit` type.
- A cast's result column is sometimes named after the source type, or `?column?`, where PostgreSQL uses the target
  type's name; give it an alias.

## Examples

### A. CAST and ::

<!-- example: postgresql -->
```sql
SELECT CAST(42 AS text) AS a, 42::text AS b, '2026-01-01'::date AS c, 3.7::int AS d, '42'::int + 1 AS e;
```

```text
 a  | b  |     c      | d | e
----+----+------------+---+----
 42 | 42 | 2026-01-01 | 4 | 43
(1 row)
```

### B. Typed constants

<!-- example: postgresql -->
```sql
SELECT DATE '2026-03-01' AS d, TIMESTAMP WITH TIME ZONE '2026-03-01 10:00+00' AS tstz, INTERVAL '90 minutes' AS i;
```

```text
     d      |          tstz          |    i
------------+------------------------+----------
 2026-03-01 | 2026-03-01 10:00:00+00 | 01:30:00
(1 row)
```

### C. A string takes the other side's type

<!-- example: postgresql -->
```sql
CREATE TABLE item (id int PRIMARY KEY, made date);
INSERT INTO item VALUES (1, '2026-01-15'), (2, '2026-02-15');
SELECT id FROM item WHERE id = '2' OR made < '2026-02-01' ORDER BY id;
SELECT 1 = '1' AS eq, 1 || 'a' AS cat;
```

```text
CREATE TABLE
INSERT 0 2
 id
----
  1
  2
(2 rows)

 eq | cat
----+-----
 t  | 1a
(1 row)
```

### D. The common type of mixed values

<!-- example: postgresql -->
```sql
SELECT pg_typeof(1 + 1.5) AS sum, pg_typeof(CASE WHEN true THEN 1 ELSE 2.5 END) AS "case",
       pg_typeof(coalesce(1, 2::bigint)) AS "coalesce", pg_typeof(1::real + 1::numeric) AS real_num;
SELECT x, pg_typeof(x) FROM (SELECT 1 AS x UNION ALL SELECT 2.5) u ORDER BY x;
```

```text
   sum   |  case   | coalesce |     real_num
---------+---------+----------+------------------
 numeric | numeric | bigint   | double precision
(1 row)

  x  | pg_typeof
-----+-----------
   1 | numeric
 2.5 | numeric
(2 rows)
```

### E. Dates and times

<!-- example: postgresql -->
```sql
SELECT DATE '2026-01-01'::timestamp AS ts, TIMESTAMP '2026-01-01 10:00'::date AS d,
       TIMESTAMPTZ '2026-01-01 10:00+00'::date AS d2, '10:00'::time AS t;
```

```text
         ts          |     d      |     d2     |    t
---------------------+------------+------------+----------
 2026-01-01 00:00:00 | 2026-01-01 | 2026-01-01 | 10:00:00
(1 row)
```

### F. Errors

<!-- example: postgresql -->
```sql
SELECT int '42';
SELECT 'abc'::int;
SELECT 1 = 'a';
VALUES (1), (true);
```

```text
ERROR:  syntax error at or near "42"
ERROR:  invalid input syntax for type integer: "abc"
ERROR:  operator does not exist: 1 compared with a
ERROR:  column is of type integer but the expression is of another type
```

## See also

[Numeric types](data-types-numeric.md) · [Character types](data-types-character.md) ·
[Date and time types](data-types-datetime.md) · [Operators](operators.md)
