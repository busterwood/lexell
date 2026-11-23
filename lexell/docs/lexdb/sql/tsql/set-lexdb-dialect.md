# SET LEXDB_DIALECT (lexdb)

lexdb's own: makes the rest of the session take PostgreSQL's SQL instead of T-SQL, or T-SQL again.

**Door:** SQL Server (TDS). **Follows:** lexdb; not in SQL Server.

## Syntax

```
SET LEXDB_DIALECT { POSTGRES | TSQL }
[ ; ]
```

## Arguments

`POSTGRES`
: The session's next batches are PostgreSQL statements, as the PostgreSQL door takes them: `::` casts, `||`,
  `LIMIT`, PostgreSQL's functions and catalog. Results still come back over TDS, with SQL Server's types.

`TSQL`
: Back to T-SQL.

## Remarks

- The setting lasts for the session.
- With it, a program that has only a SQL Server driver can run PostgreSQL statements.
- Any other word is error 50000 ("SET LEXDB_DIALECT takes POSTGRES or TSQL").

## Differences from SQL Server

- SQL Server has no such option.

## Examples

### A. PostgreSQL's SQL, then T-SQL again

<!-- example: tsql -->
```sql
SET LEXDB_DIALECT POSTGRES;
GO
SELECT 1::int + 1 AS two, 'a' || 'b' AS ab;
SELECT g FROM generate_series(1, 3) AS g LIMIT 2;
GO
SET LEXDB_DIALECT TSQL;
GO
SELECT TOP (1) 'back to T-SQL' AS r;
```

```text
two ab
--- --
2   ab

(1 row affected)

g
-
1
2

(2 rows affected)

r
-------------
back to T-SQL

(1 row affected)
```

### B. Errors

<!-- example: tsql -->
```sql
SET LEXDB_DIALECT ORACLE;
```

```text
Msg 50000, Level 16, State 1, Line 1
SET LEXDB_DIALECT takes POSTGRES or TSQL
```

## See also

[SET statements](set-statements.md)
