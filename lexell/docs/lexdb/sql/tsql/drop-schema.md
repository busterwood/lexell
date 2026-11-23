# DROP SCHEMA (Transact-SQL)

Removes an empty schema.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
DROP SCHEMA [ IF EXISTS ] schema_name
[ ; ]
```

## Arguments

`IF EXISTS`
: A schema that does not exist is no error.

*schema_name*
: The schema to drop. It must hold no objects.

## Remarks

- Drop or move the schema's tables, views, procedures, functions and types first.

## Differences from SQL Server

- A schema that holds objects gives error 50000, "cannot drop schema sales because other objects depend on it"
  (SQL Server: 3729).
- A schema that does not exist gives error 50000, `schema "sales" does not exist` (SQL Server: 3701).

## Examples

### A. Drop a schema

<!-- example: tsql -->
```sql
CREATE SCHEMA sales;
GO
CREATE TABLE sales.orders (id int);
DROP SCHEMA sales;
DROP TABLE sales.orders;
DROP SCHEMA sales;
DROP SCHEMA IF EXISTS sales;
SELECT COUNT(*) AS left_over FROM sys.schemas WHERE name = 'sales';
```

```text
Msg 50000, Level 16, State 1, Line 2
cannot drop schema sales because other objects depend on it
left_over
---------
0

(1 row affected)
```

### B. Errors

<!-- example: tsql -->
```sql
DROP SCHEMA nothere;
```

```text
Msg 50000, Level 16, State 1, Line 1
schema "nothere" does not exist
```

## See also

[CREATE SCHEMA](create-schema.md)
