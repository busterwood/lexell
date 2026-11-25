# DROP ASSERTION

Removes an assertion.

**Door:** PostgreSQL. **Follows:** the SQL standard, not PostgreSQL: PostgreSQL has no assertions.

## Syntax

```
DROP ASSERTION [ IF EXISTS ] [ schema. ] name
```

## Remarks

- An assertion that does not exist is 42704 (`assertion "name" does not exist`), unless `IF EXISTS` is given.
- `CASCADE` and `RESTRICT` are 42601: the standard's statement has neither, and nothing depends on an assertion.
- Writes to its tables are not checked against it after the drop. The tables are not touched.
- An assertion made in the SQL Server or Oracle door can be dropped here, and one made here from those doors (see
  [Assertions in the three doors](../../assertions.md)).
- `DROP TABLE ... CASCADE` of a table an assertion reads drops the assertion with it; `DROP TABLE` alone is 2BP01 (see
  [CREATE ASSERTION](create-assertion.md#what-ddl-does-to-its-tables)).

## Examples

### A. Drop an assertion

<!-- example: postgresql -->
```sql
CREATE TABLE stock (item int PRIMARY KEY, qty int);
CREATE ASSERTION qty_ok CHECK (NOT EXISTS (SELECT 1 FROM stock WHERE qty < 0));
INSERT INTO stock VALUES (1, -3);
DROP ASSERTION qty_ok;
INSERT INTO stock VALUES (1, -3);
DROP ASSERTION qty_ok;
DROP ASSERTION IF EXISTS qty_ok;
DROP ASSERTION qty_ok CASCADE;
```

```text
CREATE TABLE
CREATE ASSERTION
ERROR:  assertion "qty_ok" is violated
DROP ASSERTION
INSERT 0 1
ERROR:  assertion "qty_ok" does not exist
DROP ASSERTION
ERROR:  syntax error at or near "cascade"
```

## See also

[CREATE ASSERTION](create-assertion.md), [SET CONSTRAINTS](set-constraints.md)
