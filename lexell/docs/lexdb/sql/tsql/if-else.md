# IF...ELSE (Transact-SQL)

Runs a statement or a block when a condition is true, and optionally another when it is not.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
IF boolean_expression
    { sql_statement | statement_block }
[ ELSE
    { sql_statement | statement_block } ]
```

## Arguments

*boolean_expression*
: A condition. It may use variables, `EXISTS (subquery)`, and scalar subqueries in parentheses.

*sql_statement*, *statement_block*
: One statement, or several in a [BEGIN...END](begin-end.md) block.

## Remarks

- A condition that is NULL counts as false: the `ELSE` branch runs. So does `NULL = NULL`.
- `ELSE IF` chains further conditions.
- Without `BEGIN...END`, only the next statement belongs to the `IF` or the `ELSE`.

## Differences from SQL Server

- None known.

## Examples

<!--setup: tsql
CREATE TABLE dbo.acct (id int PRIMARY KEY, bal int);
INSERT dbo.acct VALUES (1, 100), (2, 50);
-->

The examples use one table:

```sql
CREATE TABLE dbo.acct (id int PRIMARY KEY, bal int);
INSERT dbo.acct VALUES (1, 100), (2, 50);
```

### A. IF, ELSE IF and ELSE

<!-- example: tsql -->
```sql
DECLARE @bal int = (SELECT bal FROM dbo.acct WHERE id = 2);
IF @bal >= 100
    SELECT 'high' AS band;
ELSE IF @bal >= 50
    SELECT 'middle' AS band;
ELSE
    SELECT 'low' AS band;
```

```text
band
------
middle

(1 row affected)
```

### B. EXISTS and a block

<!-- example: tsql -->
```sql
IF EXISTS (SELECT 1 FROM dbo.acct WHERE bal > 90)
BEGIN
    PRINT 'some accounts are over 90';
    SELECT id FROM dbo.acct WHERE bal > 90;
END
ELSE
    PRINT 'none';
```

```text
some accounts are over 90
id
--
1

(1 row affected)
```

### C. NULL is not true

<!-- example: tsql -->
```sql
IF NULL = NULL PRINT 'equal' ELSE PRINT 'not known to be equal';
IF (SELECT COUNT(*) FROM dbo.acct) = 2 PRINT 'two accounts';
```

```text
not known to be equal
two accounts
```

## See also

[BEGIN...END](begin-end.md) · [WHILE](while.md) · [TRY...CATCH](try-catch.md)
