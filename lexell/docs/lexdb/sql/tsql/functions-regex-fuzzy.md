# Regular expression and fuzzy matching functions (Transact-SQL)

Functions that match text against a regular expression, and that measure how much two strings differ.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2025 (these functions are new in it; SQL Server 2022 has none).

## Syntax

```
REGEXP_LIKE ( string, pattern [, flags ] )
REGEXP_REPLACE ( string, pattern, replacement [, start [, occurrence [, flags ] ] ] ) → varchar | nvarchar
REGEXP_SUBSTR ( string, pattern [, start [, occurrence [, flags [, group ] ] ] ] ) → varchar | nvarchar
REGEXP_INSTR ( string, pattern [, start [, occurrence [, return_option [, flags [, group ] ] ] ] ] ) → int
REGEXP_COUNT ( string, pattern [, start [, flags ] ] ) → int

EDIT_DISTANCE ( string1, string2 [, max_distance ] ) → int
EDIT_DISTANCE_SIMILARITY ( string1, string2 ) → int
JARO_WINKLER_DISTANCE ( string1, string2 ) → float
JARO_WINKLER_SIMILARITY ( string1, string2 ) → int
```

## Functions

`REGEXP_LIKE`
: A predicate: true when the string contains a match of the pattern. Like `LIKE` and `EXISTS`, it can stand where a
  condition does (`WHERE`, `HAVING`, `CASE WHEN`, `IIF`), but not in a select list by itself (example A).

`REGEXP_REPLACE`
: The string with the matches of *pattern* replaced by *replacement*, from character *start* (default 1). *occurrence*
  names the match to replace; 0, the default, replaces every one. The replacement refers to a captured group as `\1`
  to `\9`.

`REGEXP_SUBSTR`
: The text of the *occurrence*th match (default 1) from *start*, or NULL when there is none. With *group* it is the
  text that capture group matched.

`REGEXP_INSTR`
: The position of the *occurrence*th match from *start*, or 0. *return_option* 0 (the default) gives the position
  of its first character, 1 the position after its last.

`REGEXP_COUNT`
: The number of matches from *start*.

`EDIT_DISTANCE`
: The fewest insertions, deletions, substitutions and swaps of two neighbouring characters (each one edit) that turn
  one string into the other. The comparison follows the collation, which is case-insensitive here. With
  *max_distance*, a distance above it is reported as *max_distance* + 1.

`EDIT_DISTANCE_SIMILARITY`
: How alike two strings are, from 0 (nothing in common) to 100 (equal), as `(1 - distance / longer length) * 100`.

`JARO_WINKLER_DISTANCE`
: The Jaro-Winkler distance, from 0.0 (equal) to 1.0.

`JARO_WINKLER_SIMILARITY`
: The Jaro-Winkler similarity, from 0 (nothing in common) to 100 (equal).

## Remarks

- The patterns are RE2 regular expressions, as in SQL Server 2025: `\d`, `\w`, `\s`, character classes, groups,
  `*`, `+`, `?`, `{n,m}`, `|`, `^` and `$`. A pattern that RE2 refuses is error 19300 (with the specific errors 19307
  for an unexpected `)`, 19308 for a missing `]` or `)`, and 19309 for a trailing backslash).
- *flags* is a string of these letters: `i` ignores case, `c` respects it (the default; the last of the two wins),
  `s` lets `.` match a line feed, `m` makes `^` and `$` match at each line. Any other letter is error 19303.
- With a NULL string or pattern the result is NULL.
- The fuzzy matching functions do not take a string with a `SQL_` collation, which is the database's default
  (`SQL_Latin1_General_CP1_CI_AS`): they fail with error 9847. Give the first argument a Windows collation with
  `COLLATE Latin1_General_100_CI_AS` (examples F to H).

## Differences from SQL Server

- **`REGEXP_REPLACE` without a replacement never answers** (SQL Server: the matches are removed):
  `REGEXP_REPLACE('abc', 'b')` hangs the session. Always give the third argument, `''` to remove the matches.
- The replacement refers to a group only as `\1` to `\9`; `$1` is written out as it stands.

## Examples

### A. REGEXP_LIKE

A condition, not a value: in a select list it is error 156.

<!-- example: tsql -->
```sql
SELECT CASE WHEN REGEXP_LIKE('abc123', '^[a-z]+[0-9]+$') THEN 'match' ELSE 'no match' END AS pattern_match,
       CASE WHEN REGEXP_LIKE('ABC', 'abc') THEN 'match' ELSE 'no match' END AS case_sensitive,
       CASE WHEN REGEXP_LIKE('ABC', 'abc', 'i') THEN 'match' ELSE 'no match' END AS ignore_case;
GO
SELECT name FROM (VALUES ('apple'), ('banana'), ('cherry')) AS v(name) WHERE REGEXP_LIKE(name, '^[ab]') ORDER BY name;
GO
SELECT REGEXP_LIKE('abc', 'b') AS by_itself;
```

```text
pattern_match case_sensitive ignore_case
------------- -------------- -----------
match         no match       match

(1 row affected)

name
------
apple
banana

(2 rows affected)

Msg 156, Level 15, State 1, Line 1
Incorrect syntax near the keyword 'regexp_like'.
```

### B. REGEXP_REPLACE

<!-- example: tsql -->
```sql
SELECT REGEXP_REPLACE('a1b22c333', '[0-9]+', '#') AS all_matches, REGEXP_REPLACE('a1b22c333', '[0-9]+', '#', 1, 2) AS second_only,
       REGEXP_REPLACE('John Smith', '(\w+) (\w+)', '\2, \1') AS groups, REGEXP_REPLACE('  a   b  ', '\s+', ' ') AS spaces,
       REGEXP_REPLACE('Hello World', 'O', '0', 1, 0, 'i') AS ignore_case, REGEXP_REPLACE('abc', 'b', '') AS removed,
       REGEXP_REPLACE('abc', '(a)(b)', '$2$1') AS dollar_not_a_group;
```

```text
all_matches second_only groups      spaces ignore_case removed dollar_not_a_group
----------- ----------- ----------- ------ ----------- ------- ------------------
a#b#c#      a1b#c333    Smith, John  a b   Hell0 W0rld ac      $2$1c

(1 row affected)
```

### C. REGEXP_SUBSTR

<!-- example: tsql -->
```sql
SELECT REGEXP_SUBSTR('abc123def456', '[0-9]+') AS first_number, REGEXP_SUBSTR('abc123def456', '[0-9]+', 1, 2) AS second_number,
       REGEXP_SUBSTR('abc', '[0-9]+') AS none, REGEXP_SUBSTR('user@example.com', '[^@]+$') AS domain,
       REGEXP_SUBSTR('2026-03-05', '(\d+)-(\d+)-(\d+)', 1, 1, 'i', 2) AS month_group, REGEXP_SUBSTR('abcabc', 'b', 3) AS from_3;
```

```text
first_number second_number none domain      month_group from_3
------------ ------------- ---- ----------- ----------- ------
123          456           NULL example.com 03          b

(1 row affected)
```

### D. REGEXP_INSTR

<!-- example: tsql -->
```sql
SELECT REGEXP_INSTR('abcabc', 'b') AS first, REGEXP_INSTR('abcabc', 'b', 3) AS from_3, REGEXP_INSTR('abcabc', 'b', 1, 2) AS second,
       REGEXP_INSTR('abcabc', 'bc', 1, 1, 1) AS after_the_match, REGEXP_INSTR('abc', 'z') AS none,
       REGEXP_INSTR(NULL, 'b') AS null_string;
```

```text
first from_3 second after_the_match none null_string
----- ------ ------ --------------- ---- -----------
2     5      5      4               0    NULL

(1 row affected)
```

### E. REGEXP_COUNT

<!-- example: tsql -->
```sql
SELECT name, REGEXP_COUNT(name, '[aeiou]') AS vowels, REGEXP_COUNT(name, 'A', 1, 'i') AS letter_a
FROM (VALUES ('banana'), ('sky'), ('queue')) AS v(name) ORDER BY name;
```

```text
name   vowels letter_a
------ ------ --------
banana 3      3
queue  4      0
sky    0      0

(3 rows affected)
```

### F. EDIT_DISTANCE

The default collation is refused; a Windows collation works.

<!-- example: tsql -->
```sql
SELECT EDIT_DISTANCE('kitten', 'sitting') AS default_collation;
GO
SELECT EDIT_DISTANCE('kitten' COLLATE Latin1_General_100_CI_AS, 'sitting') AS distance,
       EDIT_DISTANCE('abc' COLLATE Latin1_General_100_CI_AS, 'ABC') AS ignores_case,
       EDIT_DISTANCE('abc' COLLATE Latin1_General_100_CI_AS, 'abc') AS equal,
       EDIT_DISTANCE('kitten' COLLATE Latin1_General_100_CI_AS, 'sitting', 2) AS past_max_2,
       EDIT_DISTANCE('kitten' COLLATE Latin1_General_100_CI_AS, 'sitting', 1) AS past_max_1,
       EDIT_DISTANCE('kitten' COLLATE Latin1_General_100_CI_AS, 'sitting', 5) AS within_max,
       EDIT_DISTANCE('ab' COLLATE Latin1_General_100_CI_AS, 'ba') AS swap,
       EDIT_DISTANCE(NULL, 'a' COLLATE Latin1_General_100_CI_AS) AS null_argument;
```

```text
Msg 9847, Level 16, State 1, Line 1
The fuzzy string matching function does not support SQL_* collations. Use a Windows collation instead.
distance ignores_case equal past_max_2 past_max_1 within_max swap null_argument
-------- ------------ ----- ---------- ---------- ---------- ---- -------------
3        0            0     3          2          3          1    NULL

(1 row affected)
```

### G. EDIT_DISTANCE_SIMILARITY

<!-- example: tsql -->
```sql
SELECT EDIT_DISTANCE_SIMILARITY('kitten' COLLATE Latin1_General_100_CI_AS, 'sitting') AS similar,
       EDIT_DISTANCE_SIMILARITY('abc' COLLATE Latin1_General_100_CI_AS, 'abc') AS equal,
       EDIT_DISTANCE_SIMILARITY('abc' COLLATE Latin1_General_100_CI_AS, 'xyz') AS nothing_in_common;
```

```text
similar equal nothing_in_common
------- ----- -----------------
57      100   0

(1 row affected)
```

### H. Jaro-Winkler

<!-- example: tsql -->
```sql
SELECT JARO_WINKLER_DISTANCE('martha' COLLATE Latin1_General_100_CI_AS, 'marhta') AS distance,
       JARO_WINKLER_SIMILARITY('martha' COLLATE Latin1_General_100_CI_AS, 'marhta') AS similarity,
       JARO_WINKLER_SIMILARITY('abc' COLLATE Latin1_General_100_CI_AS, 'xyz') AS nothing_in_common,
       JARO_WINKLER_DISTANCE('abc' COLLATE Latin1_General_100_CI_AS, 'abc') AS equal;
```

```text
distance            similarity nothing_in_common equal
------------------- ---------- ----------------- -----
0.03888888888888886 96         0                 0.0

(1 row affected)
```

### I. Errors in patterns and flags

<!-- example: tsql -->
```sql
SELECT CASE WHEN REGEXP_LIKE('abc', '[') THEN 1 ELSE 0 END AS missing_bracket;
GO
SELECT REGEXP_COUNT('abc', '(') AS missing_paren;
GO
SELECT REGEXP_COUNT('abc', 'b', 1, 'z') AS bad_flag;
```

```text
Msg 19308, Level 16, State 1, Line 1
Missing ']' in the Pattern [.
Msg 19308, Level 16, State 1, Line 1
Missing ')' in the Pattern (.
Msg 19303, Level 16, State 1, Line 1
Invalid flag provided. 'z' are not valid flags. Only {c,i,s,m} flags are valid.
```

## See also

[String functions](functions-string.md) · [Logical functions](functions-logical.md) · [SELECT](select.md)
