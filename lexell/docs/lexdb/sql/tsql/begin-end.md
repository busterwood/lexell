# BEGIN...END (Transact-SQL)

Groups statements into a block, so that `IF`, `ELSE` and `WHILE` can run them together.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
BEGIN
    { sql_statement | statement_block }
END
```

## Arguments

*sql_statement*, *statement_block*
: Any statements of the batch, blocks too: blocks nest.

## Remarks

- `BEGIN...END` is mostly used after `IF`, `ELSE` and `WHILE`, which otherwise run only the next statement, and in a
  procedure's or function's body.
- A block does not start a transaction: that is [BEGIN TRANSACTION](begin-transaction.md).

## Differences from SQL Server

- None known.

## Examples

### A. A block after IF

<!-- example: tsql -->
```sql
CREATE TABLE dbo.acct (id int PRIMARY KEY, bal int);
INSERT dbo.acct VALUES (1, 100), (2, 50);
IF EXISTS (SELECT 1 FROM dbo.acct WHERE bal < 60)
BEGIN
    UPDATE dbo.acct SET bal = bal + 10 WHERE bal < 60;
    SELECT id, bal FROM dbo.acct ORDER BY id;
END
```

```text
(2 rows affected)

(1 row affected)

id bal
-- ---
1  100
2  60

(2 rows affected)
```

### B. Nested blocks

<!-- example: tsql -->
```sql
BEGIN
    SELECT 'outer' AS level;
    BEGIN
        SELECT 'inner' AS level;
    END
END
```

```text
level
-----
outer

(1 row affected)

level
-----
inner

(1 row affected)
```

## See also

[IF...ELSE](if-else.md) · [WHILE](while.md) · [TRY...CATCH](try-catch.md)
