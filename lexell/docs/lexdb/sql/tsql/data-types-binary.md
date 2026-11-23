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

- Bytes come from the client (a JDBC `setBytes`, the bulk copy protocol, a `varbinary` parameter), from
  `CAST('text' AS varbinary(n))`, from `BASE64_DECODE`, and from `NEWID()` cast to `varbinary(16)`.
- A `varbinary` value read through a driver or `sqlcmd` shows as hexadecimal digits.
- Binary values compare byte by byte (`=`, `<`, `ORDER BY`).
- `DATALENGTH` of a value is its number of bytes. `SUBSTRING`, `LEN` and `LEFT` do not work on bytes: see below.
- `BASE64_ENCODE` and `BASE64_DECODE` convert between bytes and base 64 text: see
  [string functions](functions-string.md).

## Differences from SQL Server

- **Hexadecimal literals are numbers.** `0x4142` is the integer 16706, not two bytes, and `CAST(0x4142 AS
  varbinary(10))` is error 50000 (`cannot cast type bigint to bytea`). Only `0x` alone is an empty byte string.
  Binary values cannot be written in a batch except through `CAST('text' AS varbinary(n))`; programs send them as
  parameters.
- A cast of a binary value to `varchar` gives its hexadecimal text with a `\x` in front (`\x4142`), not the
  characters. `CONVERT(varchar, binary, 1)` and `2` give the same text.
- `CAST(65 AS binary(4))` is error 50000; casts between binary values and numbers do not work.
- `binary(n)` is not padded to *n* bytes, and a value longer than *n* is not refused or cut: `INSERT` of five bytes
  into a `varbinary(4)` column succeeds and keeps all five.
- `+` on two binary values is error 195. `SUBSTRING` and `LEFT` work on the hexadecimal text with its `\x` in
  front (`SUBSTRING(CAST('ABCD' AS varbinary(10)), 2, 2)` is `x4`), and `LEN` of a binary value is 0.
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
4142  2      \x4142

(1 row affected)
```

### B. Binary columns

<!-- example: tsql -->
```sql
CREATE TABLE bt (a binary(4), b varbinary(4), c varbinary(max));
INSERT INTO bt VALUES (CAST('A' AS binary(4)), CAST('AB' AS varbinary(4)), CAST('ABC' AS varbinary(max)));
SELECT a, b, c, DATALENGTH(a) AS la, DATALENGTH(b) AS lb, DATALENGTH(c) AS lc FROM bt;
GO
INSERT INTO bt (b) VALUES (CAST('ABCDE' AS varbinary(10)));
SELECT b, DATALENGTH(b) AS five_bytes_in_a_four_byte_column FROM bt WHERE a IS NULL;
```

```text
(1 row affected)

a  b    c      la lb lc
-- ---- ------ -- -- --
41 4142 414243 1  2  3

(1 row affected)

(1 row affected)

b          five_bytes_in_a_four_byte_column
---------- --------------------------------
4142434445 5

(1 row affected)
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

### E. A GUID as bytes

<!-- example: tsql -->
```sql
SELECT CAST(NEWID() AS varbinary(16)) IS NOT NULL AS not_null, DATALENGTH(CAST(NEWID() AS varbinary(16))) AS length;
```

```text
not_null length
-------- ------
1        16

(1 row affected)
```

### F. Hexadecimal literals are numbers

<!-- example: tsql -->
```sql
SELECT 0x4142 AS literal;
GO
SELECT CAST(0x4142 AS varbinary(10)) AS bytes;
```

```text
literal
-------
16706

(1 row affected)

Msg 50000, Level 16, State 1, Line 1
cannot cast type bigint to bytea
```

### G. rowversion is not filled in

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

### H. Text functions on bytes

<!-- example: tsql -->
```sql
SELECT SUBSTRING(CAST('ABCD' AS varbinary(10)), 2, 2) AS sub, LEN(CAST('ABCD' AS varbinary(10))) AS len,
       CAST(CAST('AB' AS varbinary(10)) AS varchar(10)) AS as_text;
GO
SELECT CAST('AB' AS varbinary(10)) + CAST('CD' AS varbinary(10)) AS joined;
```

```text
sub len as_text
--- --- -------
x4  0   \x4142

(1 row affected)

Msg 195, Level 16, State 1, Line 1
operator does not exist: \x4142 + \x4344
```

## See also

[Character types](data-types-character.md), [CAST and CONVERT](functions-conversion.md),
[Bulk loading](../../bulk-load.md#sql-server-bulk-copy)
