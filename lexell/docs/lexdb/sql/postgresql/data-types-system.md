# System types

`oid`, the `reg` types that name catalog objects, and the vector types of the catalog.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
oid
regclass
regtype
regnamespace
regproc
regprocedure
regrole
int2vector
oidvector
```

## Arguments

`oid`
: An object identifier: an unsigned 4-byte integer that the catalog tables use as keys (`pg_class.oid`).

`regclass`
: A relation (table, view, index, sequence). `'name'::regclass` looks the name up on the search path, or in the
  schema it names (`'app.t'`), and gives its oid; a `regclass` shows as the name.

`regtype`
: A type, by any of its names (`'int4'`, `'integer'`, `'character varying'`, `'text[]'`); it shows as the
  type's SQL name.

`regnamespace`
: A schema.

`regproc`, `regprocedure`
: A function, by name, or by name and argument types (`'add1(int)'`).

`regrole`
: A role.

`int2vector`, `oidvector`
: Lists of numbers in the catalog: `pg_index.indkey` (column numbers), `pg_proc.proargtypes` (type oids).

## Remarks

- The `reg` types are for catalog queries: `WHERE attrelid = 'person'::regclass` saves a join with `pg_class`,
  and `oid::regclass` turns an oid into a name.
- A name that does not exist is an error: 42P01 for a relation, 42704 for a type, 42883 for a function.
- An integer casts to `oid` and to each `reg` type, and back.

## Differences from PostgreSQL

- `pg_typeof` of an `oid` or a `reg` value says `text`, and clients see these values as `text` or integers.
- `regrole` is looked up as a function: `'alice'::regrole` is 42883 `function "alice" does not exist`, and
  `oid::regrole` shows the number. Use `pg_roles` or `pg_get_userbyid`.
- `regproc` and `regprocedure` find only the user's functions: `pg_proc` has no rows for built-in functions, so
  `'now'::regproc` is 42883.
- A cast to `int2vector` or `oidvector` gives an array: `'1 2'::int2vector` is `{1,2}` (PostgreSQL: `1 2`).
- A `regprocedure` shows the function's name without its argument types (`add1`; PostgreSQL: `add1(integer)`).
- `'enum_type'::regtype` is 42704 for an enum type.

## Examples

<!--setup: postgresql
CREATE TABLE person (id int PRIMARY KEY, name text);
CREATE FUNCTION add1(x int) RETURNS int LANGUAGE sql AS 'SELECT x + 1';
-->

The examples use this table and function:

```sql
CREATE TABLE person (id int PRIMARY KEY, name text);
CREATE FUNCTION add1(x int) RETURNS int LANGUAGE sql AS 'SELECT x + 1';
```

### A. regclass in catalog queries

<!-- example: postgresql -->
```sql
SELECT attname, format_type(atttypid, atttypmod) AS type
FROM pg_attribute WHERE attrelid = 'person'::regclass AND attnum > 0 ORDER BY attnum;
SELECT 'pg_class'::regclass::oid AS pg_class_oid, 1259::regclass AS name;
```

```text
 attname |  type
---------+---------
 id      | integer
 name    | text
(2 rows)

 pg_class_oid |   name
--------------+----------
         1259 | pg_class
(1 row)
```

### B. From an oid to a name

<!-- example: postgresql -->
```sql
SELECT indexrelid::regclass AS index, indrelid::regclass AS "table", indkey FROM pg_index
WHERE indrelid = 'person'::regclass;
```

```text
    index    | table  | indkey
-------------+--------+--------
 person_pkey | person | 1
(1 row)
```

### C. regtype

<!-- example: postgresql -->
```sql
SELECT 'int4'::regtype AS a, 'varchar'::regtype AS b, 'text[]'::regtype AS c, 'timestamptz'::regtype AS d,
       23::regtype AS e;
```

```text
    a    |         b         |   c    |            d             |    e
---------+-------------------+--------+--------------------------+---------
 integer | character varying | text[] | timestamp with time zone | integer
(1 row)
```

### D. regnamespace and regproc

<!-- example: postgresql -->
```sql
SELECT 'public'::regnamespace AS schema, 'add1'::regproc AS func, 'add1(int)'::regprocedure AS func_args;
SELECT proname, proargtypes FROM pg_proc WHERE oid = 'add1'::regproc;
```

```text
 schema | func | func_args
--------+------+-----------
 public | add1 | add1
(1 row)

 proname | proargtypes
---------+-------------
 add1    | 23
(1 row)
```

### E. Errors

<!-- example: postgresql -->
```sql
SELECT 'nosuch'::regclass;
SELECT 'nosuch'::regtype;
SELECT 'now'::regproc;
```

```text
ERROR:  relation "nosuch" does not exist
ERROR:  type "nosuch" does not exist
ERROR:  function "now" does not exist
```

## See also

[Catalog functions](functions-catalog.md) · [Type conversion](type-conversion.md) ·
[Catalog: tables and columns](catalog-tables.md)
