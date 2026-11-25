# DROP ASSERTION (Transact-SQL)

Removes an assertion.

**Door:** SQL Server (TDS). **Follows:** the SQL standard, not SQL Server: SQL Server has no assertions.

## Syntax

```
DROP ASSERTION [ IF EXISTS ] [ schema_name . ] assertion_name
[ ; ]
```

## Arguments

`IF EXISTS`
: An assertion that does not exist is no error.

## Remarks

- An assertion that does not exist is error 3701 (`Cannot drop the assertion 'a', because it does not exist or you do
  not have permission.`), unless `IF EXISTS` is given. A schema that is not there is 2760.
- Writes to its tables are not checked against it after the drop. The tables are not touched.
- An assertion made in the PostgreSQL or Oracle door can be dropped here, and one made here from those doors (see
  [Assertions in the three doors](../../assertions.md)).
- `DROP TABLE` of a table an assertion reads is 3729; drop the assertion first (see
  [CREATE ASSERTION](create-assertion.md#what-ddl-does-to-its-tables)).

## Examples

### A. Drop an assertion

<!-- example: tsql -->
```sql
CREATE TABLE dbo.stock (item int PRIMARY KEY, qty int);
GO
CREATE ASSERTION qty_ok CHECK (NOT EXISTS (SELECT 1 FROM dbo.stock WHERE qty < 0))
GO
INSERT dbo.stock VALUES (1, -3);
GO
DROP ASSERTION qty_ok;
GO
INSERT dbo.stock VALUES (1, -3);
GO
DROP ASSERTION qty_ok;
GO
DROP ASSERTION IF EXISTS qty_ok;
```

```text
Msg 547, Level 16, State 1, Line 1
The INSERT statement conflicted with the assertion "qty_ok". The conflict occurred in database "lexdb", table "dbo.stock".
(1 row affected)

Msg 3701, Level 11, State 1, Line 1
Cannot drop the assertion 'qty_ok', because it does not exist or you do not have permission.
```

## See also

[CREATE ASSERTION](create-assertion.md), [SET CONSTRAINTS](set-constraints.md)
