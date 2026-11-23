# Regular expression functions

`REGEXP_LIKE`, `REGEXP_REPLACE`, `REGEXP_SUBSTR`, `REGEXP_INSTR` and `REGEXP_COUNT`.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
REGEXP_LIKE ( source_char, pattern [, match_param ] )
REGEXP_REPLACE ( source_char, pattern [, replace_string [, position [, occurrence [, match_param ] ] ] ] )
REGEXP_SUBSTR ( source_char, pattern [, position [, occurrence [, match_param [, subexpr ] ] ] ] )
REGEXP_INSTR ( source_char, pattern [, position [, occurrence [, return_option [, match_param [, subexpr ] ] ] ] ] )
REGEXP_COUNT ( source_char, pattern [, position [, match_param ] ] )
```

The fuzzy matching functions of the `UTL_MATCH` package are on the [package functions page](functions-packages.md).

## Functions

`REGEXP_LIKE`
: A condition: true when *source_char* contains a match of *pattern*. It is not a value, so it appears in `WHERE`,
  `HAVING`, `CASE WHEN` and `ON`. Selecting it directly gives `true` or `false` in lexdb's output.

`REGEXP_REPLACE`
: *source_char* with matches of *pattern* replaced by *replace_string*. *position* is where the search starts and
  *occurrence* chooses the match (0, the default, replaces all). `\1` to `\9` in *replace_string* are the groups of
  the pattern. A NULL *replace_string* gives NULL.

`REGEXP_SUBSTR`
: The text of the first match of *pattern*, or NULL. *position*, *occurrence*, *match_param* and *subexpr* are
  accepted but not used (see Differences).

`REGEXP_INSTR`
: The position of the match of *pattern*, or 0. *return_option* 0 gives the position of the start and 1 the position
  after the match.

`REGEXP_COUNT`
: The number of matches of *pattern*, counted from *position*; 0 if there are none.

## Remarks

- The pattern syntax is extended regular expressions with the usual Perl-style shortcuts `\d`, `\w`, `\s` and their
  negations, and POSIX classes such as `[[:digit:]]`, `[[:alpha:]]`, `[[:space:]]` and `[[:upper:]]`. Look-ahead and
  look-behind are not supported (neither are they in Oracle).
- *match_param* is a string of flags: `i` ignore case, `c` match case (the default), `m` multiline (`^` and `$` match
  at line ends), `n` and `x` (ignore white space in the pattern). An unknown flag is ORA-01722.
- An invalid pattern is ORA-20000 with the parser's message.
- A NULL source gives NULL (`REGEXP_COUNT`) or false.
- *position* 0 or below is ORA-01722.

## Differences from Oracle

- `REGEXP_SUBSTR` uses only its first two arguments. `REGEXP_SUBSTR('abc123def456', '[0-9]+', 1, 2)` gives `123`
  (Oracle: `456`); the *position* in `REGEXP_SUBSTR('abc123def456', '[0-9]+', 5)` is ignored; the flag `i` and the
  *subexpr* have no effect: `REGEXP_SUBSTR('ABC', 'b', 1, 1, 'i')` is NULL (Oracle: `B`) and the subexpression 2
  of `([a-z]+)([0-9]+)` returns the whole match. `REGEXP_INSTR` and `REGEXP_COUNT` do use their arguments.
- `REGEXP_REPLACE` needs a *replace_string*: `REGEXP_REPLACE('abc', 'b')` is ORA-00904 (Oracle removes the matches).
- The period matches a line feed unless the `n` flag is given, and `n` has the opposite effect: Oracle's period does
  not match a line feed, and `n` makes it do so.
- A wrong *match_param* is ORA-01722; Oracle gives ORA-12714.
- `REGEXP_COUNT('hello', '')` is NULL.

## Examples

### A. REGEXP_LIKE in WHERE and CASE

<!-- example: oracle -->
```sql
CREATE TABLE r (id NUMBER, v VARCHAR2(40));
INSERT INTO r VALUES (1, 'alpha 12');
INSERT INTO r VALUES (2, 'Beta');
INSERT INTO r VALUES (3, 'line1' || CHR(10) || 'line2');
INSERT INTO r VALUES (4, 'gamma-7');
SELECT id FROM r WHERE REGEXP_LIKE(v, '[0-9]') ORDER BY id;
SELECT id FROM r WHERE NOT REGEXP_LIKE(v, '^[a-z]') ORDER BY id;
SELECT id FROM r WHERE REGEXP_LIKE(v, '^beta$', 'i') ORDER BY id;
SELECT id FROM r WHERE REGEXP_LIKE(v, '^beta$') ORDER BY id;
SELECT CASE WHEN REGEXP_LIKE('abc123', '^[a-z]+[0-9]+$') THEN 'yes' ELSE 'no' END AS matches,
       CASE WHEN REGEXP_LIKE('ABC', '^abc$', 'c') THEN 'yes' ELSE 'no' END AS match_case,
       CASE WHEN REGEXP_LIKE('abc', 'a b c', 'x') THEN 'yes' ELSE 'no' END AS ignore_blanks
FROM dual;
```

```text
Table created.

1 row created.

1 row created.

1 row created.

1 row created.

ID
--
 1
 3
 4

3 rows selected.

ID
--
 2

1 row selected.

ID
--
 2

1 row selected.

no rows selected

MATCHES MATCH_CASE IGNORE_BLANKS
------- ---------- -------------
yes     no         yes

1 row selected.
```

### B. The match parameter: multiline and the period

<!-- example: oracle -->
```sql
SELECT id FROM r WHERE REGEXP_LIKE(v, '^line2$') ORDER BY id;
SELECT id FROM r WHERE REGEXP_LIKE(v, '^line2$', 'm') ORDER BY id;
SELECT id FROM r WHERE REGEXP_LIKE(v, 'line1.line2') ORDER BY id;
SELECT id FROM r WHERE REGEXP_LIKE(v, 'line1.line2', 'n') ORDER BY id;
```

```text
no rows selected

ID
--
 3

1 row selected.

ID
--
 3

1 row selected.

no rows selected
```

### C. REGEXP_REPLACE

<!-- example: oracle -->
```sql
SELECT REGEXP_REPLACE('hello world', 'o', '0') AS all_matches, REGEXP_REPLACE('hello world', 'o', '0', 1, 1) AS first,
       REGEXP_REPLACE('hello world', 'o', '0', 1, 2) AS second, REGEXP_REPLACE('hello world', 'o', '0', 6) AS from_6,
       REGEXP_REPLACE('Hello', 'h', 'j', 1, 0, 'i') AS ignore_case, REGEXP_REPLACE('a  b   c', ' +', ' ') AS squeeze
FROM dual;
SELECT REGEXP_REPLACE('John Smith', '(\w+) (\w+)', '\2, \1') AS swapped, REGEXP_REPLACE('abc', '(b)', '[\1]') AS group_ref,
       REGEXP_REPLACE('abc', 'b', NULL) AS null_replacement, REGEXP_REPLACE('a.b', '\.', '\\') AS backslash
FROM dual;
SELECT REGEXP_REPLACE('abc123', '[[:digit:]]+', '#') AS digits, REGEXP_REPLACE('abc 123', '[[:space:]]', '_') AS space,
       REGEXP_REPLACE('Ab1', '[[:upper:]]', '*') AS upper, REGEXP_REPLACE('a1b2', '\d', '#') AS shortcut,
       REGEXP_REPLACE('abc', '^', '>') AS at_start, REGEXP_REPLACE('abc', '$', '<') AS at_end
FROM dual;
```

```text
ALL_MATCHES FIRST       SECOND      FROM_6      IGNORE_CASE SQUEEZE
----------- ----------- ----------- ----------- ----------- -------
hell0 w0rld hell0 world hello w0rld hello w0rld jello       a b c

1 row selected.

SWAPPED     GROUP_REF NULL_REPLACEMENT BACKSLASH
----------- --------- ---------------- ---------
Smith, John a[b]c                      a\b

1 row selected.

DIGITS SPACE   UPPER SHORTCUT AT_START AT_END
------ ------- ----- -------- -------- ------
abc#   abc_123 *b1   a#b#     >abc     abc<

1 row selected.
```

### D. REGEXP_SUBSTR

<!-- example: oracle -->
```sql
SELECT REGEXP_SUBSTR('abc123def456', '[0-9]+') AS first_number, REGEXP_SUBSTR('abc', '[0-9]+') AS no_match,
       REGEXP_SUBSTR('2026-11-23', '[^-]+') AS first_part, REGEXP_SUBSTR('foo bar', '\w+$') AS last_word,
       REGEXP_SUBSTR('abc123', '([a-z]+)([0-9]+)') AS whole_match, REGEXP_SUBSTR(NULL, 'a') AS null_in
FROM dual;
```

```text
FIRST_NUMBER NO_MATCH FIRST_PART LAST_WORD WHOLE_MATCH NULL_IN
------------ -------- ---------- --------- ----------- -------
123                   2026       bar       abc123

1 row selected.
```

### E. REGEXP_SUBSTR with arguments that lexdb ignores

<!-- example: oracle -->
```sql
SELECT REGEXP_SUBSTR('abc123def456', '[0-9]+', 1, 2) AS nth_match FROM dual;
SELECT REGEXP_SUBSTR('abc123def456', '[0-9]+', 5) AS from_position_5 FROM dual;
SELECT REGEXP_SUBSTR('ABC', 'b', 1, 1, 'i') AS ignore_case FROM dual;
SELECT REGEXP_SUBSTR('abc123', '([a-z]+)([0-9]+)', 1, 1, NULL, 2) AS subexpression_2 FROM dual;
```

```text
NTH_MATCH
---------
123

1 row selected.

FROM_POSITION_5
---------------
123

1 row selected.

IGNORE_CASE
-----------


1 row selected.

SUBEXPRESSION_2
---------------
abc123

1 row selected.
```

### F. REGEXP_INSTR

<!-- example: oracle -->
```sql
SELECT REGEXP_INSTR('abc123def456', '[0-9]+') AS first_start, REGEXP_INSTR('abc123def456', '[0-9]+', 1, 2) AS second_start,
       REGEXP_INSTR('abc123def456', '[0-9]+', 1, 1, 1) AS first_end, REGEXP_INSTR('abc123def456', '[0-9]+', 1, 2, 1) AS second_end,
       REGEXP_INSTR('abc', '[0-9]') AS none, REGEXP_INSTR('ABC', 'b', 1, 1, 0, 'i') AS ignore_case
FROM dual;
```

```text
FIRST_START SECOND_START FIRST_END SECOND_END NONE IGNORE_CASE
----------- ------------ --------- ---------- ---- -----------
          4           10         7         13    0           2

1 row selected.
```

### G. REGEXP_COUNT

<!-- example: oracle -->
```sql
SELECT REGEXP_COUNT('abcabcabc', 'abc') AS three, REGEXP_COUNT('abcabcabc', 'abc', 4) AS from_4,
       REGEXP_COUNT('ABCabc', 'abc') AS case_sensitive, REGEXP_COUNT('ABCabc', 'abc', 1, 'i') AS ignore_case,
       REGEXP_COUNT('a1b22c333', '[0-9]+') AS numbers, REGEXP_COUNT('aaa', 'aa') AS no_overlap,
       REGEXP_COUNT('abc', 'x') AS none, REGEXP_COUNT(NULL, 'a') AS null_in
FROM dual;
```

```text
THREE FROM_4 CASE_SENSITIVE IGNORE_CASE NUMBERS NO_OVERLAP NONE NULL_IN
----- ------ -------------- ----------- ------- ---------- ---- -------
    3      2              1           2       3          1    0

1 row selected.
```

### H. Errors

<!-- example: oracle -->
```sql
SELECT REGEXP_REPLACE('abc', 'b') FROM dual;
SELECT REGEXP_SUBSTR('abc', '(') FROM dual;
SELECT CASE WHEN REGEXP_LIKE('abc', 'a', 'z') THEN 1 END FROM dual;
SELECT REGEXP_REPLACE('abc', 'x', 'y', 0) FROM dual;
SELECT REGEXP_REPLACE('a1b2', '(?<=a)1', 'X') FROM dual;
```

```text
ERROR:
ORA-00904: invalid identifier

ERROR:
ORA-20000: invalid regular expression: error parsing regexp: missing closing ): `(?s)(()`

ERROR:
ORA-01722: invalid number

ERROR:
ORA-01722: invalid number

ERROR:
ORA-20000: invalid regular expression: error parsing regexp: invalid named capture: `(?<=a)1`
```

## See also

[Character functions](functions-character.md), [Package functions](functions-packages.md), [Operators](operators.md),
[SELECT](select.md)
