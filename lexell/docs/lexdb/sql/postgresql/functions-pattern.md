# Pattern matching

`LIKE`, `ILIKE`, `SIMILAR TO`, the regular-expression operators, and the `regexp_` functions.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
text [ NOT ] LIKE pattern [ ESCAPE escape_character ] → boolean
text [ NOT ] ILIKE pattern [ ESCAPE escape_character ] → boolean
text [ NOT ] SIMILAR TO pattern [ ESCAPE escape_character ] → boolean
text ~ regex → boolean
text ~* regex → boolean
text !~ regex → boolean
text !~* regex → boolean
substring ( text FROM pattern ) → text
substring ( text SIMILAR pattern ESCAPE escape_character ) → text
regexp_like ( text, regex [, flags ] ) → boolean
regexp_count ( text, regex [, start [, flags ] ] ) → integer
regexp_instr ( text, regex [, start [, n [, endoption [, flags [, subexpr ] ] ] ] ] ) → integer
regexp_substr ( text, regex [, start [, n [, flags [, subexpr ] ] ] ] ) → text
regexp_match ( text, regex [, flags ] ) → text[]
regexp_matches ( text, regex [, flags ] ) → setof text[]
regexp_replace ( text, regex, replacement [, start [, n ] ] [, flags ] ) → text
regexp_split_to_array ( text, regex [, flags ] ) → text[]
regexp_split_to_table ( text, regex [, flags ] ) → setof text
```

## Functions

`LIKE`, `ILIKE`
: Whether the whole text matches *pattern*, where `_` is any one character and `%` any run of characters.
  `ILIKE` ignores case. The escape character (backslash by default) makes the next character plain.

`SIMILAR TO`
: Whether the whole text matches an SQL regular expression: `LIKE`'s `_` and `%` with `|`, `*`, `+`, `?`,
  `{m,n}`, `( )` and `[ ]`.

`~`, `~*`, `!~`, `!~*`
: Whether a POSIX regular expression matches anywhere in the text; `*` ignores case, `!` negates.

`substring (text FROM pattern)`
: The part of the text a regular expression matches, or the part its first parenthesised group matches.

`substring (text SIMILAR pattern ESCAPE e)`
: The part of the text between the two `e"` marks of a `SIMILAR TO` pattern.

`regexp_like`
: Whether the regular expression matches (PostgreSQL 15).

`regexp_count`
: How many times it matches, from character *start*.

`regexp_instr`
: Where the *n*th match starts (or, with *endoption* 1, the character after it ends); 0 for no match.

`regexp_substr`
: The text of the *n*th match, or of its group *subexpr*; NULL for no match.

`regexp_match`
: The first match as an array: its groups, or the whole match when there are none. NULL for no match.

`regexp_matches`
: Each match as a row of an array; only the first without the `g` flag.

`regexp_replace`
: The text with the first match replaced, or every match with the `g` flag (or the *n*th, from *start*). In
  *replacement*, `\1` to `\9` are the groups and `\&` the whole match.

`regexp_split_to_array`, `regexp_split_to_table`
: The text split where the regular expression matches, as an array or as rows.

*flags*
: `i` ignores case, `c` respects it, `g` takes every match, `n` makes `.` and `[^...]` not match a newline, `x`
  ignores spaces and comments in the expression.

## Remarks

- The regular expressions take PostgreSQL's usual syntax: POSIX classes (`[[:alpha:]]`), `\d`, `\w`, `\s`, the
  word boundaries `\m`, `\M` and `\y`, lazy quantifiers (`*?`), and embedded options (`(?i)`).
- `.` matches a newline unless the `n` flag is given, as in PostgreSQL.
- A `LIKE` with a fixed prefix (`'abc%'`) can use a B-tree index on the column.
- A bad regular expression is 2201B.

## Differences from PostgreSQL

- The `~~`, `~~*`, `!~~` and `!~~*` spellings of `LIKE` and `ILIKE` are not taken.
- The regular-expression engine has no back references (`(a)\1`) and no lookahead or lookbehind (`(?=...)`): such
  a pattern is 2201B. Its error messages are its own (`error parsing regexp: missing closing )`), not
  PostgreSQL's.
- `ILIKE` folds ASCII letters only (`'É' ILIKE 'é'` is false); `~*` and the `i` flag fold every letter.

## Examples

<!--setup: postgresql
CREATE TABLE file (name text);
INSERT INTO file VALUES ('report_2026.PDF'), ('notes.txt'), ('photo-01.jpg'), ('photo-02.JPG'), ('100%.txt');
-->

The examples use this table:

```sql
CREATE TABLE file (name text);
INSERT INTO file VALUES ('report_2026.PDF'), ('notes.txt'), ('photo-01.jpg'), ('photo-02.JPG'), ('100%.txt');
```

### A. LIKE and ILIKE

<!-- example: postgresql -->
```sql
SELECT name FROM file WHERE name LIKE 'photo%' ORDER BY name;
SELECT name FROM file WHERE name ILIKE '%.jpg' ORDER BY name;
SELECT name FROM file WHERE name LIKE '%\%%';
SELECT name FROM file WHERE name LIKE '%!_%' ESCAPE '!';
```

```text
     name
--------------
 photo-01.jpg
 photo-02.JPG
(2 rows)

     name
--------------
 photo-01.jpg
 photo-02.JPG
(2 rows)

   name
----------
 100%.txt
(1 row)

      name
-----------------
 report_2026.PDF
(1 row)
```

### B. SIMILAR TO

<!-- example: postgresql -->
```sql
SELECT name FROM file WHERE name SIMILAR TO '%.(txt|pdf|PDF)' ORDER BY name;
SELECT 'abc' SIMILAR TO 'a_c' AS a, 'abc' SIMILAR TO 'b%' AS b;
```

```text
      name
-----------------
 100%.txt
 notes.txt
 report_2026.PDF
(3 rows)

 a | b
---+---
 t | f
(1 row)
```

### C. The regular-expression operators

<!-- example: postgresql -->
```sql
SELECT name FROM file WHERE name ~ '-\d+\.' ORDER BY name;
SELECT name FROM file WHERE name ~* '\.jpg$' ORDER BY name;
SELECT 'abc' !~ 'z' AS not_match, 'ABC' !~* 'b' AS not_match_i;
```

```text
     name
--------------
 photo-01.jpg
 photo-02.JPG
(2 rows)

     name
--------------
 photo-01.jpg
 photo-02.JPG
(2 rows)

 not_match | not_match_i
-----------+-------------
 t         | f
(1 row)
```

### D. substring with a pattern

<!-- example: postgresql -->
```sql
SELECT substring('photo-01.jpg' FROM '\d+') AS digits, substring('photo-01.jpg' FROM '\.(\w+)$') AS ext,
       substring('foobar' SIMILAR '%#"o_b#"%' ESCAPE '#') AS similar;
```

```text
 digits | ext | similar
--------+-----+---------
 01     | jpg | oob
(1 row)
```

### E. regexp_like, regexp_count, regexp_instr and regexp_substr

<!-- example: postgresql -->
```sql
SELECT regexp_like('Photo', '^photo', 'i') AS like_i, regexp_count('banana', 'an') AS count,
       regexp_instr('banana', 'an', 1, 2) AS second_at, regexp_substr('a1b22c333', '\d+', 1, 3) AS third,
       regexp_substr('k=v', '(\w)=(\w)', 1, 1, '', 2) AS group2;
```

```text
 like_i | count | second_at | third | group2
--------+-------+-----------+-------+--------
 t      |     2 |         4 | 333   | v
(1 row)
```

### F. regexp_match and regexp_matches

<!-- example: postgresql -->
```sql
SELECT regexp_match('2026-03-01', '(\d+)-(\d+)-(\d+)') AS parts, regexp_match('abc', 'z') AS none;
SELECT regexp_matches('a1b22c333', '\d+', 'g') AS m;
```

```text
    parts     | none
--------------+------
 {2026,03,01} |
(1 row)

   m
-------
 {1}
 {22}
 {333}
(3 rows)
```

### G. regexp_replace

<!-- example: postgresql -->
```sql
SELECT regexp_replace('a1b22c333', '\d+', '#') AS first, regexp_replace('a1b22c333', '\d+', '#', 'g') AS every,
       regexp_replace('John Smith', '(\w+) (\w+)', '\2, \1') AS swapped,
       regexp_replace('aaa', 'a', 'b', 1, 2) AS second_only;
```

```text
   first   | every  |   swapped   | second_only
-----------+--------+-------------+-------------
 a#b22c333 | a#b#c# | Smith, John | aba
(1 row)
```

### H. Splitting

<!-- example: postgresql -->
```sql
SELECT regexp_split_to_array('one, two,three', ',\s*') AS arr;
SELECT regexp_split_to_table('a1b22c', '\d+') AS part;
```

```text
       arr
-----------------
 {one,two,three}
(1 row)

 part
------
 a
 b
 c
(3 rows)
```

### I. Errors

<!-- example: postgresql -->
```sql
SELECT 'abc' ~ '(';
SELECT 'aa' ~ '(a)\1';
SELECT regexp_like('a', 'a', 'z');
SELECT 'abc' ~~ 'a%';
```

```text
ERROR:  invalid regular expression: error parsing regexp: missing closing ): `(?s)(`
ERROR:  invalid regular expression: error parsing regexp: invalid escape sequence: `\1` (backreferences are not supported)
ERROR:  invalid regular expression option: "z"
ERROR:  operator does not exist: ~ text
```

## See also

[String functions](functions-string.md) · [Operators](operators.md) · [Set-returning functions](functions-srf.md) ·
[CREATE INDEX](create-index.md)
