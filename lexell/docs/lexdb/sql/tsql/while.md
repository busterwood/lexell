# WHILE, BREAK and CONTINUE (Transact-SQL)

Runs a statement or a block again and again while a condition is true. `BREAK` leaves the loop; `CONTINUE` starts
its next round.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
WHILE boolean_expression
    { sql_statement | statement_block | BREAK | CONTINUE }

BREAK
CONTINUE
```

## Arguments

*boolean_expression*
: The condition, checked before each round. It may use variables, `EXISTS`, and scalar subqueries in parentheses.

`BREAK`
: Leaves the innermost `WHILE` loop. The statements after its `END` run next.

`CONTINUE`
: Skips the rest of the round and checks the condition again.

## Remarks

- A condition that is NULL ends the loop.
- Loops nest; `BREAK` and `CONTINUE` apply to the innermost one.
- A loop that changes rows one batch at a time is a common way to work through a large table in steps.

## Differences from SQL Server

- `BREAK` and `CONTINUE` outside a loop are taken and do nothing; SQL Server refuses them (error 135).

## Examples

<!--setup: tsql
CREATE TABLE dbo.acct (id int PRIMARY KEY, bal int);
INSERT dbo.acct VALUES (1, 100), (2, 50), (3, 20);
-->

The examples use one table:

```sql
CREATE TABLE dbo.acct (id int PRIMARY KEY, bal int);
INSERT dbo.acct VALUES (1, 100), (2, 50), (3, 20);
```

### A. BREAK and CONTINUE

<!-- example: tsql -->
```sql
DECLARE @i int = 0, @odd nvarchar(50) = N'';
WHILE @i < 10
BEGIN
    SET @i += 1;
    IF @i % 2 = 0 CONTINUE;
    IF @i > 7 BREAK;
    SET @odd += CAST(@i AS nvarchar(5)) + N' ';
END
SELECT @odd AS odd, @i AS i;
```

```text
odd      i
-------- -
1 3 5 7  9

(1 row affected)
```

### B. A condition on a table

<!-- example: tsql -->
```sql
SET NOCOUNT ON;
DECLARE @rounds int = 0;
WHILE (SELECT MIN(bal) FROM dbo.acct) < 80
BEGIN
    UPDATE dbo.acct SET bal = bal + 25 WHERE bal < 80;
    SET @rounds += 1;
END
SELECT @rounds AS rounds, MIN(bal) AS lowest FROM dbo.acct;
SET NOCOUNT OFF;
```

```text
rounds lowest
------ ------
3      95

(1 row affected)
```

### C. Nested loops

<!-- example: tsql -->
```sql
DECLARE @a int = 0, @b int, @pairs int = 0;
WHILE @a < 3
BEGIN
    SET @a += 1;
    SET @b = 0;
    WHILE 1 = 1
    BEGIN
        SET @b += 1;
        IF @b > @a BREAK;
        SET @pairs += 1;
    END
END
SELECT @pairs AS pairs;
```

```text
pairs
-----
6

(1 row affected)
```

### D. Work through rows in steps

<!-- example: tsql -->
```sql
CREATE TABLE dbo.queue (id int PRIMARY KEY);
INSERT dbo.queue SELECT value FROM GENERATE_SERIES(1, 10);
DECLARE @steps int = 0;
WHILE EXISTS (SELECT 1 FROM dbo.queue)
BEGIN
    DELETE TOP (4) FROM dbo.queue;
    SET @steps += 1;
END
SELECT @steps AS steps;
```

```text
(10 rows affected)

(4 rows affected)

(4 rows affected)

(2 rows affected)

steps
-----
3

(1 row affected)
```

## See also

[IF...ELSE](if-else.md) · [BEGIN...END](begin-end.md)
