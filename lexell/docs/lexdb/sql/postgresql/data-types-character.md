# Character types

Text of any length, text with a length limit, blank-padded text, and the catalog's `name` and `"char"`.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
text
character varying [ ( n ) ] | varchar [ ( n ) ]
character [ ( n ) ] | char [ ( n ) ] | bpchar [ ( n ) ]
name
"char"
```

## Arguments

`text`
: Text of any length.

`varchar(n)`
: Text of at most *n* characters. Without *n*, any length, like `text`.

`char(n)`, `bpchar(n)`
: Text of exactly *n* characters, padded with spaces. `char` alone is `char(1)`; `bpchar` alone has no length.
  *n* may be up to 10485760.

`name`
: The catalog's type for names of objects (`pg_class.relname`).

`"char"`
: The catalog's one-character type (`pg_class.relkind`). The quotes are part of the name.

## Remarks

- Text is UTF-8. `length` counts characters, `octet_length` bytes.
- Storing a value longer than a column's `varchar(n)` or `char(n)` is 22001. A cast (`'abcdef'::varchar(3)`)
  cuts the value to *n* characters instead, as in PostgreSQL.
- A `char(n)` value's trailing spaces do not count: `length`, comparison and `||` ignore them, and a value whose
  extra characters are all spaces fits the column.
- Text compares byte by byte, as in PostgreSQL's `C` collation: `'B' < 'a'`. `upper`, `lower` and `initcap`
  change only the ASCII letters, as in the `C` locale. `COLLATE` is read and ignored.
- String constants: `'it''s'` doubles a quote; `E'a\tb'` takes backslash escapes; `$$...$$` and `$tag$...$tag$`
  need no doubling.

## Differences from PostgreSQL

- A value whose extra characters are all spaces does not fit a `varchar(n)` column: `'abc   '` into `varchar(3)`
  is 22001 (PostgreSQL cuts the spaces). For `char(n)` it fits, as in PostgreSQL.
- `"char"` keeps the whole string (`'abc'::"char"` is `abc`; PostgreSQL keeps `a`), and `name` is not cut to 63
  bytes.
- `pg_typeof` of a `name` or a `"char"` value says `text`.
- `varchar(0)` is accepted (PostgreSQL: 22023).
- `COLLATE` is read and ignored; every comparison is by bytes. There are no other collations and no
  case-insensitive ones.
- Unicode escape strings (`U&'\0041'`) are not read.

## Examples

### A. The three kinds of text

<!-- example: postgresql -->
```sql
CREATE TABLE label (t text, v varchar(5), c char(5));
INSERT INTO label VALUES ('ab', 'ab', 'ab');
SELECT t || '|' AS t, v || '|' AS v, c || '|' AS c, length(c) AS len_c, octet_length(c) AS bytes_c FROM label;
```

```text
CREATE TABLE
INSERT 0 1
  t  |  v  |  c  | len_c | bytes_c
-----+-----+-----+-------+---------
 ab| | ab| | ab| |     2 |       5
(1 row)
```

### B. Too long for the column

A cast cuts the value; storing it is an error.

<!-- example: postgresql -->
```sql
SELECT 'abcdef'::varchar(3) AS v, 'abcdef'::char(3) AS c;
INSERT INTO label (v) VALUES ('abcdefg');
INSERT INTO label (c) VALUES ('abcdefg');
```

```text
  v  |  c
-----+-----
 abc | abc
(1 row)

ERROR:  value too long for type character varying(5)
ERROR:  value too long for type character(5)
```

### C. Trailing spaces in char(n)

<!-- example: postgresql -->
```sql
INSERT INTO label (c) VALUES ('xyz     ');
SELECT 'ab'::char(5) = 'ab   '::char(5) AS same, c || '|' AS c FROM label WHERE c = 'xyz';
INSERT INTO label (v) VALUES ('abc        ');
```

```text
INSERT 0 1
 same |  c
------+------
 t    | xyz|
(1 row)

ERROR:  value too long for type character varying(5)
```

### D. Characters and bytes

<!-- example: postgresql -->
```sql
SELECT length('héllo') AS chars, octet_length('héllo') AS bytes, upper('héllo') AS up;
```

```text
 chars | bytes |  up
-------+-------+-------
     5 |     6 | HéLLO
(1 row)
```

### E. Byte order

<!-- example: postgresql -->
```sql
SELECT w FROM (VALUES ('b'), ('B'), ('a'), ('A'), ('é')) v(w) ORDER BY w;
```

```text
 w
---
 A
 B
 a
 b
 é
(5 rows)
```

### F. String constants

<!-- example: postgresql -->
```sql
SELECT 'it''s' AS doubled, E'it\'s \x41' AS escaped, $$no 'doubling'$$ AS dollar, $q$a $$ b$q$ AS tagged;
```

```text
 doubled | escaped |    dollar     | tagged
---------+---------+---------------+--------
 it's    | it's A  | no 'doubling' | a $$ b
(1 row)
```

### G. name and "char" in the catalog

<!-- example: postgresql -->
```sql
SELECT relname, relkind FROM pg_class WHERE relname = 'label';
SELECT format_type(atttypid, atttypmod) AS type FROM pg_attribute
WHERE attrelid = 'pg_class'::regclass AND attname IN ('relname', 'relkind') ORDER BY attnum;
```

```text
 relname | relkind
---------+---------
 label   | r
(1 row)

  type
--------
 name
 "char"
(2 rows)
```

## See also

[String functions](functions-string.md) · [Pattern matching](functions-pattern.md) ·
[Type conversion](type-conversion.md) · [CREATE TABLE](create-table.md)
