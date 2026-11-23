# Logical functions and CASE (Transact-SQL)

Functions that choose between values, replace NULL, and compare several values; and the `CASE` expression.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
IIF ( boolean_expression, true_value, false_value ) → data type of the values
CHOOSE ( index, val_1, val_2 [, val_n ] ) → data type of the values
ISNULL ( check_expression, replacement_value ) → data type of check_expression
COALESCE ( expression [, ...n ] ) → data type of the expressions
NULLIF ( expression, expression ) → type of the first expression
GREATEST ( expression [, ...n ] ) → data type of the expressions
LEAST ( expression [, ...n ] ) → data type of the expressions

CASE input_expression
    WHEN when_expression THEN result_expression [ ...n ]
    [ ELSE else_result_expression ]
END

CASE
    WHEN boolean_expression THEN result_expression [ ...n ]
    [ ELSE else_result_expression ]
END
```

## Functions

`IIF`
: *true_value* when the condition is true, else *false_value*. A condition that is unknown (NULL) gives
  *false_value*. It is a short form of a searched `CASE`.

`CHOOSE`
: The value at position *index*, counted from 1. An index of 0, below 0 or past the last value gives NULL.

`ISNULL`
: *check_expression*, or *replacement_value* when it is NULL.

`COALESCE`
: The first argument that is not NULL, or NULL when all are. It is the standard form of `ISNULL`, and takes any number
  of arguments.

`NULLIF`
: NULL when the two expressions are equal, else the first.

`GREATEST`, `LEAST`
: The largest and the smallest of the arguments (SQL Server 2022). A NULL argument is left out; the result is NULL
  only when every argument is NULL.

`CASE`
: A language construct, not a function. The simple form compares *input_expression* with each *when_expression* in
  turn; the searched form tests each condition. The first that is true or equal gives its result; without a match
  the result is the `ELSE` value or NULL. Only the first matching branch runs.

## Remarks

- All the result expressions of a `CASE`, and the arguments of `COALESCE`, `IIF`, `CHOOSE`, `GREATEST` and `LEAST`,
  must convert to one type: the one with the highest data type precedence among them (see the
  [conversion page](functions-conversion.md)). `CASE WHEN 1 = 1 THEN 'x' ELSE 5 END` is error 245, because the
  string `'x'` cannot become an `int`.
- A comparison with NULL is never true, so `CASE WHEN NULL = NULL THEN ...` takes the `ELSE` branch. Use `IS NULL`.

## Differences from SQL Server

- `ISNULL` is `COALESCE` with two arguments: the result takes the type of *both* arguments, not of the first.
  `ISNULL(CAST(NULL AS varchar(3)), 'abcdef')` is `abcdef` (SQL Server: `abc`, cut to the type of the first), and
  `ISNULL(CAST(NULL AS int), 1.5)` is `1.5` (SQL Server: the integer 1).
- A `CASE` or `COALESCE` that mixes an integer with a decimal gives the integer's text when the integer is chosen:
  `CASE WHEN 1 = 1 THEN 1 ELSE 2.5 END` is `1` (SQL Server: `1.0`).
- `IIF` of a condition that is not boolean is not refused: `IIF(1, 'a', 'b')` is `b`. SQL Server: error 4145.
- `GREATEST(1)` gives 1 (SQL Server: error 189, the function needs two arguments).
- `CHOOSE` with an index that is not a number is error 195 (SQL Server: 245).

## Examples

### A. IIF

<!-- example: tsql -->
```sql
SELECT IIF(1 > 2, 'yes', 'no') AS false_branch, IIF(NULL IS NULL, 'is null', 'not null') AS true_branch,
       IIF(NULL > 1, 'yes', 'no') AS unknown, IIF(1 = 2, 1, 2.5) AS mixed_numbers;
```

```text
false_branch true_branch unknown mixed_numbers
------------ ----------- ------- -------------
no           is null     no      2.5

(1 row affected)
```

### B. CHOOSE

<!-- example: tsql -->
```sql
SELECT CHOOSE(2, 'a', 'b', 'c') AS second, CHOOSE(5, 'a', 'b') AS past_the_end, CHOOSE(0, 'a', 'b') AS zero,
       CHOOSE(NULL, 'a', 'b') AS null_index;
```

```text
second past_the_end zero null_index
------ ------------ ---- ----------
b      NULL         NULL NULL

(1 row affected)
```

### C. ISNULL, COALESCE and NULLIF

<!-- example: tsql -->
```sql
SELECT ISNULL(NULL, 'x') AS isnull_, ISNULL('y', 'x') AS not_null, COALESCE(NULL, NULL, 3) AS coalesce_,
       COALESCE(NULL, NULL) AS all_null, NULLIF(5, 5) AS equal, NULLIF(5, 6) AS different;
```

```text
isnull_ not_null coalesce_ all_null equal different
------- -------- --------- -------- ----- ---------
x       y        3         NULL     NULL  5

(1 row affected)
```

### D. Avoiding a division by zero

`NULLIF` turns a zero divisor into NULL, so the division gives NULL and not error 8134.

<!-- example: tsql -->
```sql
SELECT n, d, n / NULLIF(d, 0) AS quotient, COALESCE(n / NULLIF(d, 0), -1) AS with_default
FROM (VALUES (10, 2), (7, 0), (3, 3)) AS v(n, d) ORDER BY n;
```

```text
n  d quotient with_default
-- - -------- ------------
3  3 1        1
7  0 NULL     -1
10 2 5        5

(3 rows affected)
```

### E. GREATEST and LEAST

<!-- example: tsql -->
```sql
SELECT GREATEST(1, 5, 3) AS greatest_, LEAST(4, 2, 8) AS least_, GREATEST('a', 'c', 'b') AS greatest_text,
       GREATEST(1, NULL, 3) AS skips_null, LEAST(NULL, 1) AS least_skips_null, GREATEST(1, 2.5) AS mixed,
       LEAST(CAST('2026-03-05' AS date), CAST('2026-01-01' AS date)) AS least_date, GREATEST(1) AS one_argument;
```

```text
greatest_ least_ greatest_text skips_null least_skips_null mixed least_date one_argument
--------- ------ ------------- ---------- ---------------- ----- ---------- ------------
5         2      c             3          1                2.5   2026-01-01 1

(1 row affected)
```

### F. Simple and searched CASE

<!-- example: tsql -->
```sql
SELECT CASE 2 WHEN 1 THEN 'one' WHEN 2 THEN 'two' ELSE 'many' END AS simple_form,
       CASE WHEN 5 > 10 THEN 'big' WHEN 5 > 1 THEN 'medium' ELSE 'small' END AS searched_form,
       CASE 9 WHEN 1 THEN 'one' END AS no_else, CASE WHEN NULL = NULL THEN 'equal' ELSE 'not equal' END AS nulls;
```

```text
simple_form searched_form no_else nulls
----------- ------------- ------- ---------
two         medium        NULL    not equal

(1 row affected)
```

### G. CASE in the select list, ORDER BY and aggregates

<!-- example: tsql -->
```sql
SELECT n, CASE WHEN n % 2 = 0 THEN 'even' ELSE 'odd' END AS parity, CASE n WHEN 1 THEN 'one' WHEN 2 THEN 'two' ELSE 'many' END AS word
FROM (VALUES (1), (2), (3)) AS v(n) ORDER BY CASE WHEN n = 3 THEN 0 ELSE 1 END, n;
GO
SELECT region, SUM(CASE WHEN amount > 10 THEN amount ELSE 0 END) AS big_total, COUNT(CASE WHEN amount > 10 THEN 1 END) AS big_count
FROM (VALUES ('n', 5), ('n', 20), ('s', 30)) AS v(region, amount) GROUP BY region ORDER BY region;
```

```text
n parity word
- ------ ----
3 odd    many
1 odd    one
2 even   two

(3 rows affected)

region big_total big_count
------ --------- ---------
n      20        1
s      30        1

(2 rows affected)
```

### H. The result type of a CASE

The branches take the type with the highest precedence: `int` before `varchar`, `float` before `int`.

<!-- example: tsql -->
```sql
SELECT CASE WHEN 1 = 2 THEN 'x' ELSE 5 END AS int_wins, CASE WHEN 1 = 1 THEN CAST(1 AS int) ELSE CAST(2.5 AS float) END AS float_wins;
GO
SELECT CASE WHEN 1 = 1 THEN 'x' ELSE 5 END AS text_cannot_be_int;
```

```text
int_wins float_wins
-------- ----------
5        1.0

(1 row affected)

Msg 245, Level 16, State 1, Line 1
Conversion failed when converting the varchar value 'x' to data type int.
```

### I. ISNULL and COALESCE differ in lexdb from SQL Server

<!-- example: tsql -->
```sql
SELECT ISNULL(CAST(NULL AS varchar(3)), 'abcdef') AS isnull_, COALESCE(CAST(NULL AS varchar(3)), 'abcdef') AS coalesce_,
       ISNULL(CAST(NULL AS int), 1.5) AS isnull_number, CASE WHEN 1 = 1 THEN 1 ELSE 2.5 END AS case_number,
       IIF(1, 'a', 'b') AS iif_not_boolean;
```

```text
isnull_ coalesce_ isnull_number case_number iif_not_boolean
------- --------- ------------- ----------- ---------------
abcdef  abcdef    1.5           1           b

(1 row affected)
```

### J. Wrong arguments

<!-- example: tsql -->
```sql
SELECT NULLIF(1, 1, 2) AS a;
GO
SELECT GREATEST(1, 'a') AS a;
GO
SELECT CHOOSE('a', 1, 2) AS a;
```

```text
Msg 195, Level 15, State 1, Line 1
'nullif' is not a recognized built-in function name.
Msg 245, Level 16, State 1, Line 1
Conversion failed when converting the varchar value 'a' to data type int.
Msg 195, Level 15, State 1, Line 1
operator does not exist: 1 compared with a
```

## See also

[Conversion functions](functions-conversion.md) · [Mathematical functions](functions-math.md) ·
[String functions](functions-string.md) · [SELECT](select.md)
