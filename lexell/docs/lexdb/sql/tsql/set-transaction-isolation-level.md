# SET TRANSACTION ISOLATION LEVEL (Transact-SQL)

Sets the isolation level of the session's transactions. lexdb takes the statement and runs every read-write
transaction as serializable, whatever it says.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
SET TRANSACTION ISOLATION LEVEL
    { READ UNCOMMITTED
    | READ COMMITTED
    | REPEATABLE READ
    | SNAPSHOT
    | SERIALIZABLE
    }
[ ; ]
```

## Arguments

`READ UNCOMMITTED`, `READ COMMITTED`, `REPEATABLE READ`, `SNAPSHOT`, `SERIALIZABLE`
: SQL Server's levels. All are taken; none changes what lexdb does.

## Remarks

- lexdb's transactions read a consistent snapshot and never see another transaction's uncommitted changes. A
  read-write transaction is serializable: if another transaction changed and committed rows it read, its statement
  or its `COMMIT` fails with error 1205, and it should be run again.
- Drivers and tools send this statement when they connect or when a program sets the level; it succeeds.

## Differences from SQL Server

- The level is not kept: `sys.dm_exec_sessions.transaction_isolation_level` stays 2 (read committed) after
  `SET TRANSACTION ISOLATION LEVEL SERIALIZABLE`.
- Any word after `ISOLATION LEVEL` is taken (`SET TRANSACTION ISOLATION LEVEL CHAOS` succeeds); SQL Server gives a
  syntax error.
- `READ UNCOMMITTED` does not read uncommitted rows, and `SNAPSHOT` does not check the database's
  `ALLOW_SNAPSHOT_ISOLATION` (SQL Server: 3952; lexdb-dialect-gaps.md 4, package B).
- `DBCC USEROPTIONS` is not available (102).

## Examples

### A. Set the level

<!-- example: tsql -->
```sql
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
SET TRANSACTION ISOLATION LEVEL SNAPSHOT;
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
SELECT transaction_isolation_level FROM sys.dm_exec_sessions WHERE session_id = @@SPID;
```

```text
transaction_isolation_level
---------------------------
2

(1 row affected)
```

### B. Any level is taken

<!-- example: tsql -->
```sql
SET TRANSACTION ISOLATION LEVEL CHAOS;
SELECT 'taken' AS result;
```

```text
result
------
taken

(1 row affected)
```

## See also

[BEGIN TRANSACTION](begin-transaction.md) · [SET statements](set-statements.md)
