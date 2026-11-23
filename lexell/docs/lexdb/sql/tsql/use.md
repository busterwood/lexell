# USE (Transact-SQL)

Sets the session's database. lexdb has one database, `lexdb`; `USE` takes it, and `master` as the same database.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
USE { database_name | [database_name] }
[ ; ]
```

## Arguments

*database_name*
: `lexdb`, or `master`, which lexdb takes as `lexdb`.

## Remarks

- Tools and drivers send `USE` when they connect, or when a program sets its catalog; `USE lexdb` and `USE master`
  succeed and tell the client that the database is `lexdb`.
- SQL Server's other system databases (`tempdb`, `model`, `msdb`) are listed in `sys.databases` but cannot be
  opened: `USE` of one is error 916. A name that is not a database is error 911.
- Three-part names (`lexdb.dbo.emp`) name the same database.

## Differences from SQL Server

- lexdb has one database: `master` is taken as `lexdb`, and there is no other database to use. See
  [ALTER DATABASE](alter-database.md).

## Examples

### A. Use the database

<!-- example: tsql -->
```sql
USE lexdb;
SELECT DB_NAME() AS db;
```

```text
Changed database context to 'lexdb'.
db
-----
lexdb

(1 row affected)
```

### B. master is lexdb

<!-- example: tsql -->
```sql
USE [master];
SELECT DB_NAME() AS db;
```

```text
Changed database context to 'lexdb'.
db
-----
lexdb

(1 row affected)
```

### C. Errors

<!-- example: tsql -->
```sql
USE tempdb;
USE nothere;
```

```text
Msg 916, Level 14, State 1, Line 1
The server principal "sa" is not able to access the database "tempdb" under the current security context.
Msg 911, Level 16, State 1, Line 1
Database 'nothere' does not exist. Make sure that the name is entered correctly.
```

## See also

[ALTER DATABASE](alter-database.md) · [EXECUTE](execute.md)
