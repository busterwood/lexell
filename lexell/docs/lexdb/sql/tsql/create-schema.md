# CREATE SCHEMA (Transact-SQL)

Makes a schema: a namespace for tables, views, procedures and other objects.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
CREATE SCHEMA schema_name
[ ; ]
```

## Arguments

*schema_name*
: The new schema's name. Objects in it are named `schema_name.object`.

## Remarks

- The default schema is `dbo`; names without a schema are looked up there.
- `sys.schemas` and `INFORMATION_SCHEMA.SCHEMATA` list the schemas.
- `CREATE SCHEMA` is transactional.
- To drop a schema, use [DROP SCHEMA](drop-schema.md).

## Differences from SQL Server

- `AUTHORIZATION owner` is error 50000 when the owner is `dbo` ("role "dbo" does not exist"); the owner must be a
  role or user made with `CREATE ROLE` or `CREATE USER`.
- **Objects listed after the name are made in `dbo`, not in the new schema**: `CREATE SCHEMA hr2 CREATE TABLE emp
  (id int)` makes `dbo.emp`. Make the schema first and name it in each `CREATE`.
- `CREATE SCHEMA dbo` is taken; SQL Server gives error 2714. A schema that exists gives error 50000, `schema "sales"
  already exists` (SQL Server: 2714).
- `CREATE SCHEMA` need not be the first statement of its batch (SQL Server: 111).
- `ALTER SCHEMA ... TRANSFER` is error 50000 ("lexdb: ALTER SCHEMA takes RENAME TO only"): an object cannot be moved
  to another schema.

## Examples

### A. A schema and a table in it

<!-- example: tsql -->
```sql
CREATE SCHEMA sales;
GO
CREATE TABLE sales.orders (id int PRIMARY KEY, total decimal(10,2));
INSERT sales.orders VALUES (1, 9.50);
SELECT * FROM sales.orders;
SELECT SCHEMA_NAME(schema_id) AS schema_name, name FROM sys.tables WHERE name = 'orders';
```

```text
(1 row affected)

id total
-- -----
1  9.50

(1 row affected)

schema_name name
----------- ------
sales       orders

(1 row affected)
```

### B. Objects listed after the name go to dbo

<!-- example: tsql -->
```sql
CREATE SCHEMA hr CREATE TABLE staff (id int) CREATE VIEW v_staff AS SELECT id FROM staff;
GO
SELECT SCHEMA_NAME(schema_id) AS schema_name, name FROM sys.objects WHERE name IN ('staff', 'v_staff') ORDER BY name;
```

```text
schema_name name
----------- -------
dbo         staff
dbo         v_staff

(2 rows affected)
```

### C. Errors

<!-- example: tsql -->
```sql
CREATE SCHEMA sales;
CREATE SCHEMA finance AUTHORIZATION dbo;
GO
ALTER SCHEMA hr TRANSFER sales.orders;
GO
```

```text
Msg 50000, Level 16, State 1, Line 1
schema "sales" already exists
Msg 50000, Level 16, State 1, Line 1
role "dbo" does not exist
Msg 50000, Level 16, State 1, Line 1
lexdb: ALTER SCHEMA takes RENAME TO only
```

## See also

[DROP SCHEMA](drop-schema.md) · [CREATE TABLE](create-table.md) · [CREATE USER](create-user.md)
