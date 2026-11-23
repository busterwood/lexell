# CREATE TYPE

Makes an enum type: a type whose values are a fixed list of labels, in order.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
CREATE TYPE name AS ENUM ( [ 'label' [, ...] ] )
```

## Arguments

*name*
: The type's name, optionally schema-qualified.

*label*
: A value of the type, as a string. Labels are compared by their place in the list, not as text.
  Each label may appear once.

## Remarks

- A column of the type takes only its labels: another string is 22P02 (`invalid input value for enum mood:
  "angry"`).
- Values sort and compare in the list's order, so `ORDER BY` and `<` follow it.
- A value is cast to text with `::text`.
- `pg_type` (`typtype` `e`) and `pg_enum` list the types and their labels.
- `CREATE TYPE` is transactional.

## Differences from PostgreSQL

- Only enums: composite types (`AS (x int, y int)`), ranges, base types and shells are refused (0A000, `lexdb: CREATE
  TYPE supports AS ENUM only`). There are no domains.
- An array of an enum type (`mood[]`) is refused (0A000).
- An enum value's type, as `pg_typeof` gives it and a client sees it, is `text`; the column's type in the catalog
  is the enum (`format_type` gives `mood`). `'mood'::regtype` is 42704.
- `enum_range` does not exist (42883).

## Examples

### A. An enum and a column of it

<!-- example: postgresql -->
```sql
CREATE TYPE mood AS ENUM ('sad', 'ok', 'happy');
CREATE TABLE person (name text, current mood);
INSERT INTO person VALUES ('ann', 'happy'), ('bob', 'sad'), ('cy', 'ok');
SELECT * FROM person ORDER BY current;
SELECT name FROM person WHERE current > 'ok';
```

```text
CREATE TYPE
CREATE TABLE
INSERT 0 3
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

### B. Labels in the catalog

<!-- example: postgresql -->
```sql
SELECT t.typname, e.enumlabel, e.enumsortorder
FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid
ORDER BY e.enumsortorder;
SELECT format_type(atttypid, atttypmod) FROM pg_attribute WHERE attrelid = 'person'::regclass AND attname = 'current';
```

```text
 typname | enumlabel | enumsortorder
---------+-----------+---------------
 mood    | sad       |             1
 mood    | ok        |             2
 mood    | happy     |             3
(3 rows)

 format_type
-------------
 mood
(1 row)
```

### C. Errors

<!-- example: postgresql -->
```sql
INSERT INTO person VALUES ('dee', 'angry');
CREATE TYPE mood AS ENUM ('x');
CREATE TYPE point2 AS (x int, y int);
CREATE TABLE history (moods mood[]);
```

```text
ERROR:  invalid input value for enum mood: "angry"
ERROR:  type "mood" already exists
ERROR:  lexdb: CREATE TYPE supports AS ENUM only
ERROR:  lexdb: arrays of enum types are not supported
```

## See also

[ALTER TYPE](alter-type.md) · [DROP TYPE](drop-type.md) · [CREATE TABLE](create-table.md)
