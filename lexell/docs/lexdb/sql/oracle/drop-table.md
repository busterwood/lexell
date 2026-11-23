# DROP TABLE

Removes a table, its rows, its indexes and its constraints.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
DROP TABLE [ IF EXISTS ] [ schema. ] table [ CASCADE CONSTRAINTS ] [ PURGE ]
```

## Arguments

`IF EXISTS`
: No error when the table does not exist (23ai).

`CASCADE CONSTRAINTS`
: Drops the foreign keys of other tables that point at this one. Without it, a table that others reference is
  ORA-02449.

`PURGE`
: Accepted. lexdb has no recycle bin, so every drop is final.

## Remarks

- The table's indexes, constraints and rows go with it.
- A table that does not exist is ORA-00942.
- To empty a table and keep it, use [TRUNCATE TABLE](truncate-table.md).

## Differences from Oracle

- `DROP TABLE` without `PURGE` does not keep the table in a recycle bin (no `FLASHBACK TABLE ... TO BEFORE DROP`).
- None other known.

## Examples

### A. Drop a table

<!-- example: oracle -->
```sql
CREATE TABLE staff (id NUMBER);
DROP TABLE staff;
DROP TABLE staff;
```

```text
Table created.

Table dropped.

ERROR:
ORA-00942: table or view "SA"."STAFF" does not exist
```

### B. A table that other tables reference

<!-- example: oracle -->
```sql
CREATE TABLE p (id NUMBER PRIMARY KEY);
CREATE TABLE c (id NUMBER, p_id NUMBER REFERENCES p (id));
DROP TABLE p;
DROP TABLE p CASCADE CONSTRAINTS;
SELECT COUNT(*) AS foreign_keys_left FROM user_constraints WHERE table_name = 'C' AND constraint_type = 'R';
```

```text
Table created.

Table created.

ERROR:
ORA-02449: unique/primary keys in table referenced by foreign keys

Table dropped.

FOREIGN_KEYS_LEFT
-----------------
                0

1 row selected.
```

### C. PURGE

<!-- example: oracle -->
```sql
CREATE TABLE q (id NUMBER);
DROP TABLE q PURGE;
SELECT COUNT(*) AS q_left FROM user_tables WHERE table_name = 'Q';
```

```text
Table created.

Table dropped.

Q_LEFT
------
     0

1 row selected.
```

### D. IF EXISTS

<!-- example: oracle -->
```sql
DROP TABLE IF EXISTS nothere;
```

```text
Table dropped.
```

## See also

[CREATE TABLE](create-table.md), [TRUNCATE TABLE](truncate-table.md), [ALTER TABLE](alter-table.md)
