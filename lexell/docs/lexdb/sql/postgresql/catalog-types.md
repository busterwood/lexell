# Catalog: types

`pg_type`, `pg_enum`, `pg_collation`, `pg_am` and `pg_opclass`.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
SELECT ... FROM [ pg_catalog. ] pg_type
SELECT ... FROM [ pg_catalog. ] pg_enum
SELECT ... FROM [ pg_catalog. ] pg_collation
SELECT ... FROM [ pg_catalog. ] pg_am
SELECT ... FROM [ pg_catalog. ] pg_opclass
SELECT ... FROM information_schema.domains
```

## Views

Each relation has all of PostgreSQL 18's columns. The columns below are the ones lexdb fills in; the others are
NULL, zero, false or empty.

`pg_type`: one row per built-in type and per enum type
: `oid` (PostgreSQL's oids for the built-in types: 23 `int4`, 25 `text` ...), `typname`, `typnamespace`,
  `typowner`, `typlen`, `typbyval`, `typtype` (`b` base, `e` enum, `p` pseudo), `typcategory`, `typispreferred`,
  `typisdefined`, `typdelim`, `typelem`, `typarray`, `typinput`, `typoutput`, `typalign`, `typstorage`,
  `typtypmod`, `typcollation`.

`pg_enum`: one row per label of an enum type
: `oid`, `enumtypid`, `enumsortorder` (1, 2 ... in the list's order; after `ADD VALUE ... BEFORE` the labels are numbered again),
  `enumlabel`.

`pg_collation`: three rows
: `default`, `C` and `POSIX`, with `oid`, `collname`, `collnamespace`, `collprovider`, `collisdeterministic`,
  `collencoding`, `collcollate`, `collctype`.

`pg_am`: three rows
: `heap` (2), `btree` (403) and `hash` (405), with `amname`, `amhandler`, `amtype`.

`pg_opclass`
: No rows.

`information_schema.domains`: one row per domain
: `domain_catalog`, `domain_schema`, `domain_name`, `data_type` and PostgreSQL's other columns. lexdb has no
  `CREATE DOMAIN`, so the rows are the five domains of `information_schema` itself (`cardinal_number`,
  `character_data`, `sql_identifier`, `time_stamp`, `yes_or_no`), as in PostgreSQL.

## Remarks

- Clients and drivers read `pg_type` to map type oids to names; `format_type` and the `regtype` cast do the same in
  SQL.
- psql's `\dT` lists the user's types.

## Differences from PostgreSQL

- `pg_type` has about sixty rows: the types lexdb has and the pseudo-types clients ask for, not PostgreSQL's
  several hundred. Tables have no row types, and enum types no array types (`typarray` is 0).
- `typreceive` and `typsend` are `-` for most types: lexdb sends results as text.
- Only the `C` collation exists (`default` and `POSIX` are the same); `COLLATE` is read and ignored.
- After `ALTER TYPE ... ADD VALUE ... BEFORE`, `enumsortorder` is renumbered 1, 2, 3 (PostgreSQL gives the new
  label a fraction, such as 1.5).
- The `oid` column is sent as text, so psql aligns it to the left.
- `pg_am` lists `hash`, but an index `USING hash` is refused (0A000). `pg_opclass` is empty.

## Examples

### A. Built-in types

<!-- example: postgresql -->
```sql
SELECT oid, typname, typlen, typtype, typcategory, typarray FROM pg_type
WHERE typname IN ('int4', 'int8', 'numeric', 'text', 'bool', 'date', 'timestamptz', 'uuid', 'bytea') ORDER BY oid;
SELECT count(*) > 50 AS many FROM pg_type;
```

```text
 oid  |   typname   | typlen | typtype | typcategory | typarray
------+-------------+--------+---------+-------------+----------
 16   | bool        |      1 | b       | B           | 1000
 17   | bytea       |     -1 | b       | U           | 1001
 20   | int8        |      8 | b       | N           | 1016
 23   | int4        |      4 | b       | N           | 1007
 25   | text        |     -1 | b       | S           | 1009
 1082 | date        |      4 | b       | D           | 1182
 1184 | timestamptz |      8 | b       | D           | 1185
 1700 | numeric     |     -1 | b       | N           | 1231
 2950 | uuid        |     16 | b       | U           | 2951
(9 rows)

 many
------
 t
(1 row)
```

### B. Enum types and their labels

<!-- example: postgresql -->
```sql
CREATE TYPE mood AS ENUM ('sad', 'happy');
ALTER TYPE mood ADD VALUE 'ok' BEFORE 'happy';
SELECT t.typname, t.typtype, e.enumlabel, e.enumsortorder FROM pg_type t JOIN pg_enum e ON e.enumtypid = t.oid
ORDER BY e.enumsortorder;
```

```text
CREATE TYPE
ALTER TYPE
 typname | typtype | enumlabel | enumsortorder
---------+---------+-----------+---------------
 mood    | e       | sad       |             1
 mood    | e       | ok        |             2
 mood    | e       | happy     |             3
(3 rows)
```

### C. Collations and access methods

<!-- example: postgresql -->
```sql
SELECT collname, collprovider, collcollate FROM pg_collation ORDER BY oid;
SELECT amname, amtype FROM pg_am ORDER BY oid;
```

```text
 collname | collprovider | collcollate
----------+--------------+-------------
 default  | d            |
 C        | c            | C
 POSIX    | c            | POSIX
(3 rows)

 amname | amtype
--------+--------
 heap   | t
 btree  | i
 hash   | i
(3 rows)
```

### D. psql's list of types

<!-- example: postgresql -->
```sql
\dT
```

```text
     List of data types
 Schema | Name | Description
--------+------+-------------
 public | mood |
(1 row)
```

### E. Domains

<!-- example: postgresql -->
```sql
SELECT domain_schema, domain_name, data_type FROM information_schema.domains ORDER BY domain_name;
```

```text
   domain_schema    |   domain_name   |        data_type
--------------------+-----------------+--------------------------
 information_schema | cardinal_number | integer
 information_schema | character_data  | character varying
 information_schema | sql_identifier  | name
 information_schema | time_stamp      | timestamp with time zone
 information_schema | yes_or_no       | character varying
(5 rows)
```

## See also

[Enum types](data-types-enum.md) · [System types](data-types-system.md) · [CREATE TYPE](create-type.md) ·
[Catalog functions](functions-catalog.md)
