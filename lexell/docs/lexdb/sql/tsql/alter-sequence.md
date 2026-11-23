# ALTER SEQUENCE (Transact-SQL)

Restarts a sequence, or changes its step, its bounds or whether it cycles.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
ALTER SEQUENCE [ schema_name . ] sequence_name
    [ RESTART [ WITH constant ] ]
    [ INCREMENT BY constant ]
    [ MINVALUE constant ]
    [ MAXVALUE constant ]
    [ CYCLE ]
    [ CACHE [ constant ] ]
[ ; ]
```

## Arguments

`RESTART [ WITH` *constant* `]`
: The next `NEXT VALUE FOR` gives *constant*, or without `WITH` the sequence's start value.

`INCREMENT BY`, `MINVALUE`, `MAXVALUE`, `CYCLE`, `CACHE`
: As in [CREATE SEQUENCE](create-sequence.md).

## Remarks

- A restart is not undone by `ROLLBACK`.
- The type of a sequence cannot be changed: drop it and make it again.

## Differences from SQL Server

- The start value must stay within the new bounds: `ALTER SEQUENCE s INCREMENT BY 2 MAXVALUE 100` on a sequence that
  started at 1000 is error 50000 ("START value (1000) cannot be greater than MAXVALUE (100)"), even after a restart
  below 100, and with `RESTART WITH 50` in the same statement. Drop the sequence and make it again.
- `NO CACHE` is error 102.

## Examples

<!--setup: tsql
CREATE SEQUENCE dbo.order_no START WITH 1000 INCREMENT BY 10;
-->

The examples use one sequence:

```sql
CREATE SEQUENCE dbo.order_no START WITH 1000 INCREMENT BY 10;
```

### A. Restart a sequence

<!-- example: tsql -->
```sql
SELECT NEXT VALUE FOR dbo.order_no AS a;
ALTER SEQUENCE dbo.order_no RESTART WITH 5;
SELECT NEXT VALUE FOR dbo.order_no AS b;
ALTER SEQUENCE dbo.order_no RESTART;
SELECT NEXT VALUE FOR dbo.order_no AS c;
```

```text
a
----
1000

(1 row affected)

b
-
5

(1 row affected)

c
----
1000

(1 row affected)
```

### B. Change the step

<!-- example: tsql -->
```sql
ALTER SEQUENCE dbo.order_no INCREMENT BY 100;
SELECT NEXT VALUE FOR dbo.order_no AS d;
SELECT increment, current_value FROM sys.sequences WHERE name = 'order_no';
```

```text
d
----
1100

(1 row affected)

increment current_value
--------- -------------
100       1100

(1 row affected)
```

### C. Errors

<!-- example: tsql -->
```sql
ALTER SEQUENCE dbo.order_no MAXVALUE 100;
ALTER SEQUENCE dbo.order_no RESTART WITH 50 MAXVALUE 100;
ALTER SEQUENCE dbo.nothere RESTART;
GO
```

```text
Msg 50000, Level 16, State 1, Line 1
START value (1000) cannot be greater than MAXVALUE (100)
Msg 50000, Level 16, State 1, Line 2
START value (1000) cannot be greater than MAXVALUE (100)
Msg 208, Level 16, State 1, Line 3
Invalid object name 'nothere'.
```

## See also

[CREATE SEQUENCE](create-sequence.md) · [DROP SEQUENCE](drop-sequence.md)
