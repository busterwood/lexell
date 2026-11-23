# CREATE SEQUENCE (Transact-SQL)

Makes a sequence: an object that hands out numbers, one after another, with `NEXT VALUE FOR`.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
CREATE SEQUENCE [ schema_name . ] sequence_name
    [ AS { tinyint | smallint | int | bigint } ]
    [ START WITH constant ]
    [ INCREMENT BY constant ]
    [ MINVALUE constant | NO MINVALUE ]
    [ MAXVALUE constant | NO MAXVALUE ]
    [ CYCLE | NO CYCLE ]
    [ CACHE [ constant ] ]
[ ; ]

NEXT VALUE FOR [ schema_name . ] sequence_name
```

## Arguments

`AS` *type*
: The sequence's type.

`START WITH`
: The first value.

`INCREMENT BY`
: The step, positive or negative. The default is 1.

`MINVALUE`, `MAXVALUE`
: The bounds. Past a bound, `NEXT VALUE FOR` fails, or with `CYCLE` starts again from the other bound.

`CYCLE`, `NO CYCLE`
: Start again after the last value, or not (the default).

`CACHE`
: Read and taken; it changes nothing that can be seen.

`NEXT VALUE FOR` *sequence_name*
: The sequence's next value. It may be used in a select list, in `INSERT ... VALUES`, in `INSERT ... SELECT`, in
  `UPDATE ... SET`, and in a column's `DEFAULT`.

## Remarks

- A value once handed out is used: `ROLLBACK` does not give it back, so a sequence may leave gaps.
- `sys.sequences` shows the sequence, its bounds and `current_value`.
- [ALTER SEQUENCE](alter-sequence.md) restarts it or changes its step and bounds.

## Differences from SQL Server

- Without `START WITH` and `AS`, a sequence starts at 1; SQL Server's default is `bigint`, starting at its smallest
  value (-9223372036854775808).
- `NO CACHE` is error 102: leave it out.
- `AS decimal` and `AS numeric` are error 50000 ("sequence type must be smallint, integer, or bigint").
- Past `MAXVALUE` without `CYCLE` the error is 50000 with lexdb's text (SQL Server: 11728).
- `NEXT VALUE FOR` twice for one sequence in one row gives two values; SQL Server gives the same value to both.
- `NEXT VALUE FOR ... OVER (ORDER BY ...)` is error 102.
- `sp_sequence_get_range` is not available (2812).
- A name that is used is error 2714 with lexdb's text.

## Examples

### A. A sequence and its values

<!-- example: tsql -->
```sql
CREATE SEQUENCE dbo.order_no START WITH 1000 INCREMENT BY 10;
SELECT NEXT VALUE FOR dbo.order_no AS first;
SELECT NEXT VALUE FOR dbo.order_no AS second;
```

```text
first
-----
1000

(1 row affected)

second
------
1010

(1 row affected)
```

### B. A column default, and INSERT ... SELECT

<!-- example: tsql -->
```sql
CREATE TABLE dbo.orders (id int PRIMARY KEY DEFAULT (NEXT VALUE FOR dbo.order_no), item nvarchar(10));
INSERT dbo.orders (item) VALUES (N'pen'), (N'ink');
INSERT dbo.orders (id, item) SELECT NEXT VALUE FOR dbo.order_no, N'pad';
SELECT * FROM dbo.orders ORDER BY id;
```

```text
(2 rows affected)

(1 row affected)

id   item
---- ----
1020 pen
1030 ink
1040 pad

(3 rows affected)
```

### C. Bounds and CYCLE

<!-- example: tsql -->
```sql
CREATE SEQUENCE dbo.slot AS tinyint START WITH 1 MINVALUE 1 MAXVALUE 3 CYCLE;
SELECT NEXT VALUE FOR dbo.slot AS a;
SELECT NEXT VALUE FOR dbo.slot AS b;
SELECT NEXT VALUE FOR dbo.slot AS c;
SELECT NEXT VALUE FOR dbo.slot AS d;
```

```text
a
-
1

(1 row affected)

b
-
2

(1 row affected)

c
-
3

(1 row affected)

d
-
1

(1 row affected)
```

### D. Not given back by ROLLBACK

<!-- example: tsql -->
```sql
CREATE SEQUENCE dbo.ticket;
BEGIN TRANSACTION;
SELECT NEXT VALUE FOR dbo.ticket AS in_transaction;
ROLLBACK;
SELECT NEXT VALUE FOR dbo.ticket AS after_rollback;
```

```text
in_transaction
--------------
1

(1 row affected)

after_rollback
--------------
2

(1 row affected)
```

### E. The catalog

<!-- example: tsql -->
```sql
SELECT name, start_value, increment, minimum_value, maximum_value, is_cycling, current_value
FROM sys.sequences ORDER BY name;
```

```text
name     start_value increment minimum_value maximum_value       is_cycling current_value
-------- ----------- --------- ------------- ------------------- ---------- -------------
order_no 1000        10        1             9223372036854775807 0          1040
slot     1           1         1             3                   1          1
ticket   1           1         1             9223372036854775807 0          2

(3 rows affected)
```

### F. Errors

<!-- example: tsql -->
```sql
CREATE SEQUENCE dbo.limited START WITH 1 MAXVALUE 2;
SELECT NEXT VALUE FOR dbo.limited;
SELECT NEXT VALUE FOR dbo.limited;
SELECT NEXT VALUE FOR dbo.limited;
GO
CREATE SEQUENCE dbo.order_no;
GO
CREATE SEQUENCE dbo.other START WITH 1 NO CACHE;
GO
```

```text
(No column name)
----------------
1

(1 row affected)

(No column name)
----------------
2

(1 row affected)

Msg 50000, Level 16, State 1, Line 1
nextval: reached maximum value of sequence "limited" (2)
Msg 2714, Level 16, State 1, Line 1
relation "order_no" already exists
Msg 102, Level 15, State 1, Line 1
Incorrect syntax near 'no'.
```

## See also

[ALTER SEQUENCE](alter-sequence.md) · [DROP SEQUENCE](drop-sequence.md) · [CREATE TABLE](create-table.md)
