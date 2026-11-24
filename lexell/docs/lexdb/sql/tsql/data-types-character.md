# Character types (Transact-SQL)

Strings of single-byte and Unicode characters, and the old `text` types.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
char [ ( n ) ]
varchar [ ( n | max ) ]
text
nchar [ ( n ) ]
nvarchar [ ( n | max ) ]
ntext
sysname
```

## Arguments

`char(n)`, `varchar(n)`, `varchar(max)`
: Character strings of at most *n* characters (1 to 8000), or without a limit for `max`.

`nchar(n)`, `nvarchar(n)`, `nvarchar(max)`
: The same for Unicode strings; *n* is at most 4000. `N'text'` is a Unicode literal.

`text`, `ntext`
: Old names for `varchar(max)` and `nvarchar(max)`.

`sysname`
: `nvarchar(128)`, the type of names in the catalog.

## Remarks

- lexdb keeps every character type as UTF-8 text. `varchar` and `nvarchar` differ only in their name and in how the
  client driver sends values: a `varchar` column can hold any Unicode character, and `LEN` counts characters in
  both. `N` before a literal changes nothing.
- A value longer than the column is refused by `INSERT` and `UPDATE` with error 2628 (`value too long for type
  character varying(n)`). `CAST` and `CONVERT` cut the value to the length instead: `CAST('abcdef' AS varchar(3))`
  is `abc`.
- `char(n)` and `nchar(n)` are padded with blanks to *n* characters by every conversion to them (`CAST`, `CONVERT`, an
  `INSERT` or `UPDATE` of a column, an assignment to a variable): `'[' + CAST('ab' AS char(5)) + ']'` is `[ab   ]`.
  `LEN` leaves the blanks out.
- `+` joins strings and gives NULL when either side is NULL; `CONCAT` leaves NULLs out. A string that meets a
  number in `+` is converted to a number (`'12' + 1` is 13; `'abc' + 1` is error 245).
- The default collation is `SQL_Latin1_General_CP1_CI_AS`: comparisons, `ORDER BY`, `DISTINCT`, `GROUP BY` and
  `LIKE` ignore case, and trailing spaces do not count (`'abc' = 'abc   '`). Accents count (`'é' = 'e'` is false).
  A column or an expression may name another collation: with `COLLATE Latin1_General_CS_AS` it is case sensitive;
  with `COLLATE Latin1_General_BIN` it sorts by bytes.
- `LIKE` takes `%`, `_`, `[abc]`, `[a-c]` and `[^abc]`.
- `UPPER`, `LOWER` and the other functions are on [their own page](functions-string.md). `UPPER` and `LOWER` change
  ASCII letters only.

## Differences from SQL Server

- **A variable without a length is not limited.** `DECLARE @n varchar = 'abcdef'` keeps all six characters (SQL
  Server: `a`), and `CAST('abcdef' AS varchar)` is `abcdef` (SQL Server: up to 30 characters).
- **Assigning a long value to a variable is an error.** `DECLARE @v varchar(10) = 'abcdefghijklmnop'` is error 2628;
  SQL Server cuts the value silently. The variable stays NULL.
- Error 2628 reads `value too long for type character varying(5)`; SQL Server says `String or binary data would
  be truncated in table ..., column ...`.
- `DATALENGTH` counts two bytes for every character of every type: `DATALENGTH('ab')` is 4, and
  `DATALENGTH(CAST('ab' AS char(5)))` is 10 (SQL Server: 2 and 5).
- A binary value cast to a string gives the bytes as characters: see [Binary types](data-types-binary.md).
- The database and server collation is always `SQL_Latin1_General_CP1_CI_AS`. A collation named in `COLLATE` is
  read for its case sensitivity (`_CS_`) and binary (`_BIN`) markers only.

## Examples

### A. Fixed and variable length, and what a value too long does

<!-- example: tsql -->
```sql
CREATE TABLE s (a char(5), b varchar(5), c nchar(5), d nvarchar(5));
INSERT INTO s VALUES ('ab', 'ab', N'ab', N'ab');
SELECT '[' + a + ']' AS a, '[' + b + ']' AS b, '[' + c + ']' AS c, '[' + d + ']' AS d, LEN(a) AS len_a FROM s;
GO
INSERT INTO s (b) VALUES ('abcdef');
```

```text
(1 row affected)

a       b    c       d    len_a
------- ---- ------- ---- -----
[ab   ] [ab] [ab   ] [ab] 2

(1 row affected)

Msg 2628, Level 16, State 1, Line 1
value too long for type character varying(5)
```

### B. CAST cuts the value

<!-- example: tsql -->
```sql
SELECT CAST('abcdef' AS varchar(3)) AS cut, CAST('ab' AS char(5)) + '|' AS padded,
       CAST(N'日本語' AS nvarchar(10)) AS unicode, LEN(N'日本語') AS characters;
```

```text
cut padded unicode characters
--- ------ ------- ----------
abc ab   | 日本語     3

(1 row affected)
```

### C. Case and trailing spaces in comparisons

<!-- example: tsql -->
```sql
SELECT CASE WHEN 'abc' = 'ABC' THEN 'equal' ELSE 'different' END AS ignores_case,
       CASE WHEN 'abc' = 'abc   ' THEN 'equal' ELSE 'different' END AS ignores_trailing_spaces,
       CASE WHEN 'é' = 'e' THEN 'equal' ELSE 'different' END AS sees_accents;
```

```text
ignores_case ignores_trailing_spaces sees_accents
------------ ----------------------- ------------
equal        equal                   different

(1 row affected)
```

### D. Sorting, and the collation of a column

<!-- example: tsql -->
```sql
CREATE TABLE ct (name varchar(20));
INSERT INTO ct VALUES ('apple'), ('Banana'), ('cherry'), ('Apple');
SELECT name FROM ct ORDER BY name;
SELECT name FROM ct WHERE name = 'APPLE';
SELECT name FROM ct ORDER BY name COLLATE Latin1_General_BIN;
SELECT DISTINCT name FROM ct ORDER BY name;
GO
CREATE TABLE cc (v varchar(10) COLLATE Latin1_General_CS_AS, w varchar(10));
INSERT INTO cc VALUES ('abc', 'abc');
SELECT COUNT(*) AS case_sensitive FROM cc WHERE v = 'ABC';
SELECT COUNT(*) AS default_collation FROM cc WHERE w = 'ABC';
```

```text
(4 rows affected)

name
------
apple
Apple
Banana
cherry

(4 rows affected)

name
-----
apple
Apple

(2 rows affected)

name
------
Apple
Banana
apple
cherry

(4 rows affected)

name
------
apple
Banana
cherry

(3 rows affected)

(1 row affected)

case_sensitive
--------------
0

(1 row affected)

default_collation
-----------------
1

(1 row affected)
```

### E. NULL and the empty string

<!-- example: tsql -->
```sql
SELECT 'x' + NULL AS plus_null, CONCAT('x', NULL, 'y') AS concat, '' + 'a' AS empty, LEN('') AS len_empty,
       ISNULL(NULL, 'z') AS isnull;
```

```text
plus_null concat empty len_empty isnull
--------- ------ ----- --------- ------
NULL      xy     a     0         z

(1 row affected)
```

### F. Escapes and special characters

<!-- example: tsql -->
```sql
SELECT 'it''s' AS quote, N'unicode: ' + NCHAR(233) AS unicode, CHAR(65) + CHAR(66) AS chars,
       REPLICATE('ab', 3) AS repeated;
```

```text
quote unicode    chars repeated
----- ---------- ----- --------
it's  unicode: é AB    ababab

(1 row affected)
```

### G. Long strings

<!-- example: tsql -->
```sql
SELECT LEN(REPLICATE(CAST('a' AS varchar(max)), 9000)) AS len_max, LEN(REPLICATE('a', 9000)) AS len_plain;
```

```text
len_max len_plain
------- ---------
9000    9000

(1 row affected)
```

### H. text, ntext and sysname

<!-- example: tsql -->
```sql
DECLARE @n sysname = 'abc';
SELECT @n AS name_value;
GO
CREATE TABLE ntx (a ntext, b text);
INSERT INTO ntx VALUES (N'hello', 'world');
SELECT a, b, LEN(a) AS len_a FROM ntx;
```

```text
name_value
----------
abc

(1 row affected)

(1 row affected)

a     b     len_a
----- ----- -----
hello world 5

(1 row affected)
```

### I. Variables: the length is not applied

<!-- example: tsql -->
```sql
DECLARE @n varchar = 'abcdef';
SELECT @n AS n, CAST('abcdef' AS varchar) AS c;
GO
DECLARE @v varchar(10) = 'abcdefghijklmnop';
SELECT @v AS v;
```

```text
n      c
------ ------
abcdef abcdef

(1 row affected)

Msg 2628, Level 16, State 1, Line 1
value too long for type character varying(10)
v
----
NULL

(1 row affected)
```

### J. LIKE

<!-- example: tsql -->
```sql
SELECT CASE WHEN 'abc' LIKE 'A%' THEN 1 ELSE 0 END AS ignores_case,
       CASE WHEN 'abc' LIKE '[a-c]%' THEN 1 ELSE 0 END AS range_class,
       CASE WHEN 'a_c' LIKE 'a[_]c' THEN 1 ELSE 0 END AS escaped_underscore,
       CASE WHEN 'abd' LIKE 'ab[^c]' THEN 1 ELSE 0 END AS negated_class;
```

```text
ignores_case range_class escaped_underscore negated_class
------------ ----------- ------------------ -------------
1            1           1                  1

(1 row affected)
```

## See also

[String functions](functions-string.md), [CAST and CONVERT](functions-conversion.md),
[Binary types](data-types-binary.md), [Operators](operators.md)
