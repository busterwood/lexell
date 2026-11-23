# String conversion functions

Functions that build text from a template, quote values and names, and convert between text, codes, bytes and
numbers.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
format ( template [, value [, ...] ] ) → text
quote_literal ( value ) → text
quote_nullable ( value ) → text
quote_ident ( text ) → text
chr ( integer ) → text
ascii ( text ) → integer
md5 ( text | bytea ) → text
encode ( bytea, format ) → text
decode ( text, format ) → bytea
to_hex ( integer | bigint ) → text
to_bin ( integer | bigint ) → text
to_oct ( integer | bigint ) → text
unistr ( text ) → text
```

## Functions

`format`
: The *template* with each `%s` replaced by the next value as text, `%I` by the value quoted as a name, and `%L`
  by the value quoted as a constant (`NULL` for NULL). `%n$s` takes the *n*th value; a width (`%5s`, `%-5s`)
  pads to that many characters; `%%` is a `%`. A NULL value is an empty string for `%s`.

`quote_literal`
: The value as a string constant, in single quotes, with quotes and backslashes doubled. A NULL gives NULL.

`quote_nullable`
: Like `quote_literal`, but a NULL gives the text `NULL`.

`quote_ident`
: The text as an identifier: in double quotes when it is not all lower-case letters, digits and underscores, or
  when it is a reserved word.

`chr`
: The character of a Unicode code point. 0 is 54000 (`null character not permitted`).

`ascii`
: The code point of the first character; 0 for an empty string.

`md5`
: The MD5 hash of the text's bytes, or of a `bytea`, as 32 hex digits.

`encode`, `decode`
: `bytea` to text and back, in the format `hex`, `base64` or `escape`.

`to_hex`, `to_bin`, `to_oct`
: The integer in base 16, 2 or 8 (`to_bin` and `to_oct` are PostgreSQL 16's). A negative value is shown as its
  two's complement in 32 or 64 bits.

`unistr`
: The text with Unicode escapes turned into characters: `\XXXX`, `\+XXXXXX`, `\uXXXX`, `\UXXXXXXXX`; `\\` is a
  backslash. A bad escape is 22025.

## Remarks

- `format` and `quote_*` make SQL text safe to run; `%I` and `%L` quote as PostgreSQL does.
- `encode(text, ...)` takes text as its bytes.

## Differences from PostgreSQL

- `format` takes only `%s`, `%I` and `%L` with a position and a width; a width from an argument (`%*s`) is 42883
  (`too few arguments for format()`).
- `sha224`, `sha256`, `sha384`, `sha512`, `convert`, `convert_to` and `convert_from` do not exist (42883).
- `encode` and `decode` take `hex`, `base64` and `escape`; other formats are 22023.

## Examples

### A. format

<!-- example: postgresql -->
```sql
SELECT format('Hello %s, you are %s', 'Ann', 42) AS s, format('%2$s %1$s', 'world', 'hello') AS positional,
       format('[%5s][%-5s]', 'ab', 'cd') AS widths, format('100%%') AS percent;
```

```text
           s           | positional  |     widths     | percent
-----------------------+-------------+----------------+---------
 Hello Ann, you are 42 | hello world | [   ab][cd   ] | 100%
(1 row)
```

### B. format for SQL text

<!-- example: postgresql -->
```sql
SELECT format('SELECT * FROM %I WHERE name = %L', 'My Table', 'O''Brien') AS q1,
       format('UPDATE t SET x = %L', NULL) AS q2;
```

```text
                        q1                        |          q2
--------------------------------------------------+-----------------------
 SELECT * FROM "My Table" WHERE name = 'O''Brien' | UPDATE t SET x = NULL
(1 row)
```

### C. Quoting

<!-- example: postgresql -->
```sql
SELECT quote_literal('it''s') AS lit, quote_literal(42) AS num, quote_nullable(NULL) AS nullable,
       quote_ident('abc') AS plain, quote_ident('My Table') AS mixed, quote_ident('select') AS reserved;
```

```text
   lit   | num  | nullable | plain |   mixed    | reserved
---------+------+----------+-------+------------+----------
 'it''s' | '42' | NULL     | abc   | "My Table" | "select"
(1 row)
```

### D. Characters and codes

<!-- example: postgresql -->
```sql
SELECT chr(65) AS a, chr(233) AS e_acute, ascii('A') AS code_a, ascii('é') AS code_e, ascii('') AS empty;
```

```text
 a | e_acute | code_a | code_e | empty
---+---------+--------+--------+-------
 A | é       |     65 |    233 |     0
(1 row)
```

### E. md5, encode and decode

<!-- example: postgresql -->
```sql
SELECT md5('abc') AS md5, encode('abc', 'hex') AS hex, encode('abc', 'base64') AS b64,
       decode('616263', 'hex') AS from_hex, decode('YWJj', 'base64') AS from_b64;
```

```text
               md5                |  hex   | b64  | from_hex | from_b64
----------------------------------+--------+------+----------+----------
 900150983cd24fb0d6963f7d28e17f72 | 616263 | YWJj | \x616263 | \x616263
(1 row)
```

### F. Numbers in other bases

<!-- example: postgresql -->
```sql
SELECT to_hex(255) AS hex, to_hex(-1) AS hex_neg, to_hex(9223372036854775807) AS hex_big,
       to_bin(5) AS bin, to_oct(8) AS oct;
```

```text
 hex | hex_neg  |     hex_big      | bin | oct
-----+----------+------------------+-----+-----
 ff  | ffffffff | 7fffffffffffffff | 101 | 10
(1 row)
```

### G. Unicode escapes

<!-- example: postgresql -->
```sql
SELECT unistr('\0041\00e9') AS a, unistr('d\u0061t\U00000061') AS b, unistr('\+01F600') AS emoji;
```

```text
 a  |  b   | emoji
----+------+-------
 Aé | data | 😀
(1 row)
```

### H. Errors

<!-- example: postgresql -->
```sql
SELECT chr(0);
SELECT unistr('\zz');
SELECT format('%x', 1);
SELECT encode('abc', 'base32');
```

```text
ERROR:  null character not permitted
ERROR:  invalid Unicode escape
ERROR:  unrecognized format() type specifier "x"
ERROR:  unrecognized encoding: "base32"
```

## See also

[String functions](functions-string.md) · [Binary type](data-types-binary.md) ·
[Formatting functions](functions-formatting.md)
