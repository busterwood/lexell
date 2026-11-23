# ALTER VIEW

Renames a view or gives it a new owner.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
ALTER VIEW [ IF EXISTS ] name RENAME TO new_name
ALTER VIEW [ IF EXISTS ] name OWNER TO { new_owner | CURRENT_USER | SESSION_USER }
```

## Arguments

`IF EXISTS`
: If the view does not exist, does nothing and gives a notice.

*name*
: The view, optionally schema-qualified.

*new_name*
: Its new name, in the same schema.

*new_owner*
: The role that is to own the view.

## Remarks

- To change a view's query, use `CREATE OR REPLACE VIEW` (see [CREATE VIEW](create-view.md)).
- `ALTER VIEW` is transactional.

## Differences from PostgreSQL

- Not supported (0A000, `lexdb: ALTER VIEW supports RENAME TO only`): `SET SCHEMA`, `ALTER COLUMN ... SET DEFAULT`,
  `SET ( view_option )` and `RESET`. `RENAME COLUMN` is a syntax error.

## Examples

<!--setup: postgresql
CREATE TABLE emp (id int PRIMARY KEY, name text);
CREATE VIEW emp_names AS SELECT name FROM emp;
-->

The examples use one view:

```sql
CREATE TABLE emp (id int PRIMARY KEY, name text);
CREATE VIEW emp_names AS SELECT name FROM emp;
```

### A. Rename a view

<!-- example: postgresql -->
```sql
ALTER VIEW emp_names RENAME TO staff_names;
SELECT viewname FROM pg_views WHERE schemaname = 'public';
```

```text
ALTER VIEW
  viewname
-------------
 staff_names
(1 row)
```

### B. A new owner

<!-- example: postgresql -->
```sql
CREATE ROLE reporting;
ALTER VIEW staff_names OWNER TO reporting;
SELECT viewname, viewowner FROM pg_views WHERE viewname = 'staff_names';
```

```text
CREATE ROLE
ALTER VIEW
  viewname   | viewowner
-------------+-----------
 staff_names | reporting
(1 row)
```

### C. IF EXISTS, and what is refused

<!-- example: postgresql -->
```sql
ALTER VIEW IF EXISTS nosuch RENAME TO other;
ALTER VIEW staff_names SET SCHEMA public;
ALTER VIEW staff_names RENAME COLUMN name TO who;
```

```text
NOTICE:  relation "nosuch" does not exist, skipping
ALTER VIEW
ERROR:  lexdb: ALTER VIEW supports RENAME TO only
ERROR:  syntax error at or near "column"
```

## See also

[CREATE VIEW](create-view.md) · [DROP VIEW](drop-view.md)
