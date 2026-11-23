# Binary type

`bytea`: a string of bytes.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
bytea
```

## Remarks

- A `bytea` constant is written in hex, `'\x6869'`, or as text, whose UTF-8 bytes it takes (`'hi'::bytea`).
- Output is always hex (`\x6869`), as with PostgreSQL's default `bytea_output = 'hex'`.
- `||` joins two values; `length` and `octet_length` count bytes; `encode` and `decode` convert to and from
  `hex`, `base64` and `escape` text; `md5` takes `bytea` as well as text; `bit_count`, `crc32` and `crc32c` take
  `bytea`.
- A `uuid` casts to `bytea`, its 16 bytes (PostgreSQL 18).
- Bad hex is 22P02 (`invalid hexadecimal digit`).

## Differences from PostgreSQL

- `SET bytea_output = 'escape'` is accepted and ignored: output stays hex.
- `substring` and `position` on `bytea` work on the hex text, not the bytes: `substring('\x01020304'::bytea from 2
  for 2)` gives `x0`, and `position('\x03'::bytea in '\x01020304'::bytea)` gives 0.
- `get_byte`, `set_byte`, `get_bit`, `set_bit`, `convert_to`, `convert_from` and `sha224` ... `sha512` do not
  exist (42883).

## Examples

### A. Constants and output

<!-- example: postgresql -->
```sql
SELECT '\x6869'::bytea AS hex, 'hi'::bytea AS from_text, length('\x0001ff'::bytea) AS bytes;
```

```text
  hex   | from_text | bytes
--------+-----------+-------
 \x6869 | \x6869    |     3
(1 row)
```

### B. A bytea column

<!-- example: postgresql -->
```sql
CREATE TABLE blob (id int, data bytea);
INSERT INTO blob VALUES (1, '\xdeadbeef'), (2, 'hello'::bytea);
SELECT id, data, octet_length(data) FROM blob ORDER BY id;
```

```text
CREATE TABLE
INSERT 0 2
 id |     data     | octet_length
----+--------------+--------------
  1 | \xdeadbeef   |            4
  2 | \x68656c6c6f |            5
(2 rows)
```

### C. Joining, encoding and decoding

<!-- example: postgresql -->
```sql
SELECT 'hi'::bytea || '\x21'::bytea AS joined,
       encode('hello'::bytea, 'base64') AS b64,
       decode('aGVsbG8=', 'base64') AS raw,
       encode('\x41ff'::bytea, 'escape') AS escaped;
```

```text
  joined  |   b64    |     raw      | escaped
----------+----------+--------------+---------
 \x686921 | aGVsbG8= | \x68656c6c6f | A\377
(1 row)
```

### D. A uuid as bytes

<!-- example: postgresql -->
```sql
SELECT 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'::uuid::bytea AS uuid_bytes, md5('hi'::bytea);
```

```text
             uuid_bytes             |               md5
------------------------------------+----------------------------------
 \xa0eebc999c0b4ef8bb6d6bb9bd380a11 | 49f68a5c8493ec2c0bf489821c21fc3b
(1 row)
```

### E. Errors

<!-- example: postgresql -->
```sql
SELECT '\xzz'::bytea;
SELECT get_byte('abc'::bytea, 0);
```

```text
ERROR:  invalid hexadecimal digit: "z"
ERROR:  function get_byte with 2 arguments does not exist
```

## See also

[String functions](functions-string.md) · [UUID type](data-types-uuid.md) · [Type conversion](type-conversion.md)
