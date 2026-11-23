# Operators

Arithmetic, concatenation, comparison and logical operators, and how they bind.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
+  -  *  /                      arithmetic, unary + and -
||                              concatenation
=  <>  !=  <  <=  >  >=          comparison
AND  OR  NOT
expr [ NOT ] LIKE pattern [ ESCAPE char ]
expr [ NOT ] IN ( value [, ...] | subquery )
expr [ NOT ] BETWEEN low AND high
EXISTS ( subquery )
expr comparison { ALL | ANY | SOME } ( subquery )
expr IS [ NOT ] NULL
expr IS [ NOT ] DISTINCT FROM expr         -- lexdb's addition
PRIOR expr                                  -- hierarchical queries
column (+)                                  -- the outer join marker
```

## Arguments

`+`, `-`, `*`, `/`
: Add, subtract, multiply and divide. `/` is a decimal division on `NUMBER` (`10/4` is 2.5). `DATE + n` adds days,
  `DATE - DATE` is a number of days, and an `INTERVAL` can be added to a date or timestamp. Use `MOD` and `POWER` for
  the remainder and the power; lexdb also takes `%` as a remainder, which Oracle does not have.

`||`
: Joins strings; NULL is the empty string, so `'a' || NULL` is `a`. A number is converted to text.

`=`, `<>`, `!=`, `<`, `<=`, `>`, `>=`
: Comparisons. `<>` and `!=` are the same. A comparison with NULL is unknown.

`AND`, `OR`, `NOT`
: Logic over true, false and unknown.

`LIKE`
: `%` is any run of characters, `_` one character; `ESCAPE` names an escape character. Case matters.

`IN`, `BETWEEN`, `EXISTS`, `ALL`, `ANY`, `SOME`
: A list or subquery, an inclusive range, the existence of rows, and a comparison with all or some rows of a
  subquery.

`IS [NOT] NULL`
: The test for NULL. Remember that `''` is NULL.

`IS [NOT] DISTINCT FROM`
: A comparison in which two NULLs are equal. Oracle 23ai does not have it; lexdb takes it in every dialect.

## Remarks

- Precedence, from the tightest: unary `+` and `-`, `PRIOR`; `*` and `/`; binary `+`, `-` and `||`; the comparisons,
  `IS NULL`, `LIKE`, `BETWEEN`, `IN`; `NOT`; `AND`; `OR`. Use brackets when in doubt.
- A comparison is a condition, not a value: in a select list use `CASE WHEN ... THEN ... END`, or `TO_BOOLEAN`. A
  `BOOLEAN` column can be a condition on its own.
- Comparing a string with a number in `WHERE` converts the string: `'12' = 12` is true, and `'abc' = 12` is
  ORA-01722.
- `NOT IN` with a NULL in the list is never true.

## Differences from Oracle

- `IS [NOT] DISTINCT FROM` is a lexdb addition (Oracle 23ai has none).
- `^=` (not equal) is ORA-00900. `%` works as a remainder and `**` is ORA-00900.
- A comparison of a string with a number inside a `CASE WHEN` in a select list is ORA-00900 (example H); the same
  comparison in `WHERE` converts the string.

## Examples

### A. Arithmetic

<!-- example: oracle -->
```sql
SELECT 2 + 3 * 4 AS a, (2 + 3) * 4 AS b, -2 + 5 AS c, 10 - 4 - 3 AS d, 10 / 4 AS e, MOD(10, 4) AS f,
       POWER(2, 10) AS g FROM dual;
SELECT 5 % 2 AS remainder FROM dual;
SELECT 2 ** 3 FROM dual;
```

```text
 A  B C D   E F    G
-- -- - - --- - ----
14 20 3 3 2.5 2 1024

1 row selected.

REMAINDER
---------
        1

1 row selected.

ERROR:
ORA-00900: invalid SQL statement
```

### B. Dates

<!-- example: oracle -->
```sql
SELECT TO_CHAR(DATE '2026-03-15' + 1, 'YYYY-MM-DD') AS next_day,
       TO_CHAR(DATE '2026-03-15' + 0.5, 'YYYY-MM-DD HH24:MI') AS half_day,
       DATE '2026-03-20' - DATE '2026-03-15' AS days_apart FROM dual;
```

```text
NEXT_DAY   HALF_DAY         DAYS_APART
---------- ---------------- ----------
2026-03-16 2026-03-15 12:00          5

1 row selected.
```

### C. Concatenation

<!-- example: oracle -->
```sql
SELECT 'a' || 'b' AS ab, 'n=' || 5 AS with_number, 'x' || NULL AS with_null, 'a' || NULL || 'b' AS skipped FROM dual;
```

```text
AB WITH_NUMBER WITH_NULL SKIPPED
-- ----------- --------- -------
ab n=5         x         ab

1 row selected.
```

### D. Comparison and logic

<!-- example: oracle -->
```sql
SELECT CASE WHEN 1 = 1 AND 2 > 1 THEN 'y' ELSE 'n' END AS and_,
       CASE WHEN NOT 1 = 2 THEN 'y' ELSE 'n' END AS not_,
       CASE WHEN 1 = 2 OR 3 <> 4 THEN 'y' ELSE 'n' END AS or_,
       CASE WHEN 1 != 2 THEN 'y' ELSE 'n' END AS bang_equal
FROM dual;
SELECT CASE WHEN 1 ^= 2 THEN 'y' ELSE 'n' END AS caret_equal FROM dual;
```

```text
AND_ NOT_ OR_ BANG_EQUAL
---- ---- --- ----------
y    y    y   y

1 row selected.

ERROR:
ORA-00900: invalid SQL statement
```

### E. NULL

<!-- example: oracle -->
```sql
SELECT CASE WHEN NULL = NULL THEN 'y' ELSE 'n' END AS equals_null,
       CASE WHEN NULL IS NULL THEN 'y' ELSE 'n' END AS is_null,
       CASE WHEN '' IS NULL THEN 'y' ELSE 'n' END AS empty_is_null,
       CASE WHEN NULL IS NOT DISTINCT FROM NULL THEN 'y' ELSE 'n' END AS not_distinct,
       CASE WHEN 1 IS DISTINCT FROM NULL THEN 'y' ELSE 'n' END AS distinct_
FROM dual;
```

```text
EQUALS_NULL IS_NULL EMPTY_IS_NULL NOT_DISTINCT DISTINCT_
----------- ------- ------------- ------------ ---------
n           y       y             y            y

1 row selected.
```

### F. IN, BETWEEN, ALL, ANY, EXISTS

<!-- example: oracle -->
```sql
SELECT CASE WHEN 2 IN (1, 2, 3) THEN 'y' ELSE 'n' END AS in_,
       CASE WHEN 5 NOT IN (1, 2, 3) THEN 'y' ELSE 'n' END AS not_in,
       CASE WHEN 5 BETWEEN 1 AND 10 THEN 'y' ELSE 'n' END AS between_,
       CASE WHEN 1 NOT IN (2, NULL) THEN 'y' ELSE 'n' END AS not_in_with_null,
       CASE WHEN 3 > ALL (SELECT 1 FROM dual UNION ALL SELECT 2 FROM dual) THEN 'y' ELSE 'n' END AS all_,
       CASE WHEN 3 > ANY (SELECT 5 FROM dual) THEN 'y' ELSE 'n' END AS any_,
       CASE WHEN EXISTS (SELECT 1 FROM dual WHERE 1 = 0) THEN 'y' ELSE 'n' END AS exists_
FROM dual;
```

```text
IN_ NOT_IN BETWEEN_ NOT_IN_WITH_NULL ALL_ ANY_ EXISTS_
--- ------ -------- ---------------- ---- ---- -------
y   y      y        n                y    n    n

1 row selected.
```

### G. LIKE

<!-- example: oracle -->
```sql
SELECT CASE WHEN 'Abc' LIKE 'a%' THEN 'y' ELSE 'n' END AS case_matters,
       CASE WHEN 'Abc' LIKE 'A_c' THEN 'y' ELSE 'n' END AS underscore,
       CASE WHEN 'a%b' LIKE 'a!%b' ESCAPE '!' THEN 'y' ELSE 'n' END AS escaped,
       CASE WHEN 'abc' NOT LIKE 'x%' THEN 'y' ELSE 'n' END AS not_like
FROM dual;
```

```text
CASE_MATTERS UNDERSCORE ESCAPED NOT_LIKE
------------ ---------- ------- --------
n            y          y       y

1 row selected.
```

### H. Strings and numbers

<!-- example: oracle -->
```sql
SELECT 'converted' AS result FROM dual WHERE '12' = 12;
SELECT 'x' FROM dual WHERE 'abc' = 12;
SELECT CASE WHEN '12' = 12 THEN 'equal' ELSE 'different' END AS in_a_case FROM dual;
```

```text
RESULT
---------
converted

1 row selected.

ERROR:
ORA-01722: invalid number

ERROR:
ORA-00900: invalid SQL statement
```

### I. The outer join marker

<!-- example: oracle -->
```sql
CREATE TABLE a (id NUMBER, v VARCHAR2(5));
CREATE TABLE b (id NUMBER, w VARCHAR2(5));
INSERT INTO a VALUES (1, 'a1');
INSERT INTO a VALUES (2, 'a2');
INSERT INTO b VALUES (1, 'b1');
SELECT a.id, a.v, b.w FROM a, b WHERE a.id = b.id (+) ORDER BY a.id;
```

```text
Table created.

Table created.

1 row created.

1 row created.

1 row created.

ID V  W
-- -- --
 1 a1 b1
 2 a2

2 rows selected.
```

## See also

[Numeric types](data-types-number.md), [Character types](data-types-character.md),
[Date and time types](data-types-datetime.md), [Hierarchical queries](hierarchical-queries.md)
