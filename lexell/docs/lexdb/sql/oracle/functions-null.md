# NULL-handling and conditional functions

`NVL`, `NVL2`, `NULLIF`, `COALESCE`, `DECODE`, `GREATEST`, `LEAST` and the `CASE` expression.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
NVL ( expr1, expr2 )
NVL2 ( expr1, expr2, expr3 )
NULLIF ( expr1, expr2 )
COALESCE ( expr1, expr2 [, expr ]... )
DECODE ( expr, search, result [, search, result ]... [, default ] )
GREATEST ( expr [, expr ]... )
LEAST ( expr [, expr ]... )

CASE expr WHEN value THEN result [ WHEN ... THEN ... ] [ ELSE result ] END
CASE WHEN condition THEN result [ WHEN ... THEN ... ] [ ELSE result ] END
```

## Functions

`NVL`
: *expr2* when *expr1* is NULL, else *expr1*. Remember that the empty string is NULL.

`NVL2`
: *expr2* when *expr1* is not NULL, else *expr3*.

`NULLIF`
: NULL when the two values are equal, else *expr1*.

`COALESCE`
: The first of the arguments that is not NULL.

`DECODE`
: Compares *expr* with each *search* in turn and gives the matching *result*, else *default* (NULL if none). Two NULLs
  match in `DECODE`.

`GREATEST`, `LEAST`
: The largest and smallest of the arguments, numbers, strings or dates. NULL if any argument is NULL.

`CASE`
: The simple form compares *expr* with each `WHEN` value; the searched form takes conditions. Without `ELSE`, the
  result is NULL when nothing matches. `CASE` is an expression: it can appear anywhere a value can.

## Remarks

- `COALESCE` and `CASE` evaluate their arguments in order and stop at the first that decides the result.
- `LNNVL` and `NANVL` do not exist (ORA-00904).

## Differences from Oracle

- `LNNVL` and `NANVL` are not available.

## Examples

### A. NVL, NVL2, NULLIF and COALESCE

<!-- example: oracle -->
```sql
SELECT NVL(NULL, 'default') AS nvl_null, NVL('x', 'default') AS nvl_value, NVL('', 'was empty') AS nvl_empty,
       NVL2('x', 'has value', 'is null') AS nvl2_a, NVL2(NULL, 'has value', 'is null') AS nvl2_b,
       NULLIF(1, 1) AS nullif_same, NULLIF(1, 2) AS nullif_different,
       COALESCE(NULL, NULL, 3, 4) AS coalesced
FROM dual;
```

```text
NVL_NULL NVL_VALUE NVL_EMPTY NVL2_A    NVL2_B  NULLIF_SAME NULLIF_DIFFERENT COALESCED
-------- --------- --------- --------- ------- ----------- ---------------- ---------
default  x         was empty has value is null                            1         3

1 row selected.
```

### B. DECODE

<!-- example: oracle -->
```sql
SELECT DECODE(2, 1, 'one', 2, 'two', 'other') AS found, DECODE(9, 1, 'one', 2, 'two', 'other') AS default_,
       DECODE(9, 1, 'one') AS no_default, DECODE(NULL, NULL, 'nulls match', 'no') AS null_match
FROM dual;
```

```text
FOUND DEFAULT_ NO_DEFAULT NULL_MATCH
----- -------- ---------- -----------
two   other               nulls match

1 row selected.
```

### C. GREATEST and LEAST

<!-- example: oracle -->
```sql
SELECT GREATEST(1, 5, 3) AS greatest_number, LEAST(1, 5, 3) AS least_number,
       GREATEST('apple', 'pear', 'fig') AS greatest_string, LEAST('apple', 'pear', 'fig') AS least_string,
       TO_CHAR(GREATEST(DATE '2026-01-01', DATE '2026-03-15'), 'YYYY-MM-DD') AS latest,
       GREATEST(1, NULL, 3) AS with_null
FROM dual;
```

```text
GREATEST_NUMBER LEAST_NUMBER GREATEST_STRING LEAST_STRING LATEST     WITH_NULL
--------------- ------------ --------------- ------------ ---------- ---------
              5            1 pear            apple        2026-03-15

1 row selected.
```

### D. CASE

<!-- example: oracle -->
```sql
CREATE TABLE emp (id NUMBER, grade NUMBER, salary NUMBER);
INSERT INTO emp VALUES (1, 1, 100);
INSERT INTO emp VALUES (2, 2, 200);
INSERT INTO emp VALUES (3, 9, 300);
SELECT id, CASE grade WHEN 1 THEN 'junior' WHEN 2 THEN 'senior' ELSE 'other' END AS simple,
       CASE WHEN salary < 150 THEN 'low' WHEN salary < 250 THEN 'mid' END AS searched
FROM emp ORDER BY id;
SELECT SUM(CASE WHEN grade = 1 THEN salary ELSE 0 END) AS junior_pay, COUNT(CASE WHEN grade > 1 THEN 1 END) AS others
FROM emp;
```

```text
Table created.

1 row created.

1 row created.

1 row created.

ID SIMPLE SEARCHED
-- ------ --------
 1 junior low
 2 senior mid
 3 other

3 rows selected.

JUNIOR_PAY OTHERS
---------- ------
       100      2

1 row selected.
```

### E. A mixed-type NVL, and functions that are not available

NVL converts the second argument to the first's type, as Oracle does: `'x'` is not a number, so ORA-01722.

<!-- example: oracle -->
```sql
SELECT NVL(1, 'x') FROM dual;
SELECT LNNVL(1 = 1) FROM dual;
SELECT NANVL(1, 0) FROM dual;
```

```text
ERROR:
ORA-01722: invalid number

ERROR:
ORA-00904: invalid identifier

ERROR:
ORA-00904: invalid identifier
```

## See also

[Operators](operators.md), [Conversion functions](README.md#functions)
