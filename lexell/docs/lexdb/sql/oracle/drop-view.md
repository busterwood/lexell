# DROP VIEW

Removes a view.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
DROP VIEW [ schema. ] view
```

## Remarks

- The tables the view reads are not touched.
- A view that does not exist is ORA-00942.

## Differences from Oracle

- A view that another view reads cannot be dropped: ORA-02449 (example B). Oracle drops it and marks the other view invalid.

## Examples

### A. Drop a view

<!-- example: oracle -->
```sql
CREATE TABLE t (a NUMBER);
CREATE VIEW v AS SELECT a FROM t;
DROP VIEW v;
DROP VIEW v;
```

```text
Table created.

View created.

View dropped.

ERROR:
ORA-00942: table or view "SA"."V" does not exist
```

### B. A view that another view reads

<!-- example: oracle -->
```sql
CREATE TABLE t2 (a NUMBER);
CREATE VIEW inner_v AS SELECT a FROM t2;
CREATE VIEW outer_v AS SELECT a FROM inner_v;
DROP VIEW inner_v;
SELECT * FROM outer_v;
```

```text
Table created.

View created.

View created.

ERROR:
ORA-02449: unique/primary keys in table referenced by foreign keys

no rows selected
```

## See also

[CREATE VIEW](create-view.md)
