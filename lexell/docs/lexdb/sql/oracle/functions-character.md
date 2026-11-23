# Character functions

Functions that measure, cut, search, pad, trim and convert character values.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
SUBSTR ( char, position [, length ] )
SUBSTRB ( char, position [, length ] )
INSTR ( string, substring [, position [, occurrence ] ] )
LENGTH ( char )
LENGTHB ( char )
UPPER ( char )
LOWER ( char )
INITCAP ( char )
LPAD ( expr1, n [, expr2 ] )
RPAD ( expr1, n [, expr2 ] )
LTRIM ( char [, set ] )
RTRIM ( char [, set ] )
TRIM ( [ { LEADING | TRAILING | BOTH } ] [ trim_character ] FROM trim_source )
REPLACE ( char, search_string [, replacement_string ] )
TRANSLATE ( expr, from_string, to_string )
CONCAT ( char1, char2 )
char1 || char2
CHR ( n )
ASCII ( char )
UNISTR ( string )
RAWTOHEX ( raw )
HEXTORAW ( char )
TO_CLOB ( char )
TO_NCLOB ( char )
SYS_GUID ( )
```

Pattern functions are on the [regular expression page](functions-regex.md). `TO_CHAR` and the other conversions are
on the [conversion page](functions-conversion.md).

## Functions

`SUBSTR`
: *length* characters from *position* (the first character is 1). A negative *position* counts from the end; 0 is
  taken as 1. Without *length* the rest of the string comes back. A *length* below 1, a *position* past the end or a
  NULL gives NULL. Fractions are truncated. `SUBSTR` also takes a `CLOB`.

`SUBSTRB`
: As `SUBSTR`. lexdb counts characters, not bytes (see Differences).

`INSTR`
: The position of the *occurrence*th match of *substring*, searching from *position*, or 0. A negative *position*
  searches backwards from the end. The search is case-sensitive. `INSTRB` is accepted as well.

`LENGTH`
: The number of characters. The empty string is NULL, so `LENGTH('')` is NULL. A number is measured as text.
  `LENGTHC` is the same function.

`LENGTHB`
: The number of bytes in Oracle; lexdb gives the number of characters (see Differences).

`UPPER`, `LOWER`
: The string in upper or lower case. Letters outside ASCII are changed too.

`INITCAP`
: The first letter of every word in upper case and the rest in lower case. A word ends at any character that is not
  a letter or a digit, so `-` and `_` start a new word.

`LPAD`, `RPAD`
: The string made *n* characters long by adding *expr2* (a space if omitted) on the left or the right. A string
  longer than *n* is cut to *n* characters. *n* of 0 or less, or a NULL argument, gives NULL.

`LTRIM`, `RTRIM`
: Remove from the left or the right every character that is in *set* (a space if omitted). *set* is a list of
  characters, not a string to match.

`TRIM`
: Removes one *trim_character* (a space if omitted) from the start, the end or both (`BOTH` is the default).

`REPLACE`
: Replaces every occurrence of *search_string* by *replacement_string*; without a replacement the occurrences are
  removed. An empty *search_string* changes nothing. A number argument is converted to text.

`TRANSLATE`
: Replaces each character of *from_string* by the character at the same place in *to_string*. A character without a
  partner in *to_string* is removed.

`CONCAT`
: Joins two strings. A NULL argument counts as an empty string; the result is NULL only when both are NULL. `CONCAT`
  takes exactly two arguments.

`||`
: The concatenation operator, for any number of operands. NULL operands are ignored, and numbers and dates are
  converted to text.

`CHR`
: The character with code point *n* (UTF-8 code points, not bytes).

`ASCII`
: The code point of the first character, or NULL for an empty string.

`UNISTR`
: Reads `\xxxx` escapes (four hex digits, UTF-16 code units) in the string; `\\` is a backslash.

`RAWTOHEX`
: The hexadecimal text (upper case) of a `RAW` value or of the bytes of a string.

`HEXTORAW`
: The `RAW` value for a string of hexadecimal digits. The string needs an even number of digits.

`TO_CLOB`, `TO_NCLOB`
: Convert a string or number to `CLOB` or `NCLOB`. A `CLOB` takes the character functions above.

`SYS_GUID`
: A new 32-character identifier, different on every call. As a column default (`DEFAULT SYS_GUID()`) it fills a
  `RAW(16)` column.

## Remarks

- The empty string is NULL, so `LPAD('abc', 5, '')`, `SUBSTR('', 1)` and `ASCII('')` are NULL.
- Comparisons and `INSTR` are case-sensitive; use `UPPER` or `LOWER` on both sides to ignore case.
- `SOUNDEX`, `VSIZE`, `DUMP`, `ORA_HASH`, `STANDARD_HASH`, `NCHR`, `ASCIISTR`, `COMPOSE`, `DECOMPOSE`, `CONVERT`
  and the `NLS_UPPER` family do not exist (ORA-00904).

## Differences from Oracle

- `LENGTHB` and `SUBSTRB` count characters: `LENGTHB('héllo')` is 5 (Oracle: 6 in AL32UTF8) and `LENGTHB('€')`
  is 1 (Oracle: 3). `INSTRB` counts characters too.
- `LENGTH(DATE '2026-01-01')` is 19, the length of `YYYY-MM-DD HH24:MI:SS`; Oracle uses the session's date
  format and gives 9.
- `TRIM('xy' FROM 'xyabc')` returns `abc`; Oracle refuses a trim set of more than one character (ORA-30001).
- `SYS_GUID()` is text of 32 characters, not a `RAW(16)`: `RAWTOHEX(SYS_GUID())` is 64 characters long (Oracle: 32).
- `TRIM(CHR(0) FROM 'x')` fails with ORA-01792; a `CHR(0)` is not usable in a trim. Other trim characters work.
- `HEXTORAW('abc')` (an odd number of digits) is ORA-01722; Oracle pads it on the left.
- `REVERSE` and `REPEAT` are accepted under their PostgreSQL names; they are not Oracle SQL functions (`REVERSE`
  exists in Oracle but is undocumented).
- Error texts are shorter than Oracle's. `CONCAT` with three arguments is ORA-00909.

## Examples

### A. SUBSTR, INSTR and LENGTH

<!-- example: oracle -->
```sql
SELECT SUBSTR('abcdef', 2, 3) AS mid, SUBSTR('abcdef', -3) AS last3, SUBSTR('abcdef', -3, 2) AS neg_len,
       SUBSTR('abcdef', 0, 2) AS zero_start, SUBSTR('abcdef', 10) AS past_end, SUBSTR(12345, 2, 3) AS from_number
FROM dual;
SELECT INSTR('corporate floor', 'or') AS first_match, INSTR('corporate floor', 'or', 3) AS from_3,
       INSTR('corporate floor', 'or', 3, 2) AS second_from_3, INSTR('corporate floor', 'or', -3, 2) AS backwards,
       INSTR('abc', 'x') AS none, INSTR('CORPORATE', 'or') AS case_sensitive
FROM dual;
SELECT LENGTH('héllo') AS chars, LENGTH('') AS empty, LENGTH('  ') AS blanks, LENGTH(12345) AS from_number FROM dual;
```

```text
MID LAST3 NEG_LEN ZERO_START PAST_END FROM_NUMBER
--- ----- ------- ---------- -------- -----------
bcd def   de      ab                  234

1 row selected.

FIRST_MATCH FROM_3 SECOND_FROM_3 BACKWARDS NONE CASE_SENSITIVE
----------- ------ ------------- --------- ---- --------------
          2      5            14         2    0              0

1 row selected.

CHARS EMPTY BLANKS FROM_NUMBER
----- ----- ------ -----------
    5            2           5

1 row selected.
```

### B. Case: UPPER, LOWER, INITCAP

<!-- example: oracle -->
```sql
SELECT UPPER('Hello World') AS up, LOWER('Hello World') AS low, INITCAP('hello wORLD-foo bar_baz 3rd') AS init,
       UPPER(NULL) AS null_in, INITCAP('élan vital') AS accents
FROM dual;
```

```text
UP          LOW         INIT                        NULL_IN ACCENTS
----------- ----------- --------------------------- ------- ----------
HELLO WORLD hello world Hello World-Foo Bar_Baz 3rd         élan Vital

1 row selected.
```

### C. LPAD and RPAD

<!-- example: oracle -->
```sql
SELECT LPAD('abc', 6) AS lpad_blank, LPAD('abc', 6, '*') AS lpad_star, LPAD('abc', 8, 'xy') AS lpad_pattern,
       LPAD('abcdef', 3) AS lpad_cut, RPAD('abc', 6, '*') AS rpad_star, RPAD('abc', 8, 'xy') AS rpad_pattern,
       RPAD('abcdef', 3, '*') AS rpad_cut, LPAD(12, 5, 0) AS from_number
FROM dual;
SELECT LPAD('a', 0) AS zero, LPAD('a', -1) AS negative, LPAD('abc', 5, '') AS empty_pad, RPAD(NULL, 3, 'x') AS null_in
FROM dual;
```

```text
LPAD_BLANK LPAD_STAR LPAD_PATTERN LPAD_CUT RPAD_STAR RPAD_PATTERN RPAD_CUT FROM_NUMBER
---------- --------- ------------ -------- --------- ------------ -------- -----------
   abc     ***abc    xyxyxabc     abc      abc***    abcxyxyx     abc      00012

1 row selected.

ZERO NEGATIVE EMPTY_PAD NULL_IN
---- -------- --------- -------


1 row selected.
```

### D. LTRIM, RTRIM and TRIM

<!-- example: oracle -->
```sql
SELECT '[' || LTRIM('  abc  ') || ']' AS ltrim_blank, '[' || RTRIM('  abc  ') || ']' AS rtrim_blank,
       LTRIM('xxyabc', 'xy') AS ltrim_set, RTRIM('abcxxy', 'xy') AS rtrim_set,
       LTRIM('123abc', '0123456789') AS ltrim_digits
FROM dual;
SELECT '[' || TRIM('  abc  ') || ']' AS trim_blank, TRIM(LEADING 'x' FROM 'xxabcxx') AS leading_x,
       TRIM(TRAILING 'x' FROM 'xxabcxx') AS trailing_x, TRIM(BOTH 'x' FROM 'xxabcxx') AS both_x,
       TRIM('x' FROM 'xxabcxx') AS default_both, TRIM(LEADING FROM '  abc ') AS leading_blank
FROM dual;
```

```text
LTRIM_BLANK RTRIM_BLANK LTRIM_SET RTRIM_SET LTRIM_DIGITS
----------- ----------- --------- --------- ------------
[abc  ]     [  abc]     abc       abc       abc

1 row selected.

TRIM_BLANK LEADING_X TRAILING_X BOTH_X DEFAULT_BOTH LEADING_BLANK
---------- --------- ---------- ------ ------------ -------------
[abc]      abcxx     xxabc      abc    abc          abc

1 row selected.
```

### E. REPLACE, TRANSLATE and CONCAT

<!-- example: oracle -->
```sql
SELECT REPLACE('hello world', 'o', '0') AS replaced, REPLACE('hello world', 'o') AS removed,
       REPLACE('hello', 'l', 'LL') AS longer, REPLACE('hello', '', 'x') AS empty_search,
       REPLACE('Hello', 'h', 'j') AS case_sensitive, REPLACE(123, 2, 9) AS from_number
FROM dual;
SELECT TRANSLATE('hello', 'el', 'ip') AS two_for_two, TRANSLATE('hello', 'elo', 'ip') AS drops_o,
       TRANSLATE('2KRW229', '0123456789', '9999999999') AS digits_to_nine, TRANSLATE('abc', 'xb', 'y') AS drops_b
FROM dual;
SELECT CONCAT('ab', 'cd') AS two, CONCAT('ab', NULL) AS with_null, CONCAT(1, 2) AS numbers,
       'ab' || 'cd' || 'ef' AS operator, 'ab' || NULL || 'cd' AS operator_null,
       'x' || 1 || 2.5 AS operator_numbers, 'on ' || DATE '2026-01-02' AS operator_date
FROM dual;
```

```text
REPLACED    REMOVED   LONGER  EMPTY_SEARCH CASE_SENSITIVE FROM_NUMBER
----------- --------- ------- ------------ -------------- -----------
hell0 w0rld hell wrld heLLLLo hello        Hello          193

1 row selected.

TWO_FOR_TWO DROPS_O DIGITS_TO_NINE DROPS_B
----------- ------- -------------- -------
hippo       hipp    9KRW999        ac

1 row selected.

TWO  WITH_NULL NUMBERS OPERATOR OPERATOR_NULL OPERATOR_NUMBERS OPERATOR_DATE
---- --------- ------- -------- ------------- ---------------- -------------
abcd ab        12      abcdef   abcd          x12.5            on 02-JAN-26

1 row selected.
```

### F. CHR, ASCII and UNISTR

<!-- example: oracle -->
```sql
SELECT CHR(65) AS chr_a, CHR(97) AS chr_lower, CHR(8364) AS euro, ASCII('A') AS ascii_a, ASCII('abc') AS first_only,
       ASCII('€') AS ascii_euro, ASCII('') AS empty
FROM dual;
SELECT UNISTR('d\00e9j\00e0 vu') AS accents, UNISTR('\20AC 100') AS euro, UNISTR('a\\b') AS backslash,
       UNISTR('abc') AS plain, UNISTR('\D83D\DE00') AS pair
FROM dual;
```

```text
CHR_A CHR_LOWER EURO ASCII_A FIRST_ONLY ASCII_EURO EMPTY
----- --------- ---- ------- ---------- ---------- -----
A     a         €         65         97       8364

1 row selected.

ACCENTS EURO  BACKSLASH PLAIN PAIR
------- ----- --------- ----- ----
déjà vu € 100 a\b       abc   😀

1 row selected.
```

### G. RAWTOHEX, HEXTORAW, TO_CLOB and SYS_GUID

<!-- example: oracle -->
```sql
SELECT RAWTOHEX(HEXTORAW('48656C6C6F')) AS hex, RAWTOHEX('Hello') AS text_bytes, RAWTOHEX('é') AS utf8_bytes,
       HEXTORAW('4A4B') = HEXTORAW('4a4b') AS same_raw
FROM dual;
SELECT TO_CLOB('hello') AS clob_text, LENGTH(TO_CLOB('hello')) AS clob_len, TO_NCLOB('héllo') AS nclob_text,
       SUBSTR(TO_CLOB('abcdef'), 2, 3) AS clob_substr, INSTR(TO_CLOB('abcdef'), 'cd') AS clob_instr,
       UPPER(TO_CLOB('abc')) AS clob_upper, TO_CLOB(NULL) AS clob_null
FROM dual;
SELECT LENGTH(SYS_GUID()) AS guid_len, SYS_GUID() = SYS_GUID() AS guids_equal FROM dual;
CREATE TABLE g (id RAW(16) DEFAULT SYS_GUID(), n NUMBER);
INSERT INTO g (n) VALUES (1);
INSERT INTO g (n) VALUES (2);
SELECT COUNT(DISTINCT id) AS distinct_ids FROM g;
```

```text
HEX        TEXT_BYTES UTF8_BYTES SAME_RAW
---------- ---------- ---------- --------
48656C6C6F 48656C6C6F C3A9       true

1 row selected.

CLOB_TEXT CLOB_LEN NCLOB_TEXT CLOB_SUBSTR CLOB_INSTR CLOB_UPPER CLOB_NULL
--------- -------- ---------- ----------- ---------- ---------- ---------
hello            5 héllo      bcd                  3 ABC

1 row selected.

GUID_LEN GUIDS_EQUAL
-------- -----------
      32 false

1 row selected.

Table created.

1 row created.

1 row created.

DISTINCT_IDS
------------
           2

1 row selected.
```

### H. Where lexdb differs

<!-- example: oracle -->
```sql
SELECT LENGTH('€') AS chars, LENGTHB('€') AS bytes, SUBSTRB('héllo', 1, 3) AS first3_bytes FROM dual;
SELECT TRIM('xy' FROM 'xyabc') AS multi_char_trim FROM dual;
SELECT HEXTORAW('abc') FROM dual;
SELECT CONCAT('a', 'b', 'c') FROM dual;
```

```text
CHARS BYTES FIRST3_BYTES
----- ----- ------------
    1     1 hél

1 row selected.

MULTI_CHAR_TRIM
---------------
abc

1 row selected.

ERROR:
ORA-01722: invalid number

ERROR:
ORA-00909: invalid number of arguments
```

### I. Functions that are not available

<!-- example: oracle -->
```sql
SELECT SOUNDEX('smith') FROM dual;
SELECT VSIZE('abc') FROM dual;
SELECT DUMP('abc') FROM dual;
SELECT ORA_HASH('abc') FROM dual;
SELECT STANDARD_HASH('abc', 'SHA256') FROM dual;
SELECT NCHR(8364) FROM dual;
SELECT ASCIISTR('é') FROM dual;
```

```text
ERROR:
ORA-00904: invalid identifier

ERROR:
ORA-00904: invalid identifier

ERROR:
ORA-00904: invalid identifier

ERROR:
ORA-00904: invalid identifier

ERROR:
ORA-00904: invalid identifier

ERROR:
ORA-00904: invalid identifier

ERROR:
ORA-00904: invalid identifier
```

## See also

[Regular expression functions](functions-regex.md), [Package functions](functions-packages.md),
[Conversion functions](functions-conversion.md), [Operators](operators.md), [NULL-handling functions](functions-null.md),
[Character data types](data-types-character.md)
