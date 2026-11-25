# System stored procedures (Transact-SQL)

The system procedures lexdb has: dynamic SQL, result-set description, the catalog procedures that drivers call,
and a few server procedures. [sp_rename](sp-rename.md) has its own page.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
EXEC sp_executesql @stmt [ , @params [ , @param1 = value [ OUTPUT ] [ ,...n ] ] ]
EXEC sp_describe_first_result_set @tsql [ , @params ]
EXEC sp_refreshview [ @viewname = ] 'view'

EXEC sp_tables [ @table_name = ] name [ , [ @table_owner = ] schema ] [ , [ @table_type = ] "'TABLE', 'VIEW'" ]
EXEC sp_columns [ @table_name = ] name [ , [ @table_owner = ] schema ] [ , [ @column_name = ] column ]
EXEC sp_pkeys [ @table_name = ] name [ , [ @table_owner = ] schema ]
EXEC sp_fkeys [ @pktable_name = ] name | [ @fktable_name = ] name
EXEC sp_statistics [ @table_name = ] name
EXEC sp_special_columns [ @table_name = ] name
EXEC sp_stored_procedures [ [ @sp_name = ] name ]
EXEC sp_sproc_columns [ @procedure_name = ] name
EXEC sp_table_privileges [ @table_name = ] name
EXEC sp_column_privileges [ @table_name = ] name
EXEC sp_datatype_info [ data_type ]
EXEC sp_tablecollations_100 'schema.table'

EXEC xp_msver
EXEC xp_instance_regread ...
```

## The procedures

### Dynamic SQL and description

`sp_executesql`
: Runs a string of T-SQL with typed parameters. `@params` declares them (`N'@d int, @c int OUTPUT'`); the arguments
  follow by name. Output parameters come back to the caller's variables.

`sp_describe_first_result_set`
: Describes the columns of a query's first result set without running it: name, nullability, type, length,
  precision, scale and collation, one row per column.

`sp_refreshview`
: Makes a view again from its stored text, so that a `SELECT *` view takes its table's columns as they are now (see
  [CREATE VIEW](create-view.md), example H). A name that is not a view is error 15165.

`sp_prepare`, `sp_execute`, `sp_prepexec`, `sp_unprepare`
: Prepared statements. Drivers call them as RPC requests, and lexdb takes them there. Called by `EXEC` in a batch
  they are error 2812.

### Catalog procedures

ODBC and JDBC drivers call these for their metadata functions (`getTables`, `getColumns`, `getPrimaryKeys` ...).
Their result sets have SQL Server's columns.

| Procedure | Returns |
|---|---|
| `sp_tables` | Tables and views. |
| `sp_columns` | A table's columns, with ODBC types. |
| `sp_pkeys` | A table's primary key columns. |
| `sp_fkeys` | Foreign keys to or from a table. |
| `sp_statistics` | A table's indexes. |
| `sp_special_columns` | The columns that identify a row (the primary key). |
| `sp_stored_procedures` | Procedures, named `name;1` as SQL Server names them. |
| `sp_sproc_columns` | A procedure's parameters, with `@RETURN_VALUE` first. |
| `sp_table_privileges`, `sp_column_privileges` | Permissions on a table and its columns. |
| `sp_datatype_info` | The types, SQL Server 2022's 37 rows. |
| `sp_tablecollations_100` (and `_90`, plain) | A table's columns' collations, for bulk copy. |

### Server procedures

`xp_msver`
: The server's version rows, as SQL Server 2022 (16.0.4315) gives them. Its `ProcessorCount` and `PhysicalMemory`
  rows are the machine's.

`xp_instance_regread`, `xp_regread`
: lexdb has no registry: an `OUTPUT` argument is set to NULL, and no rows come back.

## Remarks

- A batch that starts with a system procedure's name runs it without `EXEC`.
- An unknown procedure is error 2812.

## Differences from SQL Server

- `sp_help`, `sp_helptext`, `sp_helpindex`, `sp_helpdb`, `sp_who`, `sp_spaceused`, `sp_configure`,
  `sp_server_info`, `sp_addrolemember` and `sp_sequence_get_range` are not available (2812).
- `sp_datatype_info` returns every type whatever its argument.
- `sp_prepare`, `sp_execute`, `sp_prepexec` and `sp_unprepare` work as RPC only.

## Examples

<!--setup: tsql
CREATE TABLE dbo.emp (id int PRIMARY KEY, name nvarchar(30), boss int REFERENCES dbo.emp (id));
CREATE INDEX ix_emp_boss ON dbo.emp (boss);
INSERT dbo.emp VALUES (1, N'Ann', NULL), (2, N'Bob', 1), (3, N'Cid', 1);
-->

The examples use one table:

```sql
CREATE TABLE dbo.emp (id int PRIMARY KEY, name nvarchar(30), boss int REFERENCES dbo.emp (id));
CREATE INDEX ix_emp_boss ON dbo.emp (boss);
INSERT dbo.emp VALUES (1, N'Ann', NULL), (2, N'Bob', 1), (3, N'Cid', 1);
```

### A. sp_executesql with input and output parameters

<!-- example: tsql -->
```sql
DECLARE @n int;
EXEC sp_executesql N'SELECT @c = COUNT(*) FROM dbo.emp WHERE boss = @b',
                   N'@b int, @c int OUTPUT', @b = 1, @c = @n OUTPUT;
SELECT @n AS reports;
```

```text
reports
-------
2

(1 row affected)
```

### B. sp_describe_first_result_set

<!-- example: tsql -->
```sql
EXEC sp_describe_first_result_set N'SELECT id, name, boss FROM dbo.emp';
```

```text
is_hidden column_ordinal name is_nullable system_type_id system_type_name max_length precision scale collation_name               user_type_id user_type_database user_type_schema user_type_name assembly_qualified_type_name xml_collection_id xml_collection_database xml_collection_schema xml_collection_name is_xml_document is_case_sensitive is_fixed_length_clr_type source_server source_database source_schema source_table source_column is_identity_column is_part_of_unique_key is_updateable is_computed_column is_sparse_column_set ordinal_in_order_by_list order_by_is_descending order_by_list_length tds_type_id tds_length tds_collation_id tds_collation_sort_id
--------- -------------- ---- ----------- -------------- ---------------- ---------- --------- ----- ---------------------------- ------------ ------------------ ---------------- -------------- ---------------------------- ----------------- ----------------------- --------------------- ------------------- --------------- ----------------- ------------------------ ------------- --------------- ------------- ------------ ------------- ------------------ --------------------- ------------- ------------------ -------------------- ------------------------ ---------------------- -------------------- ----------- ---------- ---------------- ---------------------
0         1              id   0           56             int              4          10        0     NULL                         NULL         NULL               NULL             NULL           NULL                         NULL              NULL                    NULL                  NULL                0               0                 0                        NULL          NULL            NULL          NULL         NULL          0                  NULL                  1             0                  0                    NULL                     NULL                   NULL                 56          4          NULL             NULL
0         2              name 1           231            nvarchar(30)     60         0         0     SQL_Latin1_General_CP1_CI_AS NULL         NULL               NULL             NULL           NULL                         NULL              NULL                    NULL                  NULL                0               0                 0                        NULL          NULL            NULL          NULL         NULL          0                  NULL                  1             0                  0                    NULL                     NULL                   NULL                 231         60         13632521         52
0         3              boss 1           56             int              4          10        0     NULL                         NULL         NULL               NULL             NULL           NULL                         NULL              NULL                    NULL                  NULL                0               0                 0                        NULL          NULL            NULL          NULL         NULL          0                  NULL                  1             0                  0                    NULL                     NULL                   NULL                 38          4          NULL             NULL

(3 rows affected)
```

### C. Tables, keys and indexes

<!-- example: tsql -->
```sql
EXEC sp_tables @table_name = 'emp';
EXEC sp_pkeys @table_name = 'emp';
EXEC sp_fkeys @pktable_name = 'emp';
EXEC sp_statistics @table_name = 'emp';
```

```text
TABLE_QUALIFIER TABLE_OWNER TABLE_NAME TABLE_TYPE REMARKS
--------------- ----------- ---------- ---------- -------
lexdb           dbo         emp        TABLE      NULL

(1 row affected)

TABLE_QUALIFIER TABLE_OWNER TABLE_NAME COLUMN_NAME KEY_SEQ PK_NAME
--------------- ----------- ---------- ----------- ------- --------
lexdb           dbo         emp        id          1       emp_pkey

(1 row affected)

PKTABLE_QUALIFIER PKTABLE_OWNER PKTABLE_NAME PKCOLUMN_NAME FKTABLE_QUALIFIER FKTABLE_OWNER FKTABLE_NAME FKCOLUMN_NAME KEY_SEQ UPDATE_RULE DELETE_RULE FK_NAME       PK_NAME  DEFERRABILITY
----------------- ------------- ------------ ------------- ----------------- ------------- ------------ ------------- ------- ----------- ----------- ------------- -------- -------------
lexdb             dbo           emp          id            lexdb             dbo           emp          boss          1       1           1           emp_boss_fkey emp_pkey 7

(1 row affected)

TABLE_QUALIFIER TABLE_OWNER TABLE_NAME NON_UNIQUE INDEX_QUALIFIER INDEX_NAME  TYPE SEQ_IN_INDEX COLUMN_NAME COLLATION CARDINALITY PAGES FILTER_CONDITION
--------------- ----------- ---------- ---------- --------------- ----------- ---- ------------ ----------- --------- ----------- ----- ----------------
lexdb           dbo         emp        NULL       NULL            NULL        0    NULL         NULL        NULL      0           0     NULL
lexdb           dbo         emp        0          emp             emp_pkey    1    1            id          A         0           0     NULL
lexdb           dbo         emp        1          emp             ix_emp_boss 3    1            boss        A         NULL        NULL  NULL

(3 rows affected)
```

### D. Columns

<!-- example: tsql -->
```sql
EXEC sp_columns @table_name = 'emp';
```

```text
TABLE_QUALIFIER TABLE_OWNER TABLE_NAME COLUMN_NAME DATA_TYPE TYPE_NAME PRECISION LENGTH SCALE RADIX NULLABLE REMARKS COLUMN_DEF SQL_DATA_TYPE SQL_DATETIME_SUB CHAR_OCTET_LENGTH ORDINAL_POSITION IS_NULLABLE SS_IS_SPARSE SS_IS_COLUMN_SET SS_IS_COMPUTED SS_IS_IDENTITY SS_UDT_CATALOG_NAME SS_UDT_SCHEMA_NAME SS_UDT_ASSEMBLY_TYPE_NAME SS_XML_SCHEMACOLLECTION_CATALOG_NAME SS_XML_SCHEMACOLLECTION_SCHEMA_NAME SS_XML_SCHEMACOLLECTION_NAME SS_DATA_TYPE
--------------- ----------- ---------- ----------- --------- --------- --------- ------ ----- ----- -------- ------- ---------- ------------- ---------------- ----------------- ---------------- ----------- ------------ ---------------- -------------- -------------- ------------------- ------------------ ------------------------- ------------------------------------ ----------------------------------- ---------------------------- ------------
lexdb           dbo         emp        id          4         int       10        4      0     10    0        NULL    NULL       4             NULL             NULL              1                NO          0            0                0              0              NULL                NULL               NULL                      NULL                                 NULL                                NULL                         56
lexdb           dbo         emp        name        -9        nvarchar  30        60     NULL  NULL  1        NULL    NULL       -9            NULL             60                2                YES         0            0                0              0              NULL                NULL               NULL                      NULL                                 NULL                                NULL                         231
lexdb           dbo         emp        boss        4         int       10        4      0     10    1        NULL    NULL       4             NULL             NULL              3                YES         0            0                0              0              NULL                NULL               NULL                      NULL                                 NULL                                NULL                         38

(3 rows affected)
```

### E. Procedures and their parameters

<!-- example: tsql -->
```sql
CREATE PROCEDURE dbo.reports_of @boss int, @n int OUTPUT AS SELECT @n = COUNT(*) FROM dbo.emp WHERE boss = @boss;
GO
EXEC sp_stored_procedures @sp_name = 'reports_of';
EXEC sp_sproc_columns @procedure_name = 'reports_of';
```

```text
PROCEDURE_QUALIFIER PROCEDURE_OWNER PROCEDURE_NAME NUM_INPUT_PARAMS NUM_OUTPUT_PARAMS NUM_RESULT_SETS REMARKS PROCEDURE_TYPE
------------------- --------------- -------------- ---------------- ----------------- --------------- ------- --------------
lexdb               dbo             reports_of;1   -1               -1                -1              NULL    2

(1 row affected)

PROCEDURE_QUALIFIER PROCEDURE_OWNER PROCEDURE_NAME COLUMN_NAME   COLUMN_TYPE DATA_TYPE TYPE_NAME PRECISION LENGTH SCALE RADIX NULLABLE REMARKS COLUMN_DEF SQL_DATA_TYPE SQL_DATETIME_SUB CHAR_OCTET_LENGTH ORDINAL_POSITION IS_NULLABLE SS_DATA_TYPE
------------------- --------------- -------------- ------------- ----------- --------- --------- --------- ------ ----- ----- -------- ------- ---------- ------------- ---------------- ----------------- ---------------- ----------- ------------
lexdb               dbo             reports_of;1   @RETURN_VALUE 5           4         int       10        4      0     10    0        NULL    NULL       4             NULL             NULL              0                NO          56
lexdb               dbo             reports_of;1   @boss         1           4         int       10        4      0     10    1        NULL    NULL       4             NULL             NULL              1                YES         38
lexdb               dbo             reports_of;1   @n            2           4         int       10        4      0     10    1        NULL    NULL       4             NULL             NULL              2                YES         38

(3 rows affected)
```

### F. Privileges and collations

<!-- example: tsql -->
```sql
EXEC sp_table_privileges @table_name = 'emp';
EXEC sp_tablecollations_100 'dbo.emp';
```

```text
TABLE_QUALIFIER TABLE_OWNER TABLE_NAME GRANTOR GRANTEE PRIVILEGE  IS_GRANTABLE
--------------- ----------- ---------- ------- ------- ---------- ------------
lexdb           dbo         emp        dbo     dbo     DELETE     YES
lexdb           dbo         emp        dbo     dbo     INSERT     YES
lexdb           dbo         emp        dbo     dbo     REFERENCES YES
lexdb           dbo         emp        dbo     dbo     SELECT     YES
lexdb           dbo         emp        dbo     dbo     UPDATE     YES

(5 rows affected)

colid name tds_collation collation
----- ---- ------------- ----------------------------
1     id   NULL          NULL
2     name 0904D00034    SQL_Latin1_General_CP1_CI_AS
3     boss NULL          NULL

(3 rows affected)
```

### G. Errors

<!-- example: tsql -->
```sql
EXEC sp_help 'dbo.emp';
DECLARE @h int;
EXEC sp_prepare @h OUTPUT, N'@i int', N'SELECT name FROM dbo.emp WHERE id = @i';
```

```text
Msg 2812, Level 16, State 62, Line 1
Could not find stored procedure 'sp_help'.
Msg 2812, Level 16, State 62, Line 3
Could not find stored procedure 'sp_prepare'.
```

## See also

[EXECUTE](execute.md) · [sp_rename](sp-rename.md) · [Bulk copy](../../bulk-load.md#sql-server-bulk-copy)
