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

## Differences from SQL Server

- A sequence that does not exist is error 208, `sequence "s" does not exist` (SQL Server: 3701).
- A sequence that a column's default uses can be dropped; the next `INSERT` that needs the default fails with
  error 208 (example B). SQL Server refuses the drop (3729).

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
INSERT dbo.t (v) VALUES (1);
SELECT * FROM dbo.t;
```

```text
Msg 208, Level 16, State 1, Line 1
Invalid object name 'ticket'.
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
