# Catalog views: databases, principals, permissions and the server (Transact-SQL)

`sys.databases`, `sys.database_principals`, `sys.server_principals`, `sys.database_permissions`,
`sys.dm_exec_sessions`, `sys.configurations` and the views that tools read and lexdb leaves empty.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
SELECT ... FROM sys.databases
SELECT ... FROM sys.database_principals
SELECT ... FROM sys.server_principals
SELECT ... FROM sys.database_permissions
SELECT ... FROM sys.dm_exec_sessions
SELECT ... FROM sys.configurations
```

## Views

`sys.databases`
: Five rows: `master` (1), `tempdb` (2), `model` (3), `msdb` (4) and `lexdb` (5), the user database. Columns
  include `name`, `database_id`, `collation_name`, `compatibility_level` (160), `state_desc` (`ONLINE`),
  `recovery_model_desc`, `is_read_only`, `user_access_desc` and the `is_*_on` flags. The options set with
  [ALTER DATABASE](alter-database.md) show here.

`sys.database_principals`
: The database's users and roles: `name`, `principal_id`, `type` (`S` user, `R` role), `type_desc`,
  `default_schema_name`, `owning_principal_id`, `sid`, `is_fixed_role`. It holds the fixed roles (`public`,
  `db_owner`, `db_datareader`, ...), `dbo`, `guest`, `sys`, `INFORMATION_SCHEMA`, and the users and roles made
  with [CREATE USER](create-user.md) and [CREATE ROLE](create-role.md).

`sys.server_principals`
: The logins and server roles: `name`, `principal_id`, `sid`, `type`, `type_desc`, `is_disabled`,
  `default_database_name`, `is_fixed_role`. It holds `public`, `sysadmin` and the other fixed server roles, but not the logins: `sa` is not listed.

`sys.database_permissions`
: `class`, `class_desc`, `major_id`, `minor_id`, `grantee_principal_id`, `grantor_principal_id`, `type`,
  `permission_name`, `state`, `state_desc`: the permissions [GRANT](grant.md) gave, and the default permissions of
  `public`.

`sys.dm_exec_sessions`
: One row of fixed, recorded session facts (login `sa`, program `SQLCMD`, isolation level 2). It does not describe
  the current connection.

`sys.configurations`
: The `sp_configure` options (97 rows) with their documented defaults.

### Views lexdb has and leaves empty

`sys.extended_properties`, `sys.synonyms`, `sys.triggers`, `sys.all_parameters`, `sys.assemblies`,
`sys.xml_schema_collections`
: No rows, so that tools which read them work (lexdb has no such objects).

`sys.stats`, `sys.database_files`, `sys.data_spaces`, `sys.syslanguages`
: A statistics row per index, the database's data and log file, one data space, and the list of languages.

## Remarks

- A role made with `CREATE ROLE r` is a database principal of type `R`; a user made with `CREATE USER u` is type
  `S`.
- The row of a fixed role is there so that `IS_MEMBER` and tools find it; it does not carry rights.

## Differences from SQL Server

- `sys.dm_exec_sessions` does not list the sessions of the server. `sys.dm_exec_requests`, `sys.dm_tran_locks`,
  `sys.dm_os_sys_info`, `sys.dm_db_partition_stats` and `sys.database_role_members` do not exist (error 208).
- `CREATE LOGIN` is not supported: the logins are lexdb's own.
- `master`, `tempdb`, `model` and `msdb` are rows only; they cannot be used as databases.

## Examples

<!--setup: tsql
CREATE SCHEMA hr;
GO
CREATE TABLE hr.dept (id int PRIMARY KEY, name varchar(30) NOT NULL UNIQUE);
CREATE TABLE hr.emp (id int IDENTITY(1,1) PRIMARY KEY, dept_id int NOT NULL REFERENCES hr.dept (id), name varchar(40) NOT NULL, salary decimal(10,2) CONSTRAINT df_sal DEFAULT 1000, bonus AS (salary / 10), CONSTRAINT ck_sal CHECK (salary >= 0));
CREATE INDEX ix_emp_name ON hr.emp (name) INCLUDE (salary);
GO
CREATE VIEW hr.v_emp AS SELECT id, name FROM hr.emp;
GO
CREATE PROCEDURE hr.p_raise @pct int, @out int OUTPUT AS SET @out = @pct * 2;
GO
CREATE FUNCTION hr.f_sq (@x int) RETURNS int AS BEGIN RETURN @x * @x; END;
GO
CREATE SEQUENCE hr.sq START WITH 5;
GO
CREATE TYPE hr.idl AS TABLE (id int);
GO
-->

The examples use the objects of [the first catalog page](catalog-tables.md):

```sql
CREATE SCHEMA hr;
GO
CREATE TABLE hr.dept (id int PRIMARY KEY, name varchar(30) NOT NULL UNIQUE);
CREATE TABLE hr.emp (id int IDENTITY(1,1) PRIMARY KEY, dept_id int NOT NULL REFERENCES hr.dept (id),
    name varchar(40) NOT NULL, salary decimal(10,2) CONSTRAINT df_sal DEFAULT 1000, bonus AS (salary / 10),
    CONSTRAINT ck_sal CHECK (salary >= 0));
CREATE INDEX ix_emp_name ON hr.emp (name) INCLUDE (salary);
GO
CREATE VIEW hr.v_emp AS SELECT id, name FROM hr.emp;
GO
CREATE PROCEDURE hr.p_raise @pct int, @out int OUTPUT AS SET @out = @pct * 2;
GO
CREATE FUNCTION hr.f_sq (@x int) RETURNS int AS BEGIN RETURN @x * @x; END;
GO
CREATE SEQUENCE hr.sq START WITH 5;
GO
CREATE TYPE hr.idl AS TABLE (id int);
```

### A. The databases

<!-- example: tsql -->
```sql
SELECT name, database_id, compatibility_level, collation_name, state_desc, recovery_model_desc, is_read_only
FROM sys.databases ORDER BY database_id;
```

```text
name   database_id compatibility_level collation_name               state_desc recovery_model_desc is_read_only
------ ----------- ------------------- ---------------------------- ---------- ------------------- ------------
master 1           160                 SQL_Latin1_General_CP1_CI_AS ONLINE     SIMPLE              0
tempdb 2           160                 SQL_Latin1_General_CP1_CI_AS ONLINE     SIMPLE              0
model  3           160                 SQL_Latin1_General_CP1_CI_AS ONLINE     FULL                0
msdb   4           160                 SQL_Latin1_General_CP1_CI_AS ONLINE     SIMPLE              0
lexdb  5           160                 SQL_Latin1_General_CP1_CI_AS ONLINE     FULL                0

(5 rows affected)
```

### B. Users and roles

<!-- example: tsql -->
```sql
CREATE ROLE reader;
CREATE USER ann;
GRANT SELECT ON OBJECT::hr.dept TO reader;
GO
SELECT name, type, type_desc, is_fixed_role FROM sys.database_principals
WHERE name IN ('public', 'dbo', 'db_owner', 'reader', 'ann') ORDER BY name;
```

```text
name     type type_desc     is_fixed_role
-------- ---- ------------- -------------
ann      S    SQL_USER      0
db_owner R    DATABASE_ROLE 1
dbo      S    SQL_USER      0
public   R    DATABASE_ROLE 0
reader   R    DATABASE_ROLE 0

(5 rows affected)
```

### C. Permissions

<!-- example: tsql -->
```sql
SELECT pr.name AS grantee, p.class_desc, OBJECT_NAME(p.major_id) AS object_name, p.permission_name, p.state_desc
FROM sys.database_permissions p JOIN sys.database_principals pr ON pr.principal_id = p.grantee_principal_id
WHERE pr.name = 'reader';
```

```text
grantee class_desc       object_name permission_name state_desc
------- ---------------- ----------- --------------- ----------
reader  OBJECT_OR_COLUMN dept        SELECT          GRANT

(1 row affected)
```

### D. Logins

<!-- example: tsql -->
```sql
SELECT name, type_desc, is_disabled, is_fixed_role FROM sys.server_principals
WHERE name IN ('sa', 'public', 'sysadmin') ORDER BY name;
```

```text
name     type_desc   is_disabled is_fixed_role
-------- ----------- ----------- -------------
public   SERVER_ROLE 0           0
sysadmin SERVER_ROLE 0           1

(2 rows affected)
```

### E. Settings

<!-- example: tsql -->
```sql
SELECT COUNT(*) AS options FROM sys.configurations;
SELECT name, value, value_in_use FROM sys.configurations
WHERE name IN ('max degree of parallelism', 'show advanced options') ORDER BY name;
```

```text
options
-------
97

(1 row affected)

name                      value value_in_use
------------------------- ----- ------------
max degree of parallelism 0     0
show advanced options     0     0

(2 rows affected)
```

### F. Views that are empty or missing

<!-- example: tsql -->
```sql
SELECT COUNT(*) AS triggers FROM sys.triggers;
SELECT COUNT(*) AS synonyms FROM sys.synonyms;
SELECT COUNT(*) AS extended_properties FROM sys.extended_properties;
GO
SELECT * FROM sys.dm_exec_requests;
```

```text
triggers
--------
0

(1 row affected)

synonyms
--------
0

(1 row affected)

extended_properties
-------------------
0

(1 row affected)

Msg 208, Level 16, State 1, Line 1
Invalid object name 'sys.dm_exec_requests'.
```

## See also

[GRANT](grant.md), [CREATE USER](create-user.md), [CREATE ROLE](create-role.md),
[ALTER DATABASE](alter-database.md), [System functions](functions-system.md)
