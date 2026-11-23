# CREATE TYPE (Transact-SQL)

Makes a table type, for table variables and table-valued parameters. `DROP TYPE` removes one.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
CREATE TYPE [ schema_name. ] type_name AS TABLE
    ( { column_definition | table_constraint } [ ,...n ] )
[ ; ]

DROP TYPE [ IF EXISTS ] [ schema_name. ] type_name
[ ; ]
```

## Arguments

*type_name*
: The type's name, with its schema (`dbo` by default).

*column_definition*, *table_constraint*
: As in [CREATE TABLE](create-table.md): types, `NULL`/`NOT NULL`, `DEFAULT`, `IDENTITY`, `PRIMARY KEY`, `UNIQUE`,
  `CHECK`.

## Remarks

- `DECLARE @v type_name` makes a table variable of the type; its constraints are checked as rows go in.
- A procedure's parameter of the type, marked `READONLY`, is a table-valued parameter.
- `sys.types` (with `is_table_type` 1) and `sys.table_types` show the type.
- A type that exists is error 219; dropping one that does not is error 218.

## Differences from SQL Server

- Only table types: alias types (`CREATE TYPE phone FROM varchar(20)`) are error 156, and CLR types are not
  supported.
- An index in the type (`INDEX ix (col)`) is error 102.
- A type that a procedure's parameter uses can be dropped (SQL Server: 3732).
- A table-valued parameter cannot be passed from a T-SQL batch (see [CREATE PROCEDURE](create-procedure.md)); clients
  pass it over RPC.

## Examples

### A. A table type and a table variable of it

<!-- example: tsql -->
```sql
CREATE TYPE dbo.id_list AS TABLE (id int PRIMARY KEY, note nvarchar(20) NULL);
GO
DECLARE @ids dbo.id_list;
INSERT @ids VALUES (2, N'b'), (1, N'a');
SELECT * FROM @ids ORDER BY id;
```

```text
(2 rows affected)

id note
-- ----
1  a
2  b

(2 rows affected)
```

### B. The catalog

<!-- example: tsql -->
```sql
SELECT name, is_table_type FROM sys.types WHERE name = 'id_list';
SELECT name FROM sys.table_types;
```

```text
name    is_table_type
------- -------------
id_list 1

(1 row affected)

name
-------
id_list

(1 row affected)
```

### C. Drop a type

<!-- example: tsql -->
```sql
CREATE TYPE dbo.scratch AS TABLE (a int);
DROP TYPE dbo.scratch;
DROP TYPE IF EXISTS dbo.scratch;
SELECT COUNT(*) AS left_over FROM sys.table_types WHERE name = 'scratch';
```

```text
left_over
---------
0

(1 row affected)
```

### D. Errors

<!-- example: tsql -->
```sql
DECLARE @ids dbo.id_list;
INSERT @ids VALUES (1, N'a'), (1, N'again');
GO
CREATE TYPE dbo.id_list AS TABLE (x int);
DROP TYPE dbo.nothere;
GO
CREATE TYPE dbo.phone FROM varchar(20) NOT NULL;
GO
```

```text
Msg 2627, Level 14, State 1, Line 1
duplicate key value violates unique constraint "#tv_ids_pkey"
Msg 219, Level 16, State 1, Line 1
The type 'dbo.id_list' already exists, or you do not have permission to create it.
Msg 218, Level 16, State 1, Line 1
Could not find the type 'dbo.nothere'. Either it does not exist or you do not have the necessary permission.
Msg 156, Level 15, State 1, Line 1
Incorrect syntax near the keyword 'from'.
```

## See also

[DECLARE @local_variable](declare-local-variable.md) · [CREATE PROCEDURE](create-procedure.md) ·
[CREATE TABLE](create-table.md)
