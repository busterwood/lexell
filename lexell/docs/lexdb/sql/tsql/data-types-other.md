# Other types: bit, uniqueidentifier, xml, table types (Transact-SQL)

The boolean-like `bit`, GUIDs, XML kept as text, and the types left out.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
bit
uniqueidentifier
json
xml
sql_variant
type_name                  -- a table type made by CREATE TYPE ... AS TABLE
```

## Arguments

`bit`
: 1, 0 or NULL. Any non-zero number stored or cast to `bit` becomes 1; the strings `'true'`, `'false'`, `'1'` and
  `'0'` convert too.

`uniqueidentifier`
: A 16-byte GUID, written as 36 characters (`6F9619FF-8B86-D011-B42D-00C04FC964FF`); braces are accepted.
  `NEWID()` makes a random one.

`json`
: Validated RFC 8259 JSON text (SQL Server 2025's type; sent as `nvarchar(max)` over TDS). Text that is not JSON is error 245 on `INSERT`
  and `CAST` (SQL Server: 13609). See [JSON, OPENJSON and FOR JSON](functions-json.md) and example H.

`xml`
: A column that holds XML text. lexdb keeps the text and checks nothing.

`sql_variant`
: Accepted as the type of a variable; see the differences below.

*type_name*
: A table type: see [CREATE TYPE](create-type.md).

## Remarks

- T-SQL has no boolean values: a comparison such as `1 = 1` is a condition for `WHERE`, `IF` and `CASE`, not a
  value. To return one, write `CASE WHEN ... THEN 1 ELSE 0 END` or `CAST(... AS bit)`.
- `bit` columns take `&`, `|`, `^` and `~`; `+` on two `bit` values is error 195.
- A `uniqueidentifier` compares, sorts and works as a key. It is not a number: it cannot be added to anything.
- `xml` is a string type here: `xml` values come back as the text that went in.
- Table types are described on [CREATE TYPE](create-type.md): `DECLARE @t dbo.id_list` makes a table variable and a
  procedure parameter of the type is a table-valued parameter.

## Differences from SQL Server

- `SELECT 1 = 1` is taken and returns 1 (SQL Server: error 102). Do not rely on it.
- **`xml` has no methods.** `doc.value(...)`, `query`, `nodes`, `exist`, `FOR XML` and `OPENXML` are not supported
  (`doc.value(...)` is error 4121), and no XML schema checks run.
- **`sql_variant`** is accepted in a declaration (`DECLARE @v sql_variant = 1`) but behaves as a plain value;
  `SQL_VARIANT_PROPERTY` does not exist (error 195).
- A `uniqueidentifier` converts to and from `binary(n)` and `varbinary(n)` in SQL Server's byte order (see
  [binary types](data-types-binary.md), example I). `CAST(... AS varchar(n))` gives upper case, and `n` under 36 is
  error 8170.
- `hierarchyid`, `geography`, `geometry`, `cursor` and CLR types do not exist (error 2715).

## Examples

### A. bit

<!-- example: tsql -->
```sql
CREATE TABLE b (id int, flag bit NOT NULL DEFAULT 0, opt bit);
INSERT INTO b (id) VALUES (1);
INSERT INTO b VALUES (2, 1, NULL), (3, 5, 0), (4, 0, 1);
SELECT * FROM b;
SELECT id FROM b WHERE flag = 1;
SELECT SUM(CAST(flag AS int)) AS flagged, COUNT(opt) AS with_opt FROM b;
```

```text
(1 row affected)

(3 rows affected)

id flag opt
-- ---- ----
1  0    NULL
2  1    NULL
3  1    0
4  0    1

(4 rows affected)

id
--
2
3

(2 rows affected)

flagged with_opt
------- --------
2       2

(1 row affected)
```

### B. Strings and bit

<!-- example: tsql -->
```sql
SELECT CAST('true' AS bit) AS t, CAST('0' AS bit) AS z, CAST(5 AS bit) AS five, CAST(NULL AS bit) AS n,
       flag & opt AS bit_and, ~flag AS bit_not
FROM b WHERE id = 2;
```

```text
t z five n    bit_and bit_not
- - ---- ---- ------- -------
1 0 1    NULL NULL    0

(1 row affected)
```

### C. A comparison is not a value

<!-- example: tsql -->
```sql
SELECT CASE WHEN 1 = 1 THEN 1 ELSE 0 END AS as_case, CAST(1 AS bit) AS as_bit;
GO
SELECT 1 = 1;
GO
SELECT CAST(1 AS bit) + CAST(1 AS bit) AS plus;
```

```text
as_case as_bit
------- ------
1       1

(1 row affected)

(No column name)
----------------
1

(1 row affected)

Msg 195, Level 15, State 1, Line 1
operator does not exist: t + t
```

### D. uniqueidentifier

<!-- example: tsql -->
```sql
CREATE TABLE g (id uniqueidentifier PRIMARY KEY, label varchar(10));
INSERT INTO g VALUES ('6F9619FF-8B86-D011-B42D-00C04FC964FF', 'one'),
                     (CAST('00000000-0000-0000-0000-000000000001' AS uniqueidentifier), 'two');
SELECT * FROM g ORDER BY id;
GO
SELECT CASE WHEN NEWID() = NEWID() THEN 'same' ELSE 'different' END AS two_new, LEN(CAST(NEWID() AS varchar(36))) AS length;
GO
INSERT INTO g VALUES ('not-a-guid', 'bad');
```

```text
(2 rows affected)

id                                   label
------------------------------------ -----
00000000-0000-0000-0000-000000000001 two
6F9619FF-8B86-D011-B42D-00C04FC964FF one

(2 rows affected)

two_new   length
--------- ------
different 36

(1 row affected)

Msg 8169, Level 16, State 1, Line 1
Conversion failed when converting from a character string to uniqueidentifier.
```

### E. Writing a GUID

<!-- example: tsql -->
```sql
SELECT CAST('6f9619ff-8b86-d011-b42d-00c04fc964ff' AS uniqueidentifier) AS lower_case,
       CAST('{6F9619FF-8B86-D011-B42D-00C04FC964FF}' AS uniqueidentifier) AS with_braces,
       CAST(CAST('6F9619FF-8B86-D011-B42D-00C04FC964FF' AS uniqueidentifier) AS varchar(40)) AS as_text;
```

```text
lower_case                           with_braces                          as_text
------------------------------------ ------------------------------------ ------------------------------------
6F9619FF-8B86-D011-B42D-00C04FC964FF 6F9619FF-8B86-D011-B42D-00C04FC964FF 6F9619FF-8B86-D011-B42D-00C04FC964FF

(1 row affected)
```

### F. xml is text

<!-- example: tsql -->
```sql
CREATE TABLE x (id int, doc xml);
INSERT INTO x VALUES (1, '<a><b>hi</b></a>');
SELECT * FROM x;
GO
SELECT doc.value('(/a/b)[1]', 'varchar(10)') AS v FROM x;
```

```text
(1 row affected)

id doc
-- ----------------
1  <a><b>hi</b></a>

(1 row affected)

Msg 4121, Level 16, State 1, Line 1
Cannot find either column "doc" or the user-defined function or aggregate "doc.value", or the name is ambiguous.
```

### G. Types that do not exist

<!-- example: tsql -->
```sql
CREATE TABLE gg (g geography);
GO
SELECT SQL_VARIANT_PROPERTY(1, 'BaseType') AS base_type;
```

```text
Msg 2715, Level 16, State 1, Line 1
Column, parameter, or variable #1: Cannot find data type geography.
Msg 195, Level 15, State 1, Line 1
'sql_variant_property' is not a recognized built-in function name.
```

### H. json

<!-- example: tsql -->
```sql
CREATE TABLE jj (id int PRIMARY KEY, doc json NULL);
INSERT jj VALUES (1, N'{"a":[1,2]}'), (2, NULL);
GO
SELECT id, doc, JSON_VALUE(doc, '$.a[1]') AS second FROM jj ORDER BY id;
GO
INSERT jj VALUES (3, N'{"a":');
GO
SELECT CAST(N'[1, 2]' AS json) AS j;
GO
SELECT CAST(N'nope' AS json) AS j;
GO
DROP TABLE jj;
```

```text
(2 rows affected)

id doc         second
-- ----------- ------
1  {"a":[1,2]} 2
2  NULL        NULL

(2 rows affected)

Msg 245, Level 16, State 1, Line 1
invalid input syntax for type json: "{"a":"
j
------
[1, 2]

(1 row affected)

Msg 245, Level 16, State 1, Line 1
invalid input syntax for type json: "nope"
```

## See also

[Numeric types](data-types-numeric.md), [Binary types](data-types-binary.md), [CREATE TYPE](create-type.md),
[NEWID and system functions](functions-system.md)
