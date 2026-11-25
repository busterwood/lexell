# DROP ASSERTION

Removes an assertion.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26.1 and later).

## Syntax

```
DROP ASSERTION [ IF EXISTS ] [ schema. ] assertion
```

## Remarks

- An assertion that does not exist is ORA-13650, unless `IF EXISTS` is given.
- Writes to its tables are not checked against it after the drop. The tables are not touched.
- An assertion made in the PostgreSQL or SQL Server door can be dropped here, and one made here from those doors
  (see [Assertions in the three doors](../../assertions.md)).
- `DROP TABLE ... CASCADE CONSTRAINTS` of a table an assertion reads drops the assertion with it; `DROP TABLE` alone is
  ORA-08702 (see [CREATE ASSERTION](create-assertion.md#what-ddl-does-to-its-tables)).
- A name is matched as an unquoted name is, folded to upper case; `DROP ASSERTION "MixA"` drops the one made as
  `"MixA"`.

## Examples

### A. Drop an assertion, and the same again

<!-- example: oracle -->
```sql
CREATE TABLE stock (item NUMBER PRIMARY KEY, qty NUMBER);
CREATE ASSERTION qty_ok CHECK (NOT EXISTS (SELECT 1 FROM stock WHERE qty < 0));
INSERT INTO stock VALUES (1, -3);
DROP ASSERTION qty_ok;
INSERT INTO stock VALUES (1, -3);
DROP ASSERTION qty_ok;
DROP ASSERTION IF EXISTS qty_ok;
```

```text
Table created.

Assertion created.

ERROR:
ORA-08601: Assertion (SA.QTY_OK) violated.

Assertion dropped.

1 row created.

ERROR:
ORA-13650: The specified object does not exist for this execution.

Assertion dropped.
```

### B. DROP TABLE and the assertion that reads it

<!-- example: oracle -->
```sql
CREATE TABLE tmp1 (id NUMBER PRIMARY KEY, v NUMBER);
CREATE ASSERTION tmp_a CHECK (NOT EXISTS (SELECT 1 FROM tmp1 WHERE v < 0));
DROP TABLE tmp1;
DROP TABLE tmp1 CASCADE CONSTRAINTS PURGE;
SELECT COUNT(*) AS n FROM user_assertions WHERE assertion_name = 'TMP_A';
```

```text
Table created.

Assertion created.

ERROR:
ORA-08702: Columns are referenced by assertion SA.TMP_A.

Table dropped.

N
-
0

1 row selected.
```

## See also

[CREATE ASSERTION](create-assertion.md), [ALTER ASSERTION](alter-assertion.md)
