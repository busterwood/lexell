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
- Values sort in the order of the list, not as text: `ORDER BY` follows it, and so do comparisons in `WHERE`
  (`current > 'ok'`, `BETWEEN`).
- A value casts to `text` with `::text`, and a string to the type with `::name`.
- `pg_type` (`typtype = 'e'`) and `pg_enum` list the types and labels; `format_type` names the column's type.
- See [CREATE TYPE](create-type.md), [ALTER TYPE](alter-type.md) and [DROP TYPE](drop-type.md).

## Differences from PostgreSQL

- A value comes out typed as `text`: `pg_typeof('ok'::mood)` is `text`, and clients see a text column.
- A cast does not check the label: `'angry'::mood` gives `angry`. Storing it in a column is 22P02, as in
  PostgreSQL.
- Outside `WHERE` and `ORDER BY`, enum values compare as text. In the select list, `current < 'happy'` is false
  for `ok`, and `'ok'::mood < 'happy'::mood` is false. `min`, `max`, `greatest` and `least` compare as text too:
  over `happy` and `sad` (list `sad`, `ok`, `happy`), `min` is `happy` and `max` is `sad`.
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

### C. Comparisons outside WHERE compare as text

The same comparison gives the list's answer in `WHERE` and the text answer in the select list; `min` and `max`
compare as text.

<!-- example: postgresql -->
```sql
SELECT name FROM person WHERE current < 'happy' ORDER BY name;
SELECT name, current, current < 'happy' AS less FROM person ORDER BY current;
SELECT min(current), max(current) FROM person;
```

```text
 name
------
 bob
 cy
(2 rows)

 name | current | less
------+---------+------
 bob  | sad     | f
 cy   | ok      | f
 ann  | happy   | f
(3 rows)

  min  | max
-------+-----
 happy | sad
(1 row)
```

### D. The labels in the catalog

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

### E. Errors

<!-- example: postgresql -->
```sql
INSERT INTO person VALUES ('dan', 'angry');
SELECT enum_range(NULL::mood);
```

```text
ERROR:  invalid input value for enum mood: "angry"
ERROR:  function enum_range with 1 arguments does not exist
```

## See also

[CREATE TYPE](create-type.md) · [ALTER TYPE](alter-type.md) · [DROP TYPE](drop-type.md) ·
[Catalog: types](catalog-types.md)
