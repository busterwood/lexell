# SQL Server door: Transact-SQL reference

The SQL Server door takes T-SQL batches. lexdb follows SQL Server 2022, with parts of SQL Server 2025 (regular
expressions, fuzzy matching, `PRODUCT`, `base64_encode`), and reports itself at login as SQL Server 2022
(16.0.4315). Each page names what lexdb lacks or does differently.

This index lists everything the door takes today. Pages not written yet are listed without a link.

## Statements

### Queries

| Statement | What it does |
|---|---|
| [SELECT](select.md) | Queries; table hints (read and ignored), `OPTION (MAXRECURSION n)`. |
| [TOP](top.md) | `TOP (n) [PERCENT] [WITH TIES]`. |
| [FROM, JOIN and APPLY](from.md) | Joins, `CROSS APPLY` / `OUTER APPLY`, derived tables, table-valued functions. |
| [GROUP BY](select-group-by.md) | Grouping, `ROLLUP`, `CUBE`, `GROUPING SETS`, `HAVING`. |
| [OVER](over.md) | Window functions and the `WINDOW` clause. |
| [ORDER BY](order-by.md) | Sorting, `OFFSET ... FETCH`. |
| [SELECT INTO](select-into.md) | A new table from a query. |
| [UNION, EXCEPT, INTERSECT](set-operators.md) | Set operators. |
| [WITH](with.md) | Common table expressions, recursive ones too. |
| [VALUES](values.md) | Table value constructors. |

### Changing data

| Statement | What it does |
|---|---|
| [INSERT](insert.md) | Adds rows; `OUTPUT`, `INSERT ... EXEC`, `DEFAULT VALUES`. |
| [UPDATE](update.md) | Changes rows; `FROM`, `TOP`, `OUTPUT`, compound assignment (`+=`). |
| [DELETE](delete.md) | Removes rows; `FROM ... JOIN`, `TOP`, `OUTPUT`. |
| [MERGE](merge.md) | Inserts, updates or deletes by a join; `OUTPUT $action`. |
| [TRUNCATE TABLE](truncate-table.md) | Empties a table. |
| [OUTPUT clause](output.md) | The changed rows, as a result set or into a table. |
| [SET IDENTITY_INSERT](set-identity-insert.md) | Explicit values for an identity column. |
| INSERT BULK | The bulk copy protocol's statement (bcp, `SqlBulkCopy`): see [bulk loading](../../bulk-load.md#sql-server-bulk-copy). |

### Tables, indexes and other objects

| Statement | What it does |
|---|---|
| [CREATE TABLE](create-table.md) | `IDENTITY(s, i)`, computed columns, constraints, `#temp` tables. |
| [ALTER TABLE](alter-table.md), [DROP TABLE](drop-table.md) | |
| [CREATE INDEX](create-index.md), [DROP INDEX](drop-index.md) | Unique, filtered, `INCLUDE`. |
| [CREATE VIEW](create-view.md) (and `CREATE OR ALTER VIEW`), [ALTER VIEW](alter-view.md), [DROP VIEW](drop-view.md) | |
| [CREATE PROCEDURE](create-procedure.md) (and `ALTER`, `CREATE OR ALTER`), [DROP PROCEDURE](drop-procedure.md) | Procedures with parameters, `OUTPUT` parameters and return codes. |
| [CREATE FUNCTION](create-function.md) (and `ALTER`, `CREATE OR ALTER`), [DROP FUNCTION](drop-function.md) | Scalar functions and inline table-valued functions (multi-statement ones are made but cannot be read yet). |
| [CREATE TYPE](create-type.md) (and `DROP TYPE`) | Table types (for table-valued parameters). |
| [CREATE SEQUENCE](create-sequence.md), [ALTER SEQUENCE](alter-sequence.md), [DROP SEQUENCE](drop-sequence.md) | `NEXT VALUE FOR`. |
| [CREATE SCHEMA](create-schema.md), [DROP SCHEMA](drop-schema.md) | |
| ALTER DATABASE | `SET` options (most read and kept; `READ_ONLY`, `SINGLE_USER`, `OFFLINE` refused). |
| [sp_rename](sp-rename.md) | Renames a table, column or index. |

### Batches and control of flow

| Statement | What it does |
|---|---|
| [DECLARE](declare-local-variable.md) | Variables and table variables (`DECLARE @t TABLE (...)`). |
| [SET @variable](set-local-variable.md), [SELECT @variable =](select-local-variable.md) | Assignment, compound assignment. |
| [IF ... ELSE](if-else.md), [WHILE, BREAK, CONTINUE](while.md), [BEGIN ... END](begin-end.md), [RETURN](return.md) | |
| [TRY ... CATCH](try-catch.md) | With `ERROR_NUMBER()`, `ERROR_MESSAGE()` and the other error functions, `XACT_STATE()`. |
| [THROW](throw.md), [RAISERROR](raiserror.md), [PRINT](print.md) | |
| [EXECUTE](execute.md) | Procedures (with named, default and `OUTPUT` arguments) and dynamic SQL strings. |
| [USE](use.md) | `lexdb` (or `master`). |

### Transactions

| Statement | What it does |
|---|---|
| [BEGIN TRANSACTION](begin-transaction.md), [COMMIT](commit-transaction.md), [ROLLBACK](rollback-transaction.md), [SAVE TRANSACTION](save-transaction.md) | Named transactions and savepoints; `@@TRANCOUNT`. |
| [SET TRANSACTION ISOLATION LEVEL](set-transaction-isolation-level.md) | Accepted; every read-write transaction is serializable. |
| [SET IMPLICIT_TRANSACTIONS](set-implicit-transactions.md), [SET XACT_ABORT](set-xact-abort.md) | |

### Session

| Statement | What it does |
|---|---|
| SET options | `NOCOUNT`, `XACT_ABORT`, `IMPLICIT_TRANSACTIONS`, `IDENTITY_INSERT`, `ROWCOUNT`, `QUOTED_IDENTIFIER`, `FMTONLY`, and the `ANSI_*` and other options drivers send (accepted). |
| SET LEXDB_DIALECT | lexdb's own: `POSTGRES` makes the rest of the session take PostgreSQL's SQL. |

### Security

| Statement | What it does |
|---|---|
| CREATE USER, CREATE ROLE, DROP USER, DROP ROLE | |
| GRANT, REVOKE | Object permissions (`ON [OBJECT::]name`). |

### System procedures

`sp_executesql`, `sp_prepare`, `sp_execute`, `sp_prepexec`, `sp_unprepare`, `sp_describe_first_result_set`,
`sp_rename`, `sp_tables`, `sp_columns`, `sp_pkeys`, `sp_fkeys`, `sp_statistics`, `sp_special_columns`,
`sp_datatype_info`, `sp_stored_procedures`, `sp_sproc_columns`, `sp_table_privileges`, `sp_column_privileges`,
`sp_tablecollations_100`, `xp_msver`.

### Not in this door

Triggers, synonyms, cursors (`DECLARE CURSOR`, `FETCH`), `WAITFOR`, `GOTO`, `DENY`, `CREATE LOGIN`, `BULK INSERT`,
`OPENROWSET`, `DBCC`, `BACKUP` and `RESTORE`, `KILL`, `RECONFIGURE`.

## Data types

| Type | Names |
|---|---|
| Integers | `tinyint`, `smallint`, `int`, `bigint` |
| Exact numbers | `decimal(p, s)`, `numeric(p, s)`, `money`, `smallmoney` |
| Floating point | `real`, `float(n)` |
| Bit | `bit` |
| Character | `char(n)`, `varchar(n | max)`, `nchar(n)`, `nvarchar(n | max)`, `text`, `ntext`, `sysname` |
| Binary | `binary(n)`, `varbinary(n | max)`, `image`, `rowversion` |
| Date and time | `date`, `time(p)`, `datetime`, `smalldatetime`, `datetime2(p)`, `datetimeoffset(p)` |
| Other | `uniqueidentifier`, `xml` (as text), table types |

Not available: `sql_variant`, `hierarchyid`, `geography`, `geometry`, `cursor`, CLR types.

## Functions

| Family | Functions |
|---|---|
| String | `LEN`, `DATALENGTH`, `LEFT`, `RIGHT`, `SUBSTRING`, `CHARINDEX`, `PATINDEX`, `REPLACE`, `REPLICATE`, `REVERSE`, `STUFF`, `SPACE`, `UPPER`, `LOWER`, `LTRIM`, `RTRIM`, `TRIM`, `CONCAT`, `CONCAT_WS`, `QUOTENAME`, `CHAR`, `NCHAR`, `ASCII`, `TRANSLATE`, `FORMAT`, `STRING_AGG`, `UNISTR`, `BASE64_ENCODE`, `BASE64_DECODE` |
| Regular expressions (2025) | `REGEXP_LIKE`, `REGEXP_REPLACE`, `REGEXP_SUBSTR`, `REGEXP_INSTR`, `REGEXP_COUNT` |
| Fuzzy matching (2025) | `EDIT_DISTANCE`, `EDIT_DISTANCE_SIMILARITY`, `JARO_WINKLER_DISTANCE`, `JARO_WINKLER_SIMILARITY` |
| Mathematical | `ABS`, `CEILING`, `FLOOR`, `ROUND`, `SIGN`, `POWER`, `SQUARE`, `SQRT`, `EXP`, `LOG`, `LOG10`, `PI`, `SIN`, `COS`, `TAN`, `COT`, `ASIN`, `ACOS`, `ATAN`, `DEGREES`, `RADIANS` |
| Bit manipulation | `BIT_COUNT`, `LEFT_SHIFT`, `RIGHT_SHIFT`, `GET_BIT`, `SET_BIT` |
| Date and time | `GETDATE`, `GETUTCDATE`, `SYSDATETIME`, `SYSUTCDATETIME`, `SYSDATETIMEOFFSET`, `CURRENT_TIMESTAMP`, `DATEADD`, `DATEDIFF`, `DATEDIFF_BIG`, `DATEPART`, `DATENAME`, `YEAR`, `MONTH`, `DAY`, `EOMONTH`, `DATEFROMPARTS`, `DATETRUNC`, `DATE_BUCKET` |
| Conversion | `CAST`, `CONVERT` (with styles), `TRY_CAST`, `TRY_CONVERT` |
| Logical | `IIF`, `CHOOSE`, `ISNULL`, `COALESCE`, `NULLIF`, `GREATEST`, `LEAST` |
| Aggregate | `COUNT`, `COUNT_BIG`, `SUM`, `AVG`, `MIN`, `MAX`, `STRING_AGG`, `PRODUCT`, `APPROX_PERCENTILE_CONT`, `APPROX_PERCENTILE_DISC` |
| Window | `ROW_NUMBER`, `RANK`, `DENSE_RANK`, `NTILE`, `PERCENT_RANK`, `CUME_DIST`, `LAG`, `LEAD`, `FIRST_VALUE`, `LAST_VALUE` (with `IGNORE NULLS`), `PERCENTILE_CONT`, `PERCENTILE_DISC`, and aggregates with `OVER` |
| Set-returning | `GENERATE_SERIES`, inline table-valued functions |
| Identity and sequences | `SCOPE_IDENTITY`, `@@IDENTITY`, `NEXT VALUE FOR`, `NEWID` |
| Error handling | `ERROR_NUMBER`, `ERROR_MESSAGE`, `ERROR_SEVERITY`, `ERROR_STATE`, `ERROR_LINE`, `ERROR_PROCEDURE`, `XACT_STATE`, `@@ERROR` |
| Metadata | `OBJECT_ID`, `OBJECT_NAME`, `OBJECT_SCHEMA_NAME`, `OBJECT_DEFINITION`, `OBJECTPROPERTY`, `OBJECTPROPERTYEX`, `COLUMNPROPERTY`, `INDEXPROPERTY`, `TYPE_NAME`, `TYPE_ID`, `SCHEMA_NAME`, `SCHEMA_ID`, `DB_NAME`, `DB_ID`, `DATABASEPROPERTYEX`, `SERVERPROPERTY`, `SESSIONPROPERTY`, `CONNECTIONPROPERTY`, `HAS_PERMS_BY_NAME`, `HAS_DBACCESS`, `IS_MEMBER`, `IS_SRVROLEMEMBER` |
| Security and session | `USER_NAME`, `SUSER_NAME`, `SUSER_SNAME`, `SUSER_SID`, `ORIGINAL_LOGIN`, `SYSTEM_USER`, `CONTEXT_INFO` |
| System variables | `@@ROWCOUNT`, `@@TRANCOUNT`, `@@SPID`, `@@VERSION`, `@@SERVERNAME`, `@@SERVICENAME`, `@@LANGUAGE`, `@@NESTLEVEL`, `@@PROCID`, `@@DATEFIRST`, `@@MAX_PRECISION`, `@@TEXTSIZE`, `@@LOCK_TIMEOUT` and others |

Not available: `UNICODE`, `STDEV`, `STDEVP`, `VAR`, `VARP`, `ATN2`, `SOUNDEX`, `DIFFERENCE`, `STR`, `ISNUMERIC`, `ISDATE`, `HASHBYTES`, `CHECKSUM` functions, JSON
functions (`JSON_VALUE`, `OPENJSON`), `STRING_SPLIT`, `PARSE`, `TRY_PARSE`, `RAND`, `IDENT_CURRENT`,
`SWITCHOFFSET`, `TODATETIMEOFFSET`.

## Operators

Arithmetic `+ - * / %`; string concatenation `+`; bitwise `& | ^ ~` and (2022) `<< >>`; comparison `= <> != < <= >
>=`; compound assignment `+= -= *= /= %= &= |= ^=`; `LIKE` (with `[ ]` patterns), `IN`, `BETWEEN`, `EXISTS`,
`ANY`/`SOME`/`ALL`, `IS [NOT] NULL`, `IS [NOT] DISTINCT FROM`; `AND`, `OR`, `NOT`; `COLLATE`.

## System catalog views

- **sys**: `sys.tables`, `sys.columns`, `sys.objects`, `sys.schemas`, `sys.types`, `sys.indexes`,
  `sys.index_columns`, `sys.key_constraints`, `sys.foreign_keys`, `sys.foreign_key_columns`,
  `sys.check_constraints`, `sys.default_constraints`, `sys.identity_columns`, `sys.computed_columns`,
  `sys.views`, `sys.procedures`, `sys.parameters`, `sys.sql_modules`, `sys.sequences`, `sys.table_types`,
  `sys.databases`, `sys.database_principals`, `sys.server_principals`, `sys.database_permissions`,
  `sys.dm_exec_sessions`, `sys.all_objects`, `sys.all_columns`, `sys.stats`, `sys.extended_properties` and the
  others the SQL Server tools read (empty where lexdb has no such object).
- **INFORMATION_SCHEMA**: `TABLES`, `COLUMNS`, `VIEWS`, `TABLE_CONSTRAINTS`, `KEY_COLUMN_USAGE`,
  `REFERENTIAL_CONSTRAINTS`, `ROUTINES`, `PARAMETERS` and the others, with PostgreSQL's columns.

## Errors

Errors carry SQL Server's numbers and severities: 208 (invalid object name), 207 (invalid column name), 102
(incorrect syntax), 2627 and 2601 (duplicate key), 515 (NULL not allowed), 547 (constraint conflict), 2628 (string
truncated), 8134 (divide by zero), 245 and 8114 (conversion), 1205 (serialization failure: retry), 3906
(read-only replica), 3902 and 3903 (no transaction), 2812 (no such procedure), 50000 (not supported by lexdb, and
`RAISERROR` messages).
