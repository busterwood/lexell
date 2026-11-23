# COMMENT ON

Gives a table or column a comment.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
COMMENT ON { TABLE [ schema. ] table | COLUMN [ schema. ] table.column } IS 'text'
```

## Remarks

- The statement is accepted and **the comment is not kept**: `USER_TAB_COMMENTS` and `USER_COL_COMMENTS` list the
  table and its columns with an empty comment.
- A table that does not exist is not an error (see the examples).

## Differences from Oracle

- Comments are not stored.
- `COMMENT ON` a table that does not exist succeeds; Oracle gives ORA-00942.
- Comments on other objects (`INDEXTYPE`, `OPERATOR`, `MATERIALIZED VIEW`, ...) were not checked.

## Examples

<!--setup: oracle
CREATE TABLE staff (id NUMBER, name VARCHAR2(20));
-->

### A. Comment on a table and a column

<!-- example: oracle -->
```sql
COMMENT ON TABLE staff IS 'Staff of the company';
COMMENT ON COLUMN staff.name IS 'Full name';
SELECT comments FROM user_tab_comments WHERE table_name = 'STAFF';
SELECT column_name, comments FROM user_col_comments WHERE table_name = 'STAFF' AND column_name = 'NAME';
```

```text
Comment created.

Comment created.

COMMENTS
--------


1 row selected.

COLUMN_NAME COMMENTS
----------- --------
NAME

1 row selected.
```

### B. A table that is not there

<!-- example: oracle -->
```sql
COMMENT ON TABLE nothere IS 'x';
```

```text
Comment created.
```

## See also

[CREATE TABLE](create-table.md), [ALTER TABLE](alter-table.md)
