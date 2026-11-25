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
| [FROM, JOIN and APPLY](from.md) | Joins, `CROSS APPLY` / `OUTER APPLY`, derived tables, table-valued functions, [`GRAPH_TABLE`](graph-table.md). |
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
| [ALTER TABLE](alter-table.md), [DROP TABLE](drop-table.md) | Columns and constraints; `WITH NOCHECK`, `NOCHECK CONSTRAINT`, `CHECK CONSTRAINT`. |
| [CREATE INDEX](create-index.md), [DROP INDEX](drop-index.md) | Unique, filtered, `INCLUDE`. |
| [CREATE VIEW](create-view.md) (and `CREATE OR ALTER VIEW`), [ALTER VIEW](alter-view.md), [DROP VIEW](drop-view.md) | |
| [CREATE PROCEDURE](create-procedure.md) (and `ALTER`, `CREATE OR ALTER`), [DROP PROCEDURE](drop-procedure.md) | Procedures with parameters, `OUTPUT` parameters and return codes. |
| [CREATE FUNCTION](create-function.md) (and `ALTER`, `CREATE OR ALTER`), [DROP FUNCTION](drop-function.md) | Scalar functions and inline table-valued functions (multi-statement ones are made but cannot be read yet). |
| [CREATE TYPE](create-type.md) (and `DROP TYPE`) | Table types (for table-valued parameters). |
| [CREATE SEQUENCE](create-sequence.md), [ALTER SEQUENCE](alter-sequence.md), [DROP SEQUENCE](drop-sequence.md) | `NEXT VALUE FOR`. |
| [CREATE ASSERTION](create-assertion.md), [DROP ASSERTION](drop-assertion.md) | The SQL standard's constraint across tables; lexdb's own here (SQL Server has none); `DEFERRABLE`. |
| [CREATE PROPERTY GRAPH](create-property-graph.md), [DROP PROPERTY GRAPH](drop-property-graph.md) | SQL:2023 property graphs (SQL/PGQ; SQL Server has none), queried with [`GRAPH_TABLE`](graph-table.md). |
| [CREATE SCHEMA](create-schema.md), [DROP SCHEMA](drop-schema.md) | |
| [ALTER DATABASE](alter-database.md) | `SET` options (most read and kept; `READ_ONLY`, `SINGLE_USER`, `OFFLINE` refused). |
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
| [SET CONSTRAINTS](set-constraints.md) | lexdb's own: defers or runs the check of an assertion. |

### Session

| Statement | What it does |
|---|---|
| [SET options](set-statements.md) | `NOCOUNT`, `XACT_ABORT`, `IMPLICIT_TRANSACTIONS`, `IDENTITY_INSERT`, `ROWCOUNT`, `QUOTED_IDENTIFIER`, `FMTONLY`, and the `ANSI_*` and other options drivers send (accepted). |
| [SET LEXDB_DIALECT](set-lexdb-dialect.md) | lexdb's own: `POSTGRES` makes the rest of the session take PostgreSQL's SQL. |

### Security

| Statement | What it does |
|---|---|
| [CREATE USER](create-user.md), [CREATE ROLE](create-role.md), [DROP USER](drop-user.md), [DROP ROLE](drop-role.md) | Membership by `GRANT role TO user`. |
| [GRANT](grant.md), [REVOKE](revoke.md) | Object permissions (`ON [OBJECT::]name`). |

### System procedures

See [System stored procedures](system-procedures.md) and [sp_rename](sp-rename.md).

`sp_executesql`, `sp_prepare`, `sp_execute`, `sp_prepexec`, `sp_unprepare`, `sp_describe_first_result_set`,
`sp_rename`, `sp_tables`, `sp_columns`, `sp_pkeys`, `sp_fkeys`, `sp_statistics`, `sp_special_columns`,
`sp_datatype_info`, `sp_stored_procedures`, `sp_sproc_columns`, `sp_table_privileges`, `sp_column_privileges`,
`sp_tablecollations_100`, `xp_msver`.

### Not in this door

Triggers, synonyms, cursors (`DECLARE CURSOR`, `FETCH`), `WAITFOR`, `GOTO`, `DENY`, `CREATE LOGIN`, `BULK INSERT`,
`OPENROWSET`, `DBCC`, `BACKUP` and `RESTORE`, `KILL`, `RECONFIGURE`.

## Data types

| Page | Types |
|---|---|
| [Numeric types](data-types-numeric.md) | `tinyint`, `smallint`, `int`, `bigint`, `decimal(p, s)`, `numeric(p, s)`, `money`, `smallmoney`, `real`, `float(n)` |
| [Character types](data-types-character.md) | `char(n)`, `varchar(n | max)`, `nchar(n)`, `nvarchar(n | max)`, `text`, `ntext`, `sysname` |
| [Binary types](data-types-binary.md) | `binary(n)`, `varbinary(n | max)`, `image`, `rowversion` |
| [Date and time types](data-types-datetime.md) | `date`, `time(p)`, `datetime`, `smalldatetime`, `datetime2(p)`, `datetimeoffset(p)` |
| [Other types](data-types-other.md) | `bit`, `uniqueidentifier`, `xml` (as text), `sql_variant`, table types |

Not available: `hierarchyid`, `geography`, `geometry`, `cursor`, CLR types.

## Functions

| Page | Functions |
|---|---|
| [String functions](functions-string.md) | `LEN`, `DATALENGTH`, `LEFT`, `RIGHT`, `SUBSTRING`, `CHARINDEX`, `PATINDEX`, `REPLACE`, `REPLICATE`, `REVERSE`, `STUFF`, `SPACE`, `UPPER`, `LOWER`, `LTRIM`, `RTRIM`, `TRIM`, `CONCAT`, `CONCAT_WS`, `QUOTENAME`, `CHAR`, `NCHAR`, `ASCII`, `TRANSLATE`, `UNISTR`, `BASE64_ENCODE`, `BASE64_DECODE`, `STRING_AGG` |
| [FORMAT](functions-format.md) | `FORMAT` with .NET format strings |
| [Regular expressions and fuzzy matching](functions-regex-fuzzy.md) | `REGEXP_LIKE`, `REGEXP_REPLACE`, `REGEXP_SUBSTR`, `REGEXP_INSTR`, `REGEXP_COUNT`, `EDIT_DISTANCE`, `EDIT_DISTANCE_SIMILARITY`, `JARO_WINKLER_DISTANCE`, `JARO_WINKLER_SIMILARITY` (2025) |
| [Mathematical and bit functions](functions-math.md) | `ABS`, `CEILING`, `FLOOR`, `ROUND`, `SIGN`, `POWER`, `SQUARE`, `SQRT`, `EXP`, `LOG`, `LOG10`, `PI`, `SIN`, `COS`, `TAN`, `COT`, `ASIN`, `ACOS`, `ATAN`, `DEGREES`, `RADIANS`, `BIT_COUNT`, `LEFT_SHIFT`, `RIGHT_SHIFT`, `GET_BIT`, `SET_BIT` |
| [Logical functions and CASE](functions-logical.md) | `IIF`, `CHOOSE`, `ISNULL`, `COALESCE`, `NULLIF`, `GREATEST`, `LEAST`, `CASE` |
| [Conversion functions](functions-conversion.md) | `CAST`, `CONVERT` (with styles), `TRY_CAST`, `TRY_CONVERT` |
| [Date and time functions](functions-datetime.md) | `GETDATE`, `GETUTCDATE`, `SYSDATETIME`, `SYSUTCDATETIME`, `SYSDATETIMEOFFSET`, `CURRENT_TIMESTAMP`, `DATEADD`, `DATEDIFF`, `DATEDIFF_BIG`, `DATEPART`, `DATENAME`, `YEAR`, `MONTH`, `DAY`, `EOMONTH`, `DATEFROMPARTS`, `DATETRUNC`, `DATE_BUCKET`, `SWITCHOFFSET`, `TODATETIMEOFFSET`, `AT TIME ZONE` |
| [Aggregate functions](functions-aggregate.md) | `COUNT`, `COUNT_BIG`, `SUM`, `AVG`, `MIN`, `MAX`, `STRING_AGG`, `PRODUCT`, `APPROX_PERCENTILE_CONT`, `APPROX_PERCENTILE_DISC` |
| [Window functions](functions-window.md) | `ROW_NUMBER`, `RANK`, `DENSE_RANK`, `NTILE`, `PERCENT_RANK`, `CUME_DIST`, `LAG`, `LEAD`, `FIRST_VALUE`, `LAST_VALUE`, `NTH_VALUE`, `PERCENTILE_CONT`, `PERCENTILE_DISC`; see also [OVER](over.md) |
| [System, identity, error and metadata functions](functions-system.md) | `@@ROWCOUNT`, `@@ERROR`, `@@TRANCOUNT`, `SCOPE_IDENTITY`, `@@IDENTITY`, `NEXT VALUE FOR`, `NEWID`, `ERROR_NUMBER` and the other error functions, `XACT_STATE`, `@@VERSION` and the other system variables, `SERVERPROPERTY`, `DB_NAME`, `OBJECT_ID`, `OBJECT_NAME`, `OBJECTPROPERTY`, `COLUMNPROPERTY`, `TYPE_NAME`, `USER_NAME`, `SUSER_SNAME`, `IS_MEMBER`, `HAS_PERMS_BY_NAME` and others |

`GENERATE_SERIES` and inline table-valued functions are on [FROM](from.md) and [CREATE FUNCTION](create-function.md).

Not available: `UNICODE`, `STDEV`, `STDEVP`, `VAR`, `VARP`, `ATN2`, `SOUNDEX`, `DIFFERENCE`, `STR`, `ISNUMERIC`,
`ISDATE`, `HASHBYTES`, `CHECKSUM`, JSON functions (`JSON_VALUE`, `OPENJSON`), `STRING_SPLIT`, `PARSE`, `TRY_PARSE`,
`RAND`, `IDENT_CURRENT`. The pages above show each one's error.

## Operators

[Operators](operators.md): arithmetic `+ - * / %`; string concatenation `+`; bitwise `& | ^ ~ << >>`; comparison
`= <> != < <= > >=`; compound assignment `+= -= *= /= %= &= |= ^=`; `LIKE` (with `[ ]` patterns), `IN`, `BETWEEN`,
`EXISTS`, `ANY`/`SOME`/`ALL`, `IS [NOT] NULL`, `IS [NOT] DISTINCT FROM`; `AND`, `OR`, `NOT`; `COLLATE`.

## System catalog views

| Page | Views |
|---|---|
| [Schemas, tables, columns and indexes](catalog-tables.md) | `sys.schemas`, `sys.objects`, `sys.tables`, `sys.columns`, `sys.types`, `sys.indexes`, `sys.index_columns`, `sys.identity_columns`, `sys.computed_columns`, `sys.all_objects`, `sys.all_columns` |
| [Constraints](catalog-constraints.md) | `sys.key_constraints`, `sys.foreign_keys`, `sys.foreign_key_columns`, `sys.check_constraints`, `sys.default_constraints` |
| [Views, procedures, sequences and types](catalog-programmability.md) | `sys.views`, `sys.procedures`, `sys.parameters`, `sys.sql_modules`, `sys.sequences`, `sys.table_types` |
| [Databases, principals and the server](catalog-security.md) | `sys.databases`, `sys.database_principals`, `sys.server_principals`, `sys.database_permissions`, `sys.dm_exec_sessions`, `sys.configurations`, and the views lexdb leaves empty |
| [INFORMATION_SCHEMA views](catalog-information-schema.md) | `TABLES`, `COLUMNS`, `VIEWS`, `TABLE_CONSTRAINTS`, `KEY_COLUMN_USAGE`, `REFERENTIAL_CONSTRAINTS`, `ROUTINES`, `PARAMETERS` and the others, with PostgreSQL's columns |

## Errors

[Errors](errors.md) lists the error numbers lexdb gives, with their causes and examples: 208 (invalid object name),
207 (invalid column name), 102 (incorrect syntax), 2627 (duplicate key), 515 (NULL not allowed), 547 (constraint
conflict), 2628 (string truncated), 245 and 8114 (conversion), 8134 (divide by zero), 1205 (serialization failure:
retry), 3906 (read-only replica), 3902 and 3903 (no transaction), 2812 (no such procedure), and 50000 (not
supported by lexdb, and `RAISERROR` messages).
