# ALTER DATABASE (Transact-SQL)

Sets database options. lexdb keeps the options that tools set and shows them in `sys.databases`; it refuses the ones
that would change how it works.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
ALTER DATABASE { database_name | CURRENT }
SET option [ ,...n ]
    [ WITH { ROLLBACK AFTER n [ SECONDS ] | ROLLBACK IMMEDIATE | NO_WAIT } ]
[ ; ]

option ::=
    { ALLOW_SNAPSHOT_ISOLATION | READ_COMMITTED_SNAPSHOT | AUTO_CLOSE | AUTO_SHRINK
    | AUTO_CREATE_STATISTICS | AUTO_UPDATE_STATISTICS | AUTO_UPDATE_STATISTICS_ASYNC | TRUSTWORTHY | DB_CHAINING
    | RECURSIVE_TRIGGERS | NUMERIC_ROUNDABORT | ARITHABORT | ANSI_NULLS | ANSI_NULL_DEFAULT | ANSI_PADDING
    | ANSI_WARNINGS | CONCAT_NULL_YIELDS_NULL | QUOTED_IDENTIFIER | CURSOR_CLOSE_ON_COMMIT } { ON | OFF }
  | RECOVERY { FULL | BULK_LOGGED | SIMPLE }
  | PAGE_VERIFY { CHECKSUM | TORN_PAGE_DETECTION | NONE }
  | PARAMETERIZATION { SIMPLE | FORCED }
  | CURSOR_DEFAULT { LOCAL | GLOBAL }
  | DELAYED_DURABILITY = { DISABLED | ALLOWED | FORCED }
  | COMPATIBILITY_LEVEL = { 100 | 110 | 120 | 130 | 140 | 150 | 160 }
  | TARGET_RECOVERY_TIME = n
  | QUERY_STORE = { ON | OFF }
  | ACCELERATED_DATABASE_RECOVERY = { ON | OFF }
  | MULTI_USER | READ_WRITE | ONLINE
```

## Arguments

*database_name*, `CURRENT`
: `lexdb` (or `CURRENT`). Another name is error 5011.

*option*
: The option and its value. Several options may be set in one statement.

`WITH ROLLBACK ...`, `WITH NO_WAIT`
: Read and taken.

## Remarks

- The values are kept and shown in `sys.databases` (`snapshot_isolation_state_desc`, `is_read_committed_snapshot_on`,
  `recovery_model_desc`, `compatibility_level`, `is_auto_shrink_on` ...). They do not change how lexdb works:
  lexdb's transactions read snapshots and its read-write transactions are serializable, whatever
  `ALLOW_SNAPSHOT_ISOLATION` and `READ_COMMITTED_SNAPSHOT` say (lexdb-dialect-gaps.md 4, package B).
- `MULTI_USER`, `READ_WRITE` and `ONLINE` are the states lexdb is in: they change nothing.
- `ALTER DATABASE` cannot run inside a transaction (error 226); the error ends the batch, and the transaction stays
  open.
- An unknown option is error 102.

## Differences from SQL Server

- `READ_ONLY`, `SINGLE_USER`, `RESTRICTED_USER`, `OFFLINE`, `EMERGENCY`, `CHANGE_TRACKING`, `ENCRYPTION`, `HADR`,
  `LEDGER`, the broker options and SQL Server's other options are error 50000 ("lexdb: ALTER DATABASE ... SET
  READ_ONLY is not supported yet").
- `MODIFY NAME`, `MODIFY FILE`, `ADD FILE`, `COLLATE` and the other clauses besides `SET` are error 50000.
  `CREATE DATABASE` is error 50000 and `DROP DATABASE` error 102: lexdb has one database.
- `DATABASEPROPERTYEX(DB_NAME(), 'Recovery')` keeps saying `FULL` after `SET RECOVERY SIMPLE`, which
  `sys.databases` shows.

## Examples

### A. The options, before and after

<!-- example: tsql -->
```sql
SELECT snapshot_isolation_state_desc, is_read_committed_snapshot_on, recovery_model_desc, compatibility_level
FROM sys.databases WHERE name = DB_NAME();
ALTER DATABASE CURRENT SET ALLOW_SNAPSHOT_ISOLATION ON;
ALTER DATABASE lexdb SET READ_COMMITTED_SNAPSHOT ON WITH ROLLBACK IMMEDIATE;
ALTER DATABASE CURRENT SET RECOVERY SIMPLE, AUTO_SHRINK OFF;
ALTER DATABASE CURRENT SET COMPATIBILITY_LEVEL = 150;
SELECT snapshot_isolation_state_desc, is_read_committed_snapshot_on, recovery_model_desc, compatibility_level
FROM sys.databases WHERE name = DB_NAME();
```

```text
snapshot_isolation_state_desc is_read_committed_snapshot_on recovery_model_desc compatibility_level
----------------------------- ----------------------------- ------------------- -------------------
OFF                           0                             FULL                160

(1 row affected)

snapshot_isolation_state_desc is_read_committed_snapshot_on recovery_model_desc compatibility_level
----------------------------- ----------------------------- ------------------- -------------------
ON                            1                             SIMPLE              150

(1 row affected)
```

### B. Errors

<!-- example: tsql -->
```sql
ALTER DATABASE CURRENT SET READ_ONLY;
GO
ALTER DATABASE CURRENT SET COMPATIBILITY_LEVEL = 999;
GO
ALTER DATABASE nothere SET AUTO_SHRINK OFF;
GO
ALTER DATABASE CURRENT SET FOOBAR ON;
GO
BEGIN TRANSACTION;
ALTER DATABASE CURRENT SET AUTO_SHRINK OFF;
GO
SELECT @@TRANCOUNT AS still_open;
ROLLBACK;
GO
```

```text
Msg 50000, Level 16, State 1, Line 1
lexdb: ALTER DATABASE ... SET READ_ONLY is not supported yet
Msg 15048, Level 16, State 1, Line 1
Valid values of the database compatibility level are 100, 110, 120, 130, 140, 150 or 160.
Msg 5011, Level 16, State 1, Line 1
User does not have permission to alter database 'nothere', the database does not exist, or the database is not in a state that allows access checks.
Msg 102, Level 15, State 1, Line 1
Incorrect syntax near 'foobar'.
Msg 226, Level 16, State 1, Line 1
ALTER DATABASE statement not allowed within multi-statement transaction.
still_open
----------
1

(1 row affected)
```

## See also

[USE](use.md) · [SET TRANSACTION ISOLATION LEVEL](set-transaction-isolation-level.md)
