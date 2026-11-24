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
  the pattern. A NULL *replace_string*, or none, removes the
  matches.

`REGEXP_SUBSTR`
: The text of a match of *pattern*, or NULL. *position* is where the search starts, *occurrence* chooses the match
  (the first by default), *match_param* is the flags, and *subexpr* returns the text of that parenthesised group
  of the match instead of the whole match.

`REGEXP_INSTR`
: The position of the match of *pattern*, or 0. *return_option* 0 gives the position of the start and 1 the position
  after the match. *subexpr* gives the position of that group.

`REGEXP_COUNT`
: The number of matches of *pattern*, counted from *position*; 0 if there are none.

## Remarks

- The pattern syntax is extended regular expressions with the usual Perl-style shortcuts `\d`, `\w`, `\s` and their
  negations, and POSIX classes such as `[[:digit:]]`, `[[:alpha:]]`, `[[:space:]]` and `[[:upper:]]`. Look-ahead and
  look-behind are not supported (neither are they in Oracle).
- *match_param* is a string of flags, read as Oracle reads them: `i` ignore case, `c` match case (the default), `n`
  the period matches a line feed (by default it does not), `m` multiline (`^` and `$` match at line ends) and `x`
  ignore white space in the pattern. An unknown flag is ORA-01760.
- An invalid pattern has Oracle's error: ORA-12725 for unmatched parentheses, ORA-12726 for an unmatched bracket or
  any other pattern the engine does not read (look-behind, say), ORA-12727 for a back reference in the pattern
  (`(a)\1`: the engine has none), ORA-12728 for an invalid range, ORA-12729 for an invalid character class and
  ORA-12732 for an invalid repeat count.
- A NULL source gives NULL (`REGEXP_COUNT`) or false.
- *position*, *occurrence* and *return_option* out of range (position 0 or below, say) are ORA-01428.

## Differences from Oracle

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

no rows selected

ID
--
 3

1 row selected.
```

### C. REGEXP_REPLACE

<!-- example: oracle -->
```sql
SELECT REGEXP_REPLACE('hello world', 'o', '0') AS all_matches, REGEXP_REPLACE('hello world', 'o', '0', 1, 1) AS first,
       REGEXP_REPLACE('hello world', 'o', '0', 1, 2) AS second, REGEXP_REPLACE('hello world', 'o', '0', 6) AS from_6,
       REGEXP_REPLACE('Hello', 'h', 'j', 1, 0, 'i') AS ignore_case, REGEXP_REPLACE('a  b   c', ' +', ' ') AS squeeze
FROM dual;
SELECT REGEXP_REPLACE('John Smith', '(\w+) (\w+)', '\2, \1') AS swapped, REGEXP_REPLACE('abc', '(b)', '[\1]') AS group_ref,
       REGEXP_REPLACE('abc', 'b', NULL) AS null_replacement, REGEXP_REPLACE('abc', 'b') AS no_replacement,
       REGEXP_REPLACE('a.b', '\.', '\\') AS backslash
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

SWAPPED     GROUP_REF NULL_REPLACEMENT NO_REPLACEMENT BACKSLASH
----------- --------- ---------------- -------------- ---------
Smith, John a[b]c     ac               ac             a\b

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

### E. REGEXP_SUBSTR with position, occurrence, match parameter and subexpression

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
456

1 row selected.

FROM_POSITION_5
---------------
23

1 row selected.

IGNORE_CASE
-----------
B

1 row selected.

SUBEXPRESSION_2
---------------
123

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
SELECT REGEXP_SUBSTR('abc', '(') FROM dual;
SELECT CASE WHEN REGEXP_LIKE('abc', 'a', 'z') THEN 1 END FROM dual;
SELECT REGEXP_REPLACE('abc', 'x', 'y', 0) FROM dual;
SELECT REGEXP_REPLACE('a1b2', '(?<=a)1', 'X') FROM dual;
SELECT REGEXP_LIKE('aa', '(a)\1') FROM dual;
```

```text
ERROR:
ORA-12725: unmatched parentheses in regular expression

ERROR:
ORA-01760: illegal argument for function

ERROR:
ORA-01428: Argument 0 is out of range.

ERROR:
ORA-12726: invalid regular expression

ERROR:
ORA-12727: invalid back reference in regular expression
```

## See also

[Character functions](functions-character.md), [Package functions](functions-packages.md), [Operators](operators.md),
[SELECT](select.md)
