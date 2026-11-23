# String functions

Functions that measure, cut, pad, search, change and build text.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
lower ( text ) → text
upper ( text ) → text
initcap ( text ) → text
casefold ( text ) → text
length ( text ) → integer
char_length ( text ) → integer
octet_length ( text ) → integer
substr ( text, start [, count ] ) → text
substring ( text [ FROM start ] [ FOR count ] ) → text
substring ( text, start [, count ] ) → text
position ( substring IN text ) → integer
strpos ( text, substring ) → integer
overlay ( text PLACING new FROM start [ FOR count ] ) → text
trim ( [ LEADING | TRAILING | BOTH ] [ characters ] FROM text ) → text
btrim ( text [, characters ] ) → text
ltrim ( text [, characters ] ) → text
rtrim ( text [, characters ] ) → text
lpad ( text, length [, fill ] ) → text
rpad ( text, length [, fill ] ) → text
left ( text, n ) → text
right ( text, n ) → text
repeat ( text, n ) → text
replace ( text, from, to ) → text
translate ( text, from, to ) → text
reverse ( text ) → text
split_part ( text, delimiter, n ) → text
starts_with ( text, prefix ) → boolean
concat ( value [, ...] ) → text
concat_ws ( separator, value [, ...] ) → text
text || value → text
string_to_array ( text, delimiter [, null_string ] ) → text[]
string_to_table ( text, delimiter [, null_string ] ) → setof text
```

The functions that quote, encode and convert text are on [their own page](functions-string-convert.md):
`format`, `quote_literal`, `quote_nullable`, `quote_ident`, `chr`, `ascii`, `md5`, `encode`, `decode`, `to_hex`,
`to_bin`, `to_oct`, `unistr`.

## Functions

`lower`, `upper`
: The text in lower or upper case. Only ASCII letters change, as in PostgreSQL's `C` locale.

`initcap`
: The first letter of each word in upper case, the rest in lower case. A word is a run of letters and digits.

`casefold`
: The text folded for case-insensitive comparison (PostgreSQL 18). Unlike `lower`, it folds letters outside ASCII.

`length`, `char_length`
: The number of characters. Of a `char(n)` value, without its trailing spaces.

`octet_length`
: The number of bytes (UTF-8).

`substr`, `substring`
: The part of the text from character *start* (the first is 1), *count* characters long or to the end. A *start*
  before 1 counts the characters before 1 against *count*. A negative *count* is 22011. `substring (text FROM
  pattern)` takes a regular expression: see [pattern matching](functions-pattern.md).

`position`, `strpos`
: Where *substring* first starts in the text, or 0.

`overlay`
: The text with *count* characters from *start* replaced by *new*. Without `FOR`, *count* is the length of *new*.

`trim`, `btrim`, `ltrim`, `rtrim`
: The text without the given *characters* (spaces by default) at both ends, at the start, or at the end.
  *characters* is a set, not a string: `btrim('xyaxy', 'xy')` is `a`.

`lpad`, `rpad`
: The text filled on the left or right to *length* characters with *fill* (a space by default), repeated as
  needed; a longer text is cut to *length*.

`left`, `right`
: The first or last *n* characters. A negative *n* gives all but the last or first *-n*.

`repeat`
: The text *n* times; for *n* of 0 or less, an empty string.

`replace`
: The text with every *from* replaced by *to*.

`translate`
: The text with each character in *from* replaced by the character at the same place in *to*; a character of
  *from* with no partner in *to* is removed.

`reverse`
: The characters in the opposite order.

`split_part`
: The *n*th field of the text split at *delimiter*; a negative *n* counts from the end. Past the last field, an
  empty string.

`starts_with`
: Whether the text begins with *prefix*.

`concat`, `concat_ws`
: The values as text, joined, with NULLs left out. `concat_ws` puts *separator* between them.

`||`
: Joins text with text or with another value as text. NULL on either side gives NULL.

`string_to_array`, `string_to_table`
: The text split at *delimiter*, as an array or as rows. A field equal to *null_string* becomes NULL. A NULL
  delimiter splits into characters; an empty delimiter gives the whole text as one field.

## Remarks

- A NULL argument gives NULL, except in `concat` and `concat_ws` (NULLs are left out).
- Positions and lengths count characters, not bytes.
- `length`, `strpos` and `position` return `integer`.

## Differences from PostgreSQL

- `upper`, `lower` and `initcap` change ASCII letters only, as in a database with the `C` locale (`upper('héllo')`
  is `HéLLO`). PostgreSQL with a UTF-8 locale changes every letter.
- `character_length`, `bit_length`, `normalize`, `to_ascii` and the `^@` operator do not exist (42883, or a syntax
  error for `^@`). Use `char_length`, `octet_length * 8` and `starts_with`.
- `concat_ws` with the separator alone is 42883 (PostgreSQL: an empty string).

## Examples

### A. Case

<!-- example: postgresql -->
```sql
SELECT lower('ABC') AS lower, upper('abc') AS upper, initcap('hello wORLD-foo') AS initcap,
       casefold('ÀBC') AS casefold, upper('héllo') AS ascii_only;
```

```text
 lower | upper |     initcap     | casefold | ascii_only
-------+-------+-----------------+----------+------------
 abc   | ABC   | Hello World-Foo | àbc      | HéLLO
(1 row)
```

### B. Length

<!-- example: postgresql -->
```sql
SELECT length('héllo') AS length, char_length('héllo') AS char_length, octet_length('héllo') AS octets,
       length('ab'::char(5)) AS char5;
```

```text
 length | char_length | octets | char5
--------+-------------+--------+-------
      5 |           5 |      6 |     2
(1 row)
```

### C. substr and substring

<!-- example: postgresql -->
```sql
SELECT substr('abcdef', 2) AS a, substr('abcdef', 2, 3) AS b, substr('abcdef', 0, 3) AS c,
       substring('abcdef' FROM 2 FOR 3) AS d, substring('abcdef' FROM 3) AS e, substring('abcdef' FOR 2) AS f;
```

```text
   a   |  b  | c  |  d  |  e   | f
-------+-----+----+-----+------+----
 bcdef | bcd | ab | bcd | cdef | ab
(1 row)
```

### D. position, strpos and overlay

<!-- example: postgresql -->
```sql
SELECT position('c' IN 'abcabc') AS pos, strpos('abcabc', 'c') AS strpos, strpos('abc', 'z') AS none,
       overlay('abcdef' PLACING 'XY' FROM 2) AS o1, overlay('abcdef' PLACING 'XY' FROM 2 FOR 3) AS o2;
```

```text
 pos | strpos | none |   o1   |  o2
-----+--------+------+--------+-------
   3 |      3 |    0 | aXYdef | aXYef
(1 row)
```

### E. Trimming

<!-- example: postgresql -->
```sql
SELECT '|' || trim('  a  ') || '|' AS trim, trim(LEADING 'x' FROM 'xxaxx') AS leading,
       trim(TRAILING 'x' FROM 'xxaxx') AS trailing, btrim('xyaxy', 'xy') AS btrim,
       ltrim('xxa', 'x') AS ltrim, rtrim('axx', 'x') AS rtrim;
```

```text
 trim | leading | trailing | btrim | ltrim | rtrim
------+---------+----------+-------+-------+-------
 |a|  | axx     | xxa      | a     | a     | a
(1 row)
```

### F. Padding, left, right and repeat

<!-- example: postgresql -->
```sql
SELECT lpad('7', 3, '0') AS lpad, rpad('ab', 5, 'xy') AS rpad, lpad('abcdef', 3) AS cut,
       left('abcdef', 2) AS l, left('abcdef', -2) AS l_neg, right('abcdef', 2) AS r, repeat('ab', 3) AS rep;
```

```text
 lpad | rpad  | cut | l  | l_neg | r  |  rep
------+-------+-----+----+-------+----+--------
 007  | abxyx | abc | ab | abcd  | ef | ababab
(1 row)
```

### G. replace, translate and reverse

<!-- example: postgresql -->
```sql
SELECT replace('a-b-c', '-', '+') AS replace, translate('12345', '143', 'ax') AS translate, reverse('abc') AS reverse;
```

```text
 replace | translate | reverse
---------+-----------+---------
 a+b+c   | a2x5      | cba
(1 row)
```

### H. split_part and starts_with

<!-- example: postgresql -->
```sql
SELECT split_part('2026-03-01', '-', 2) AS month, split_part('a.b.c', '.', -1) AS last,
       starts_with('alpha', 'al') AS starts;
```

```text
 month | last | starts
-------+------+--------
 03    | c    | t
(1 row)
```

### I. Joining text

<!-- example: postgresql -->
```sql
SELECT concat('a', 1, NULL, true) AS concat, concat_ws('-', 'a', NULL, 'b', 2) AS concat_ws,
       'a' || 1 AS pipe, ('a' || NULL) IS NULL AS pipe_null;
```

```text
 concat | concat_ws | pipe | pipe_null
--------+-----------+------+-----------
 a1t    | a-b-2     | a1   | t
(1 row)
```

### J. Splitting into an array or rows

<!-- example: postgresql -->
```sql
SELECT string_to_array('a,b,,c', ',') AS a, string_to_array('a,b,,c', ',', '') AS with_null,
       string_to_array('abc', NULL) AS chars;
SELECT * FROM string_to_table('red,green,blue', ',') AS t(colour);
```

```text
     a      |  with_null   |  chars
------------+--------------+---------
 {a,b,"",c} | {a,b,NULL,c} | {a,b,c}
(1 row)

 colour
--------
 red
 green
 blue
(3 rows)
```

### K. On a table

<!-- example: postgresql -->
```sql
CREATE TABLE person (id int, full_name text, email text);
INSERT INTO person VALUES (1, 'ann LEE', 'ann@example.com'), (2, 'bob  smith ', 'bob@test.org');
SELECT id, initcap(trim(full_name)) AS name, split_part(email, '@', 2) AS domain,
       lpad(id::text, 4, '0') AS code FROM person ORDER BY id;
```

```text
CREATE TABLE
INSERT 0 2
 id |    name    |   domain    | code
----+------------+-------------+------
  1 | Ann Lee    | example.com | 0001
  2 | Bob  Smith | test.org    | 0002
(2 rows)
```

### L. Errors

<!-- example: postgresql -->
```sql
SELECT substr('abc', 1, -1);
SELECT character_length('abc');
```

```text
ERROR:  negative substring length not allowed
ERROR:  function character_length with 1 arguments does not exist
```

## See also

[String conversion functions](functions-string-convert.md) · [Pattern matching](functions-pattern.md) ·
[Formatting functions](functions-formatting.md) · [Character types](data-types-character.md) ·
[Aggregate functions](functions-aggregate.md) (`string_agg`)
