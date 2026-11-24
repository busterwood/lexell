# Enum types

A type whose values are a fixed list of labels, made with `CREATE TYPE ... AS ENUM`.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
CREATE TYPE name AS ENUM ( 'label' [, ...] )
ALTER TYPE name ADD VALUE [ IF NOT EXISTS ] 'label' [ { BEFORE | AFTER } 'label' ]
```

## Remarks

- A column of an enum type takes only its labels; another string is 22P02 (`invalid input value for enum`).
- Values sort in the order of the list, not as text. `ORDER BY`, `GROUP BY` and the comparisons `<`, `<=`, `>`, `>=`
  and `BETWEEN` follow it wherever they stand in a `SELECT` (select list, `WHERE`, `HAVING`, `CASE`, window
  keys), and so do `min`, `max`, `greatest` and `least`.
- A string that is not a label is 22P02 wherever it meets an enum value: in a cast (`'angry'::mood`), a comparison
  (`current = 'angry'`) or an `INSERT`.
- A value casts to `text` with `::text`, and a string to the type with `::name`.
- `pg_type` (`typtype = 'e'`) and `pg_enum` list the types and labels; `format_type` names the column's type.
- See [CREATE TYPE](create-type.md), [ALTER TYPE](alter-type.md) and [DROP TYPE](drop-type.md).

## Differences from PostgreSQL

- A value comes out typed as `text`: `pg_typeof('ok'::mood)` is `text`, and clients see a text column.
- Enum values are still ordered as text in four places: `min` and `max` as window functions (`min(current) OVER ()`), the
  `ORDER BY` inside an aggregate (`array_agg(name ORDER BY current)`), the `ORDER BY` of a `UNION`, `INTERSECT` or
  `EXCEPT`, and arrays: `ARRAY['ok'::mood]` is an array of text.
- `enum_range`, `enum_first` and `enum_last` do not exist (42883); `'mood'::regtype` is 42704.
- Arrays of enum types are refused (0A000).

## Examples

<!--setup: postgresql
CREATE TYPE mood AS ENUM ('sad', 'ok', 'happy');
CREATE TABLE person (name text, current mood);
INSERT INTO person VALUES ('ann', 'happy'), ('bob', 'sad'), ('cy', 'ok');
-->

The examples use this type and table:

```sql
CREATE TYPE mood AS ENUM ('sad', 'ok', 'happy');
CREATE TABLE person (name text, current mood);
INSERT INTO person VALUES ('ann', 'happy'), ('bob', 'sad'), ('cy', 'ok');
```

### A. Order follows the list

<!-- example: postgresql -->
```sql
SELECT name, current FROM person ORDER BY current;
SELECT name FROM person WHERE current > 'ok';
```

```text
 name | current
------+---------
 bob  | sad
 cy   | ok
 ann  | happy
(3 rows)

 name
------
 ann
(1 row)
```

### B. Casts

<!-- example: postgresql -->
```sql
SELECT current::text || '!' AS shout, pg_typeof(current) AS type FROM person WHERE name = 'ann';
```

```text
 shout  | type
--------+------
 happy! | text
(1 row)
```

### C. Comparisons anywhere in a query

The comparison gives the list's answer in `WHERE` and in the select list; `min`, `max`, `greatest` and `least` go
by the list too.

<!-- example: postgresql -->
```sql
SELECT name FROM person WHERE current < 'happy' ORDER BY name;
SELECT name, current, current < 'happy' AS less FROM person ORDER BY current;
SELECT min(current), max(current), greatest('sad'::mood, 'ok'::mood) AS greater FROM person;
```

```text
 name
------
 bob
 cy
(2 rows)

 name | current | less
------+---------+------
 bob  | sad     | t
 cy   | ok      | t
 ann  | happy   | f
(3 rows)

 min |  max  | greater
-----+-------+---------
 sad | happy | ok
(1 row)
```

### D. Where the list is not followed

An aggregate's own `ORDER BY` sorts the labels as text (the list's order would give `{bob,cy,ann}`), and so does a set
operation's. A window `min` takes the alphabetically first label (`happy`, where the list's first is `sad`).

<!-- example: postgresql -->
```sql
SELECT array_agg(name ORDER BY current) AS by_list FROM person;
SELECT name, min(current) OVER () AS first_label FROM person ORDER BY name;
```

```text
   by_list
--------------
 {ann,cy,bob}
(1 row)

 name | first_label
------+-------------
 ann  | happy
 bob  | happy
 cy   | happy
(3 rows)
```

### E. The labels in the catalog

<!-- example: postgresql -->
```sql
SELECT e.enumlabel, e.enumsortorder FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid
WHERE t.typname = 'mood' ORDER BY e.enumsortorder;
```

```text
 enumlabel | enumsortorder
-----------+---------------
 sad       |             1
 ok        |             2
 happy     |             3
(3 rows)
```

### F. Errors

<!-- example: postgresql -->
```sql
INSERT INTO person VALUES ('dan', 'angry');
SELECT 'angry'::mood;
SELECT name FROM person WHERE current = 'angry';
SELECT enum_range(NULL::mood);
```

```text
ERROR:  invalid input value for enum mood: "angry"
ERROR:  invalid input value for enum mood: "angry"
ERROR:  invalid input value for enum mood: "angry"
ERROR:  function enum_range with 1 arguments does not exist
```

## See also

[CREATE TYPE](create-type.md) · [ALTER TYPE](alter-type.md) · [DROP TYPE](drop-type.md) ·
[Catalog: types](catalog-types.md)
