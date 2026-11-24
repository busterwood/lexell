# DROP SEQUENCE (Transact-SQL)

Removes one or more sequences.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
DROP SEQUENCE [ IF EXISTS ] [ schema_name . ] sequence_name [ ,...n ]
[ ; ]
```

## Arguments

`IF EXISTS`
: A sequence that does not exist is no error.

*sequence_name*
: The sequence to drop.

## Remarks

- `DROP SEQUENCE` is transactional.
- A sequence that a column's default calls (`DEFAULT (NEXT VALUE FOR s)`) cannot be dropped while the default exists.

## Differences from SQL Server

- A sequence that does not exist is error 208, `sequence "s" does not exist` (SQL Server: 3701).
- A sequence that a column's default uses is refused, as in SQL Server, but with error 50000 and PostgreSQL's text
  (`cannot drop sequence ticket because other objects depend on it`); SQL Server's is 3729. Drop the table or the
  default first (example B).

## Examples

### A. Drop sequences

<!-- example: tsql -->
```sql
CREATE SEQUENCE dbo.s1;
CREATE SEQUENCE dbo.s2;
DROP SEQUENCE dbo.s1, dbo.s2;
DROP SEQUENCE IF EXISTS dbo.s3;
SELECT COUNT(*) AS left_over FROM sys.sequences;
```

```text
left_over
---------
0

(1 row affected)
```

### B. A sequence a default uses

<!-- example: tsql -->
```sql
CREATE SEQUENCE dbo.ticket;
CREATE TABLE dbo.t (id int DEFAULT (NEXT VALUE FOR dbo.ticket), v int);
DROP SEQUENCE dbo.ticket;
GO
INSERT dbo.t (v) VALUES (1);
SELECT * FROM dbo.t;
GO
DROP TABLE dbo.t;
DROP SEQUENCE dbo.ticket;
GO
SELECT COUNT(*) AS sequences FROM sys.sequences;
```

```text
Msg 50000, Level 16, State 1, Line 3
cannot drop sequence ticket because other objects depend on it
(1 row affected)

id v
-- -
1  1

(1 row affected)

sequences
---------
0

(1 row affected)
```

### C. Errors

<!-- example: tsql -->
```sql
DROP SEQUENCE dbo.nothere;
```

```text
Msg 208, Level 16, State 1, Line 1
sequence "nothere" does not exist
```

## See also

[CREATE SEQUENCE](create-sequence.md) · [ALTER SEQUENCE](alter-sequence.md)
