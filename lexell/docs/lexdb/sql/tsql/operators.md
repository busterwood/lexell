# Operators (Transact-SQL)

Arithmetic, string, bitwise, comparison and logical operators, and how they bind.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
-- arithmetic
+  -  *  /  %          unary + and -

-- string
+                      concatenation

-- bitwise
&  |  ^  ~  <<  >>

-- comparison
=  <>  !=  <  <=  >  >=

-- logical and others
AND  OR  NOT
expr [ NOT ] LIKE pattern [ ESCAPE char ]
expr [ NOT ] IN ( value [, ...] | subquery )
expr [ NOT ] BETWEEN low AND high
EXISTS ( subquery )
expr comparison { ALL | ANY | SOME } ( subquery )
expr IS [ NOT ] NULL
expr IS [ NOT ] DISTINCT FROM expr
expr COLLATE collation

-- assignment
=
+=  -=  *=  /=  %=  &=  |=  ^=
```

## Arguments

`+`, `-`, `*`, `/`, `%`
: Add, subtract, multiply, divide and remainder. With two integers `/` truncates toward zero and `%` takes the sign
  of the left operand. Division or remainder by zero is error 8134, an integer result out of range is 8115.

`+` on strings
: Joins two strings. NULL on either side gives NULL (`CONCAT` leaves NULLs out). A string and a number are added as
  numbers: convert the number with `CAST` to join them.

`&`, `|`, `^`, `~`
: Bitwise AND, OR, exclusive OR and NOT on integers.

`<<`, `>>`
: Shift left and right (SQL Server 2022). `LEFT_SHIFT` and `RIGHT_SHIFT` are the same as functions.

`=`, `<>`, `!=`, `<`, `<=`, `>`, `>=`
: Comparisons. A comparison with NULL is unknown, so `NULL = NULL` is not true: use `IS NULL`.

`AND`, `OR`, `NOT`
: Logic over three values (true, false, unknown).

`LIKE`
: Pattern matching with `%` (any characters), `_` (one character), `[abc]`, `[a-c]` and `[^abc]`. `ESCAPE` names an
  escape character.

`IN`, `BETWEEN`, `EXISTS`, `ALL`, `ANY`, `SOME`
: Membership in a list or a subquery, a range (both ends included), whether a subquery has rows, and a comparison
  with all, or with at least one, of a subquery's values.

`IS [NOT] NULL`, `IS [NOT] DISTINCT FROM`
: Tests for NULL, and a comparison in which two NULLs are equal (SQL Server 2022).

`COLLATE`
: Compares or sorts a string under a collation: see [character types](data-types-character.md).

`=`, `+=`, `-=`, `*=`, `/=`, `%=`, `&=`, `|=`, `^=`
: Assign to a variable in [SET](set-local-variable.md) and in `UPDATE ... SET`. The compound forms are
  `x = x op value`.

## Remarks

- Precedence, from the tightest: `~` and the unary signs; `*`, `/`, `%`; `+`, `-`, `&`, `^`, `|` (all at one level,
  left to right: `1 + 1 * 2 ^ 3` is `(1 + 2) ^ 3`, which is 0); the comparisons; `NOT`; `AND`; `OR`, `LIKE`, `IN`,
  `BETWEEN` and `ALL`/`ANY`/`SOME`. Use brackets when in doubt.
- The type of an arithmetic result is the wider of the two types: see [numeric types](data-types-numeric.md).
- A comparison is a condition, not a value: it can be used in `WHERE`, `HAVING`, `ON`, `IF`, `WHILE` and `CASE
  WHEN`, and a value is made with `CASE` or `IIF`.
- `NOT IN` with a NULL in the list is never true: `1 NOT IN (2, NULL)` is unknown.

## Differences from SQL Server

- `!<` and `!>` (not less than, not greater than) are error 102.
- `||` joins strings (`'a' || 'b'` is `ab`), as in PostgreSQL and Oracle: SQL Server does not take it. A
  comparison or `NOT` expression in a select list (`SELECT 1 = 1`, `SELECT NOT 1 = 2`) is taken and gives 1 or 0,
  where SQL Server gives error 102.
- `'n=' + 5` is error 245 as in SQL Server, but the message names `bigint` rather than `int`.
- `date + 1`, `date - date` and `datetime - datetime` behave differently from SQL Server's: see
  [date and time types](data-types-datetime.md).
- `**`, `<=>`, `*=` and `=*` (the old outer join operators) are error 102.

## Examples

### A. Arithmetic and precedence

<!-- example: tsql -->
```sql
SELECT 2 + 3 * 4 AS a, (2 + 3) * 4 AS b, -2 + 5 AS c, 10 - 4 - 3 AS d, 2 * 3 % 4 AS e, 7 / 2 * 2 AS f,
       1 + 1 * 2 ^ 3 AS g;
```

```text
a  b  c d e f g
-- -- - - - - -
14 20 3 3 2 6 0

(1 row affected)
```

### B. Integer and decimal division

<!-- example: tsql -->
```sql
SELECT 5 / 2 AS int_div, 5 / 2.0 AS dec_div, 5 % 2 AS remainder, CAST(5 AS float) / 2 AS float_div,
       -7 / 2 AS neg_div, -7 % 3 AS neg_remainder;
GO
SELECT 5 / 0;
```

```text
int_div dec_div  remainder float_div neg_div neg_remainder
------- -------- --------- --------- ------- -------------
2       2.500000 1         2.5       -3      -1

(1 row affected)

Msg 8134, Level 16, State 1, Line 1
Divide by zero error encountered.
```

### C. Bitwise operators

<!-- example: tsql -->
```sql
SELECT 6 & 3 AS band, 6 | 3 AS bor, 6 ^ 3 AS bxor, ~6 AS bnot, 1 << 4 AS shift_left, 256 >> 2 AS shift_right,
       5 & 3 | 8 AS mixed;
```

```text
band bor bxor bnot shift_left shift_right mixed
---- --- ---- ---- ---------- ----------- -----
2    7   5    -7   16         64          9

(1 row affected)
```

### D. Compound assignment

<!-- example: tsql -->
```sql
DECLARE @i int = 10, @s varchar(20) = 'ab';
SET @i += 5;  SELECT @i AS plus_eq;
SET @i -= 3;  SELECT @i AS minus_eq;
SET @i *= 2;  SELECT @i AS times_eq;
SET @i /= 5;  SELECT @i AS divide_eq;
SET @i %= 3;  SELECT @i AS mod_eq;
SET @i = 12;  SET @i &= 10;  SELECT @i AS and_eq;
SET @i |= 5;  SELECT @i AS or_eq;
SET @i ^= 3;  SELECT @i AS xor_eq;
SET @s += 'cd';  SELECT @s AS concat_eq;
```

```text
plus_eq
-------
15

(1 row affected)

minus_eq
--------
12

(1 row affected)

times_eq
--------
24

(1 row affected)

divide_eq
---------
4

(1 row affected)

mod_eq
------
1

(1 row affected)

and_eq
------
8

(1 row affected)

or_eq
-----
13

(1 row affected)

xor_eq
------
14

(1 row affected)

concat_eq
---------
abcd

(1 row affected)
```

### E. Comparison and logic

<!-- example: tsql -->
```sql
SELECT CASE WHEN 1 = 1 AND 2 > 1 THEN 'y' ELSE 'n' END AS and_,
       CASE WHEN NOT 1 = 2 THEN 'y' ELSE 'n' END AS not_,
       CASE WHEN 1 = 2 OR 3 <> 4 THEN 'y' ELSE 'n' END AS or_,
       CASE WHEN 1 != 2 THEN 'y' ELSE 'n' END AS not_equal,
       CASE WHEN 3 >= 3 AND 3 <= 3 THEN 'y' ELSE 'n' END AS bounds;
GO
SELECT CASE WHEN 2 !< 1 THEN 'y' ELSE 'n' END AS not_less;
```

```text
and_ not_ or_ not_equal bounds
---- ---- --- --------- ------
y    y    y   y         y

(1 row affected)

Msg 102, Level 15, State 1, Line 1
Incorrect syntax near '!'.
```

### F. NULL

<!-- example: tsql -->
```sql
SELECT CASE WHEN NULL = NULL THEN 'y' ELSE 'n' END AS equals_null,
       CASE WHEN NULL IS NULL THEN 'y' ELSE 'n' END AS is_null,
       CASE WHEN 1 IS NOT NULL THEN 'y' ELSE 'n' END AS is_not_null,
       CASE WHEN NULL IS NOT DISTINCT FROM NULL THEN 'y' ELSE 'n' END AS not_distinct,
       CASE WHEN 1 IS DISTINCT FROM NULL THEN 'y' ELSE 'n' END AS distinct_;
```

```text
equals_null is_null is_not_null not_distinct distinct_
----------- ------- ----------- ------------ ---------
n           y       y           y            y

(1 row affected)
```

### G. IN, BETWEEN, ALL, ANY and EXISTS

<!-- example: tsql -->
```sql
SELECT CASE WHEN 2 IN (1, 2, 3) THEN 'y' ELSE 'n' END AS in_,
       CASE WHEN 5 NOT IN (1, 2, 3) THEN 'y' ELSE 'n' END AS not_in,
       CASE WHEN 5 BETWEEN 1 AND 10 THEN 'y' ELSE 'n' END AS between_,
       CASE WHEN 5 NOT BETWEEN 6 AND 10 THEN 'y' ELSE 'n' END AS not_between,
       CASE WHEN 1 NOT IN (2, NULL) THEN 'y' ELSE 'n' END AS not_in_with_null;
SELECT CASE WHEN 3 > ALL (SELECT x FROM (VALUES (1), (2)) v(x)) THEN 'y' ELSE 'n' END AS all_,
       CASE WHEN 3 > ANY (SELECT x FROM (VALUES (1), (5)) v(x)) THEN 'y' ELSE 'n' END AS any_,
       CASE WHEN 3 = SOME (SELECT x FROM (VALUES (3)) v(x)) THEN 'y' ELSE 'n' END AS some_,
       CASE WHEN EXISTS (SELECT 1 WHERE 1 = 0) THEN 'y' ELSE 'n' END AS exists_;
```

```text
in_ not_in between_ not_between not_in_with_null
--- ------ -------- ----------- ----------------
y   y      y        y           n

(1 row affected)

all_ any_ some_ exists_
---- ---- ----- -------
y    y    y     n

(1 row affected)
```

### H. LIKE

<!-- example: tsql -->
```sql
SELECT CASE WHEN 'Abc' LIKE 'a%' THEN 'y' ELSE 'n' END AS ignores_case,
       CASE WHEN 'a%b' LIKE 'a!%b' ESCAPE '!' THEN 'y' ELSE 'n' END AS escaped,
       CASE WHEN 'abc' NOT LIKE 'x%' THEN 'y' ELSE 'n' END AS not_like;
```

```text
ignores_case escaped not_like
------------ ------- --------
y            y       y

(1 row affected)
```

### I. Joining strings

<!-- example: tsql -->
```sql
SELECT 'a' + 'b' AS joined, 'n=' + CAST(5 AS varchar(5)) AS with_number, 'x' + NULL AS with_null,
       CONCAT('x', NULL) AS concat_function, 'a' || 'b' AS double_bar;
GO
SELECT 'n=' + 5;
```

```text
joined with_number with_null concat_function double_bar
------ ----------- --------- --------------- ----------
ab     n=5         NULL      x               ab

(1 row affected)

Msg 245, Level 16, State 1, Line 1
invalid input syntax for type bigint: "n="
```

### J. Operators SQL Server has and lexdb lacks

<!-- example: tsql -->
```sql
SELECT 5 !> 3 AS a;
GO
SELECT 2 ** 3 AS power;
```

```text
Msg 102, Level 15, State 1, Line 1
Incorrect syntax near '!'.
Msg 102, Level 15, State 1, Line 1
Incorrect syntax near '*'.
```

## See also

[Numeric types](data-types-numeric.md), [Character types](data-types-character.md),
[Date and time types](data-types-datetime.md), [SET @variable](set-local-variable.md),
[Logical functions and CASE](functions-logical.md)
