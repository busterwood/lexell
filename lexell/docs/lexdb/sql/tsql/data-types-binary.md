# Binary types (Transact-SQL)

Byte strings, and the row version column.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
binary [ ( n ) ]
varbinary [ ( n | max ) ]
image
rowversion
timestamp
```

## Arguments

`binary(n)`, `varbinary(n)`, `varbinary(max)`
: Byte strings of at most *n* bytes (1 to 8000), or without a limit for `max`.

`image`
: The old name for `varbinary(max)`.

`rowversion`, `timestamp`
: Accepted as column types, kept as byte strings. lexdb does not fill them in: see below.

## Remarks

- Bytes come from the client (a JDBC `setBytes`, the bulk copy protocol, a `varbinary` parameter), from a hexadecimal
  literal (`0x4142`), from `CAST('text' AS varbinary(n))` and from `BASE64_DECODE`.
- A hexadecimal literal is a `varbinary` value: `0x4142` is two bytes, and `0x` alone is an empty byte string. Beside a
  number, a binary value is read as that number (`0x41 + 1` is 66).
- A `varbinary` value read through a driver or `sqlcmd` shows as hexadecimal digits.
- Binary values compare byte by byte (`=`, `<`, `ORDER BY`).
- `DATALENGTH` and `LEN` of a binary value are its number of bytes. `SUBSTRING` works on the bytes; `LEFT` and `RIGHT`
  give the first or last characters of the value read as text.
- A value stored in `binary(n)` is padded with zero bytes to *n* bytes; one longer than a `varbinary(n)` or `binary(n)`
  column is error 2628.
- `+` of two binary values joins them. The other arithmetic and bit operators (`-`, `*`, `/`, `%`, `&`, `|`, `^`)
  on two binary values are error 402, and so is a binary value beside a string in anything but a comparison (a
  comparison reads the string as bytes). A `decimal` beside a binary value is error 8114.
- `BASE64_ENCODE` and `BASE64_DECODE` convert between bytes and base 64 text: see
  [string functions](functions-string.md).

- `CAST` and `CONVERT` to `varbinary(n)` or `binary(n)`: a string by its bytes, with style 1 (`0x4142`) or 2 (`4142`)
  from hexadecimal text; a number as big-endian bytes; a binary value cut to *n* bytes, or for `binary(n)` padded
  with zeros.
- `CAST` and `CONVERT` from a binary value to `varchar`: the bytes as characters (`0x4142` gives `AB`), or with style 1
  or 2 the hexadecimal text (`0x4142`, `4142`). To `int`, `bigint` and `smallint`: the last bytes, big-endian.
  Examples E and G.
- `CAST` and `CONVERT` of a `uniqueidentifier` to `binary(n)` or `varbinary(n)` give the 16 bytes as SQL Server stores
  them: the first three groups of the GUID are little-endian, so `6F9619FF-8B86-D011-...` is `0xFF19966F868B11D0...`.
  A binary value to `uniqueidentifier` is padded with zeros or cut to 16 bytes. Example I.

## Differences from SQL Server

- `0x00 = 0x0000` is false: SQL Server pads the shorter binary value with zeros before it compares, lexdb compares the
  values as they are. `CAST(0x41 AS bit)` is error 50000.
- A `varbinary` variable cannot be used in an expression: `DECLARE @v varbinary(4) = 0x4142; SELECT @v + 0x43` is error
  195 (`@v` alone, and `DATALENGTH(@v)`, work).
- **`rowversion` and `timestamp` columns stay NULL.** SQL Server fills them with a database-wide counter on every
  insert and update; lexdb does not, so they cannot detect changes. Use an explicit version column.
- `HASHBYTES` and `CHECKSUM` do not exist (error 195).

## Examples

### A. Bytes from text

<!-- example: tsql -->
```sql
SELECT CAST('AB' AS varbinary(10)) AS bytes, DATALENGTH(CAST('AB' AS varbinary(10))) AS length,
       CAST(CAST('AB' AS varbinary(10)) AS varchar(10)) AS back_to_text;
```

```text
bytes length back_to_text
----- ------ ------------
4142  2      AB

(1 row affected)
```

### B. Binary columns

`binary(4)` pads to four bytes; a value too long for a column is refused.

<!-- example: tsql -->
```sql
CREATE TABLE bt (a binary(4), b varbinary(4), c varbinary(max));
INSERT INTO bt VALUES (CAST('A' AS binary(4)), CAST('AB' AS varbinary(4)), CAST('ABC' AS varbinary(max)));
SELECT a, b, c, DATALENGTH(a) AS la, DATALENGTH(b) AS lb, DATALENGTH(c) AS lc FROM bt;
GO
INSERT INTO bt (a, b) VALUES (0x41, 0x4142434445);
GO
INSERT INTO bt (a, b) VALUES (0x41, 0x4142);
SELECT a, b, DATALENGTH(a) AS la FROM bt WHERE a = CAST('A' AS binary(4));
```

```text
(1 row affected)

a        b    c      la lb lc
-------- ---- ------ -- -- --
41000000 4142 414243 4  2  3

(1 row affected)

Msg 2628, Level 16, State 1, Line 1
String or binary data would be truncated.
(1 row affected)

a        b    la
-------- ---- --
41000000 4142 4
41000000 4142 4

(2 rows affected)
```

### C. Comparing and ordering

<!-- example: tsql -->
```sql
SELECT CASE WHEN CAST('AB' AS varbinary(10)) = CAST('AB' AS varbinary(10)) THEN 'equal' ELSE 'different' END AS eq,
       CASE WHEN CAST('AB' AS varbinary(10)) < CAST('AC' AS varbinary(10)) THEN 'less' ELSE 'not less' END AS lt;
```

```text
eq    lt
----- ----
equal less

(1 row affected)
```

### D. Base 64

<!-- example: tsql -->
```sql
SELECT BASE64_ENCODE(CAST('hi' AS varbinary(10))) AS encoded, BASE64_DECODE('aGk=') AS decoded;
```

```text
encoded decoded
------- -------
aGk=    6869

(1 row affected)
```

### E. Hexadecimal literals

A `0x` literal is a `varbinary` value. Cast it to see its bytes as text or as a number.

<!-- example: tsql -->
```sql
SELECT 0x4142 AS literal, 0x AS empty, DATALENGTH(0x4142) AS bytes;
GO
SELECT CAST(0x4142 AS varbinary(10)) AS a, CAST(0x41424344 AS varbinary(2)) AS cut, CAST(0x41 AS binary(4)) AS padded,
       CAST(65 AS binary(4)) AS from_int;
GO
SELECT CAST(0x4142 AS varchar(10)) AS as_text, CONVERT(varchar(10), 0x4142, 1) AS style_1, CONVERT(varchar(10), 0x4142, 2) AS style_2,
       CONVERT(varbinary(10), '4142', 2) AS from_hex, CONVERT(varbinary(10), '0x4142', 1) AS from_hex_0x;
GO
SELECT CAST(0x41 AS int) AS to_int, CAST(0x0100 AS smallint) AS to_smallint, CAST(0x0000000000000100 AS bigint) AS to_bigint,
       0x41 + 1 AS beside_a_number;
```

```text
literal empty bytes
------- ----- -----
4142          2

(1 row affected)

a    cut  padded   from_int
---- ---- -------- --------
4142 4142 41000000 00000041

(1 row affected)

as_text style_1 style_2 from_hex from_hex_0x
------- ------- ------- -------- -----------
AB      0x4142  4142    4142     4142

(1 row affected)

to_int to_smallint to_bigint beside_a_number
------ ----------- --------- ---------------
65     256         256       66

(1 row affected)
```

### F. rowversion is not filled in

<!-- example: tsql -->
```sql
CREATE TABLE rv (id int PRIMARY KEY, v int, ts rowversion);
INSERT INTO rv (id, v) VALUES (1, 10);
UPDATE rv SET v = 11 WHERE id = 1;
SELECT id, v, ts FROM rv;
```

```text
(1 row affected)

(1 row affected)

id v  ts
-- -- ----
1  11 NULL

(1 row affected)
```

### G. Functions and operators on bytes

<!-- example: tsql -->
```sql
SELECT SUBSTRING(0x41424344, 2, 2) AS sub, LEN(0x414243) AS len, LEFT(0x414243, 2) AS first_two,
       RIGHT(0x414243, 2) AS last_two, 0x4142 + 0x4344 AS joined;
GO
SELECT 0x41 - 0x01 AS minus;
GO
SELECT 0x4142 + 1.5 AS with_a_decimal;
```

```text
sub  len first_two last_two joined
---- --- --------- -------- --------
4243 3   AB        BC       41424344

(1 row affected)

Msg 402, Level 16, State 1, Line 1
The data types varbinary and varbinary are incompatible in the subtract operator.
Msg 8114, Level 16, State 1, Line 1
Error converting data type varbinary to numeric.
```

### H. What lexdb does not do

<!-- example: tsql -->
```sql
SELECT CASE WHEN 0x00 = 0x0000 THEN 'equal' ELSE 'different' END AS padded_comparison;
GO
SELECT CAST(0x41 AS bit) AS as_bit;
GO
DECLARE @v varbinary(4) = 0x4142;
SELECT @v AS alone, DATALENGTH(@v) AS bytes;
SELECT @v + 0x43 AS in_an_expression;
GO
SELECT HASHBYTES('SHA2_256', 'abc') AS hash;
```

```text
padded_comparison
-----------------
different

(1 row affected)

Msg 50000, Level 16, State 1, Line 1
column is of type boolean but the expression is of another type
alone bytes
----- -----
4142  2

(1 row affected)

Msg 195, Level 15, State 1, Line 3
operator does not exist: \x4142 + \x43
Msg 195, Level 15, State 1, Line 1
'hashbytes' is not a recognized built-in function name.
```

### I. uniqueidentifier and bytes

The bytes are in SQL Server's mixed-endian order. A string for `varchar(n)` needs 36 characters.

<!-- example: tsql -->
```sql
SELECT CAST(CAST('6F9619FF-8B86-D011-B42D-00C04FC964FF' AS uniqueidentifier) AS varbinary(16)) AS guid_bytes;
SELECT CAST(0xFF19966F868B11D0B42D00C04FC964FF AS uniqueidentifier) AS guid;
SELECT CAST(0x01 AS uniqueidentifier) AS short_value, DATALENGTH(CAST(NEWID() AS binary(16))) AS bytes;
GO
SELECT CAST(CAST('6F9619FF-8B86-D011-B42D-00C04FC964FF' AS uniqueidentifier) AS varchar(20)) AS too_short;
GO
```

```text
guid_bytes
--------------------------------
FF19966F868B11D0B42D00C04FC964FF

(1 row affected)

guid
------------------------------------
6F9619FF-8B86-D011-B42D-00C04FC964FF

(1 row affected)

short_value                          bytes
------------------------------------ -----
00000001-0000-0000-0000-000000000000 16

(1 row affected)

Msg 8170, Level 16, State 1, Line 1
Insufficient result space to convert uniqueidentifier value to char.
```

## See also

[Character types](data-types-character.md), [CAST and CONVERT](functions-conversion.md),
[Bulk loading](../../bulk-load.md#sql-server-bulk-copy)
