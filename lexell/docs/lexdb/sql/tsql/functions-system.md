# System, identity, error and metadata functions (Transact-SQL)

Functions and system variables that report on the session, the last statement, the error being handled and the
objects of the database.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
-- last statement and session
@@ROWCOUNT            @@ERROR               @@TRANCOUNT           @@NESTLEVEL           @@PROCID
@@SPID                @@IDENTITY            SCOPE_IDENTITY ( )    NEXT VALUE FOR [ schema. ] sequence
NEWID ( )

-- the error being handled (in a CATCH block)
ERROR_NUMBER ( )      ERROR_MESSAGE ( )     ERROR_SEVERITY ( )    ERROR_STATE ( )
ERROR_LINE ( )        ERROR_PROCEDURE ( )   XACT_STATE ( )

-- the server and the session
@@VERSION             @@SERVERNAME          @@SERVICENAME         @@LANGUAGE            @@LANGID
@@DATEFIRST           @@MAX_PRECISION       @@TEXTSIZE            @@LOCK_TIMEOUT        @@MAX_CONNECTIONS
@@MICROSOFTVERSION
SERVERPROPERTY ( property )
DATABASEPROPERTYEX ( database, property )
SESSIONPROPERTY ( option )
CONNECTIONPROPERTY ( property )
CONTEXT_INFO ( )

-- names, ids and properties of objects
DB_NAME ( [ id ] )                   DB_ID ( [ name ] )
SCHEMA_NAME ( [ id ] )               SCHEMA_ID ( [ name ] )
OBJECT_ID ( name [ , type ] )        OBJECT_NAME ( id )               OBJECT_SCHEMA_NAME ( id )
OBJECT_DEFINITION ( id )             OBJECTPROPERTY ( id, property )  OBJECTPROPERTYEX ( id, property )
COLUMNPROPERTY ( id, column, property )                              INDEXPROPERTY ( id, index, property )
TYPE_NAME ( id )                     TYPE_ID ( name )

-- users and permissions
USER_NAME ( )          SUSER_NAME ( )          SUSER_SNAME ( )   SUSER_SID ( [ name ] )
ORIGINAL_LOGIN ( )     SYSTEM_USER             CURRENT_USER              SESSION_USER
IS_MEMBER ( role )     IS_SRVROLEMEMBER ( role )
HAS_DBACCESS ( database )
HAS_PERMS_BY_NAME ( securable, class, permission )
```

## Functions

### The last statement

`@@ROWCOUNT`
: The number of rows the previous statement changed or returned. A `SELECT` sets it too.

`@@ERROR`
: The error number of the previous statement, 0 if it succeeded. It is reset by every statement, so read it at
  once.

`@@TRANCOUNT`
: The depth of open transactions: 0 outside a transaction. See [BEGIN TRANSACTION](begin-transaction.md).

`@@NESTLEVEL`, `@@PROCID`
: The nesting depth of procedure calls (0 at the top level), and the object id of the running procedure (NULL
  outside a procedure).

`@@SPID`
: The session's id.

`SCOPE_IDENTITY()`, `@@IDENTITY`
: The last identity value an `INSERT` made in the session.

`NEXT VALUE FOR sequence`
: The next value of a sequence: see [CREATE SEQUENCE](create-sequence.md).

`NEWID()`
: A new random `uniqueidentifier`.

### The error being handled

`ERROR_NUMBER()`, `ERROR_MESSAGE()`, `ERROR_SEVERITY()`, `ERROR_STATE()`, `ERROR_LINE()`, `ERROR_PROCEDURE()`
: The number, text, severity, state, line and procedure name of the error that sent control to the `CATCH` block.
  Outside a `CATCH` block they are NULL. See [TRY ... CATCH](try-catch.md).

`XACT_STATE()`
: 1 when a transaction is open and can commit, -1 when it can only roll back, 0 when none is open.

### The server and the session

`@@VERSION`
: A text naming lexdb and the SQL Server version it reports.

`@@SERVERNAME`, `@@SERVICENAME`, `@@LANGUAGE`, `@@LANGID`, `@@DATEFIRST`, `@@MAX_PRECISION`, `@@TEXTSIZE`,
`@@LOCK_TIMEOUT`, `@@MAX_CONNECTIONS`, `@@MICROSOFTVERSION`
: Constants: `lexdb`, `MSSQLSERVER`, `us_english`, 0, 7, 38, 2147483647, -1, 32767 and 268439771.

`SERVERPROPERTY(property)`
: `ProductVersion` (`16.0.4315.2`), `ProductMajorVersion` (16), `Edition` (`Developer Edition (64-bit)`),
  `EngineEdition` (3), `IsClustered` (0), `Collation` and `ServerName`.

`DATABASEPROPERTYEX(database, property)`
: `Status` (`ONLINE`), `Recovery`, `Updateability` and other properties of the database.

`SESSIONPROPERTY(option)`, `CONNECTIONPROPERTY(property)`, `CONTEXT_INFO()`
: A session option (`ANSI_NULLS` is 1), a connection property (`net_transport` is `TCP`), and the session's
  context bytes (NULL).

### Names, ids and properties of objects

`DB_NAME([id])`, `DB_ID([name])`
: The database's name or id. Without an argument, the current one (`lexdb`, id 5; `master` is 1).

`SCHEMA_NAME([id])`, `SCHEMA_ID([name])`
: The schema's name or id; without an argument, the default schema (`dbo`, id 1).

`OBJECT_ID(name [, type])`
: The id of a table, view or other object, NULL when it does not exist or is not of the given `type` (`'U'`, `'V'`,
  `'P'`, ...). `OBJECT_NAME(id)` and `OBJECT_SCHEMA_NAME(id)` give the name and the schema back.

`OBJECT_DEFINITION(id)`
: The text of a view's or a procedure's `CREATE` statement.

`OBJECTPROPERTY(id, property)`, `OBJECTPROPERTYEX(id, property)`
: A property of an object: `IsTable`, `IsView`, `IsProcedure`, `TableHasPrimaryKey`, `TableHasClustIndex`,
  `TableHasNonclustIndex`, `TableHasUniqueCnst` and others.

`COLUMNPROPERTY(id, column, property)`, `INDEXPROPERTY(id, index, property)`
: A property of a column (`IsIdentity`, `AllowsNull`, `ColumnId`) or of an index.

`TYPE_NAME(id)`, `TYPE_ID(name)`
: The name of a system type from its id, and the other way round: `TYPE_ID('int')` is 56.

### Users and permissions

`USER_NAME()`, `SUSER_NAME()`, `SUSER_SNAME()`, `ORIGINAL_LOGIN()`, `SYSTEM_USER`, `CURRENT_USER`, `SESSION_USER`
: The login of the session. Every one is the login name (`sa` for a `trust` login).

`SUSER_SID([name])`
: The security id of a login.

`IS_MEMBER(role)`, `IS_SRVROLEMEMBER(role)`
: 1 when the user is in the database role or the server role, else 0.

`HAS_DBACCESS(database)`
: 1 when the login can use the database.

`HAS_PERMS_BY_NAME(securable, class, permission)`
: 1 when the user holds the permission on the object.

## Remarks

- `@@ROWCOUNT` is set by every statement, including a `SELECT`: read it straight after the statement it is about.
- The values of `@@SPID` and `OBJECT_ID` differ from session to session and are not shown in the examples.

## Differences from SQL Server

- `IDENT_CURRENT`, `NEWSEQUENTIALID`, `ROWCOUNT_BIG`, `TRIGGER_NESTLEVEL`, `SESSION_CONTEXT`, `APPLOCK_MODE`,
  `DATABASEPROPERTY`, `COL_NAME`, `COL_LENGTH`, `HOST_NAME`, `APP_NAME`, `SUSER_ID`, `USER_ID`, `PARSENAME`,
  `@@CURSOR_ROWS`, `@@FETCH_STATUS`, `@@DBTS`, `@@TOTAL_ERRORS`, `@@OPTIONS` and `SQL_VARIANT_PROPERTY` do not
  exist (error 195). `USER_NAME` and `SUSER_SNAME` take no argument.
- `DB_NAME(id)` and `SCHEMA_NAME(id)` give NULL for an id that does not exist; `TYPE_NAME` of an unknown id is NULL.
- `IS_MEMBER('db_owner')` and `IS_SRVROLEMEMBER('sysadmin')` are 0 for `sa`, which has every right.
- `@@VERSION` is lexdb's own text, not Microsoft's.

## Examples

<!--setup: tsql
CREATE TABLE dbo.m1 (id int PRIMARY KEY, name varchar(20) NOT NULL, n int IDENTITY(1,1));
GO
CREATE VIEW dbo.mv1 AS SELECT id FROM dbo.m1;
GO
CREATE PROCEDURE dbo.mp1 AS SELECT 1;
GO
-->

The examples use a table `dbo.m1`, a view `dbo.mv1` and a procedure `dbo.mp1`:

```sql
CREATE TABLE dbo.m1 (id int PRIMARY KEY, name varchar(20) NOT NULL, n int IDENTITY(1,1));
CREATE VIEW dbo.mv1 AS SELECT id FROM dbo.m1;
CREATE PROCEDURE dbo.mp1 AS SELECT 1;
```

### A. Row counts

<!-- example: tsql -->
```sql
CREATE TABLE dbo.w (a int, b int);
INSERT INTO dbo.w VALUES (1, 2), (3, 4), (5, 6);
UPDATE dbo.w SET b = 0 WHERE a > 1;
SELECT @@ROWCOUNT AS after_update;
DELETE FROM dbo.w WHERE a = 1;
SELECT @@ROWCOUNT AS after_delete;
SELECT * FROM dbo.w;
SELECT @@ROWCOUNT AS after_select;
```

```text
(3 rows affected)

(2 rows affected)

after_update
------------
2

(1 row affected)

(1 row affected)

after_delete
------------
1

(1 row affected)

a b
- -
3 0
5 0

(2 rows affected)

after_select
------------
2

(1 row affected)
```

### B. Identity values

<!-- example: tsql -->
```sql
CREATE TABLE dbo.id1 (id int IDENTITY(10, 5) PRIMARY KEY, v varchar(10));
INSERT INTO dbo.id1 (v) VALUES ('a');
SELECT SCOPE_IDENTITY() AS scope_id, @@IDENTITY AS at_identity;
INSERT INTO dbo.id1 (v) VALUES ('b'), ('c');
SELECT SCOPE_IDENTITY() AS scope_id, @@ROWCOUNT AS rc;
```

```text
(1 row affected)

scope_id at_identity
-------- -----------
10       10

(1 row affected)

(2 rows affected)

scope_id rc
-------- --
20       2

(1 row affected)
```

### C. Sequences and NEWID

<!-- example: tsql -->
```sql
CREATE SEQUENCE dbo.sq START WITH 100 INCREMENT BY 10;
SELECT NEXT VALUE FOR dbo.sq AS a, NEXT VALUE FOR dbo.sq AS b;
SELECT CASE WHEN NEWID() = NEWID() THEN 'same' ELSE 'different' END AS two_guids;
```

```text
a   b
--- ---
100 110

(1 row affected)

two_guids
---------
different

(1 row affected)
```

### D. Transactions: @@TRANCOUNT

<!-- example: tsql -->
```sql
BEGIN TRANSACTION;
BEGIN TRANSACTION;
SELECT @@TRANCOUNT AS inside;
COMMIT;
SELECT @@TRANCOUNT AS after_one_commit;
ROLLBACK;
SELECT @@TRANCOUNT AS after_rollback;
```

```text
inside
------
2

(1 row affected)

after_one_commit
----------------
1

(1 row affected)

after_rollback
--------------
0

(1 row affected)
```

### E. Procedure nesting

<!-- example: tsql -->
```sql
CREATE PROCEDURE dbo.lvl AS SELECT @@NESTLEVEL AS inside_procedure;
GO
EXEC dbo.lvl;
SELECT @@NESTLEVEL AS top_level, CASE WHEN @@SPID > 0 THEN 'yes' ELSE 'no' END AS has_spid;
```

```text
inside_procedure
----------------
1

(1 row affected)

top_level has_spid
--------- --------
0         yes

(1 row affected)
```

### F. The error being handled

<!-- example: tsql -->
```sql
BEGIN TRY
    SELECT 1 / 0;
END TRY
BEGIN CATCH
    SELECT ERROR_NUMBER() AS num, ERROR_MESSAGE() AS msg, ERROR_SEVERITY() AS sev, ERROR_STATE() AS st,
           ERROR_LINE() AS ln, ERROR_PROCEDURE() AS proc_name, XACT_STATE() AS xs;
END CATCH;
GO
SELECT ERROR_NUMBER() AS outside_catch, XACT_STATE() AS no_transaction;
GO
SELECT 1 / 0;
SELECT @@ERROR AS error_after;
```

```text
num  msg                               sev st ln proc_name xs
---- --------------------------------- --- -- -- --------- --
8134 Divide by zero error encountered. 16  1  2  NULL      0

(1 row affected)

outside_catch no_transaction
------------- --------------
NULL          0

(1 row affected)

Msg 8134, Level 16, State 1, Line 1
Divide by zero error encountered.
error_after
-----------
8134

(1 row affected)
```

### G. The server and the session

<!-- example: tsql -->
```sql
SELECT @@VERSION AS version;
SELECT @@SERVERNAME AS servername, @@SERVICENAME AS service, @@LANGUAGE AS language, @@DATEFIRST AS datefirst,
       @@MAX_PRECISION AS max_precision, @@TEXTSIZE AS textsize, @@LOCK_TIMEOUT AS lock_timeout;
SELECT SERVERPROPERTY('ProductVersion') AS product_version, SERVERPROPERTY('Edition') AS edition,
       SERVERPROPERTY('EngineEdition') AS engine, SERVERPROPERTY('ProductMajorVersion') AS major,
       SERVERPROPERTY('IsClustered') AS clustered, SERVERPROPERTY('Collation') AS collation;
SELECT DATABASEPROPERTYEX('lexdb', 'Status') AS status, DATABASEPROPERTYEX('lexdb', 'Updateability') AS updateability,
       SESSIONPROPERTY('ANSI_NULLS') AS ansi_nulls, CONNECTIONPROPERTY('net_transport') AS transport;
```

```text
version
--------------------------------------------------------------------------------------
lexdb (SQL Server protocol, TDS 7.4; reports itself as Microsoft SQL Server 16.0.4315)

(1 row affected)

servername service     language   datefirst max_precision textsize   lock_timeout
---------- ----------- ---------- --------- ------------- ---------- ------------
lexdb      MSSQLSERVER us_english 7         38            2147483647 -1

(1 row affected)

product_version edition                    engine major clustered collation
--------------- -------------------------- ------ ----- --------- ----------------------------
16.0.4315.2     Developer Edition (64-bit) 3      16    0         SQL_Latin1_General_CP1_CI_AS

(1 row affected)

status updateability ansi_nulls transport
------ ------------- ---------- ---------
ONLINE READ_WRITE    1          TCP

(1 row affected)
```

### H. Databases, schemas and users

<!-- example: tsql -->
```sql
SELECT DB_NAME() AS db, DB_ID() AS db_id, DB_ID('master') AS master_id, SCHEMA_NAME() AS sch, SCHEMA_ID('dbo') AS sch_id,
       USER_NAME() AS un, SUSER_SNAME() AS ssn, SYSTEM_USER AS su, ORIGINAL_LOGIN() AS ol, CURRENT_USER AS cu;
```

```text
db    db_id master_id sch sch_id un ssn su ol cu
----- ----- --------- --- ------ -- --- -- -- --
lexdb 5     1         dbo 1      sa sa  sa sa sa

(1 row affected)
```

### I. Objects and their properties

<!-- example: tsql -->
```sql
SELECT OBJECT_ID('dbo.m1') IS NOT NULL AS table_found, OBJECT_NAME(OBJECT_ID('dbo.m1')) AS object_name,
       OBJECT_SCHEMA_NAME(OBJECT_ID('dbo.m1')) AS schema_name, OBJECT_ID('dbo.nothere') AS missing,
       OBJECT_ID('dbo.mv1', 'V') IS NOT NULL AS view_found, OBJECT_ID('dbo.m1', 'V') AS table_is_not_a_view;
SELECT OBJECTPROPERTY(OBJECT_ID('dbo.m1'), 'IsTable') AS is_table,
       OBJECTPROPERTY(OBJECT_ID('dbo.mv1'), 'IsView') AS is_view,
       OBJECTPROPERTY(OBJECT_ID('dbo.m1'), 'TableHasPrimaryKey') AS has_pk,
       OBJECTPROPERTYEX(OBJECT_ID('dbo.mp1'), 'IsProcedure') AS is_procedure;
SELECT COLUMNPROPERTY(OBJECT_ID('dbo.m1'), 'n', 'IsIdentity') AS identity_column,
       COLUMNPROPERTY(OBJECT_ID('dbo.m1'), 'name', 'AllowsNull') AS name_nullable,
       COLUMNPROPERTY(OBJECT_ID('dbo.m1'), 'name', 'ColumnId') AS name_position;
SELECT OBJECT_DEFINITION(OBJECT_ID('dbo.mv1')) AS definition;
GO
CREATE TABLE dbo.k1 (id int PRIMARY KEY, code varchar(5) UNIQUE);
CREATE TABLE dbo.k2 (id int PRIMARY KEY NONCLUSTERED);
CREATE TABLE dbo.k3 (a int, b int);
GO
SELECT OBJECT_NAME(object_id) AS tbl, OBJECTPROPERTY(object_id, 'TableHasPrimaryKey') AS has_pk,
       OBJECTPROPERTY(object_id, 'TableHasClustIndex') AS has_clustered_index,
       OBJECTPROPERTY(object_id, 'TableHasNonclustIndex') AS has_nonclustered_index,
       OBJECTPROPERTY(object_id, 'TableHasUniqueCnst') AS has_unique
FROM sys.tables WHERE name IN ('k1', 'k2', 'k3') ORDER BY name;
```

```text
table_found object_name schema_name missing view_found table_is_not_a_view
----------- ----------- ----------- ------- ---------- -------------------
1           m1          dbo         NULL    1          NULL

(1 row affected)

is_table is_view has_pk is_procedure
-------- ------- ------ ------------
1        1       1      1

(1 row affected)

identity_column name_nullable name_position
--------------- ------------- -------------
1               0             2

(1 row affected)

definition
----------------------------------------------
CREATE VIEW dbo.mv1 AS SELECT id FROM dbo.m1;

(1 row affected)

tbl has_pk has_clustered_index has_nonclustered_index has_unique
--- ------ ------------------- ---------------------- ----------
k1  1      1                   1                      1
k2  1      0                   1                      0
k3  0      0                   0                      0

(3 rows affected)
```

### J. Names from ids, and types

<!-- example: tsql -->
```sql
SELECT TYPE_NAME(56) AS name_of_56, TYPE_ID('int') AS id_of_int, TYPE_NAME(231) AS name_of_231,
       DB_NAME(1) AS db_1, DB_NAME(99) AS db_99, SCHEMA_NAME(1) AS schema_1;
```

```text
name_of_56 id_of_int name_of_231 db_1   db_99 schema_1
---------- --------- ----------- ------ ----- --------
int        56        nvarchar    master NULL  dbo

(1 row affected)
```

### K. Users and permissions

<!-- example: tsql -->
```sql
SELECT IS_MEMBER('public') AS public_member, IS_MEMBER('db_owner') AS db_owner, IS_SRVROLEMEMBER('sysadmin') AS sysadmin,
       HAS_DBACCESS('lexdb') AS db_access, HAS_PERMS_BY_NAME('dbo.m1', 'OBJECT', 'SELECT') AS can_select;
```

```text
public_member db_owner sysadmin db_access can_select
------------- -------- -------- --------- ----------
1             0        0        1         1

(1 row affected)
```

### L. Errors inside a procedure

<!-- example: tsql -->
```sql
CREATE PROCEDURE dbo.bad AS SELECT 1 / 0;
GO
BEGIN TRY
    EXEC dbo.bad;
END TRY
BEGIN CATCH
    SELECT ERROR_NUMBER() AS num, ERROR_PROCEDURE() AS proc_name;
END CATCH;
```

```text
num  proc_name
---- ---------
8134 bad

(1 row affected)
```

### M. Functions that do not exist

<!-- example: tsql -->
```sql
SELECT IDENT_CURRENT('dbo.id1');
GO
SELECT NEWSEQUENTIALID();
GO
SELECT HOST_NAME();
GO
SELECT @@OPTIONS;
```

```text
Msg 195, Level 15, State 1, Line 1
'ident_current' is not a recognized built-in function name.
Msg 195, Level 15, State 1, Line 1
'newsequentialid' is not a recognized built-in function name.
Msg 195, Level 15, State 1, Line 1
'host_name' is not a recognized built-in function name.
Msg 195, Level 15, State 1, Line 1
'@@options' is not a recognized built-in function name.
```

## See also

[TRY ... CATCH](try-catch.md), [CREATE SEQUENCE](create-sequence.md), [CREATE TABLE](create-table.md),
[System stored procedures](system-procedures.md)
