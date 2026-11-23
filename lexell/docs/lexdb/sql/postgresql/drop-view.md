# DROP VIEW

Removes views.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
DROP VIEW [ IF EXISTS ] name [, ...] [ CASCADE | RESTRICT ]
```

## Arguments

`IF EXISTS`
: A view that does not exist is skipped with a notice.

*name*
: A view, optionally schema-qualified.

`CASCADE`
: Also drops the views that read these views.

`RESTRICT`
: Refuses to drop a view that another view reads (2BP01). This is the default.

## Remarks

- Dropping a view changes no table.
- `DROP VIEW` is transactional.
- A table is dropped with [DROP TABLE](drop-table.md); `DROP VIEW` of a table is 42809 (`"t" is not a view (use DROP
  TABLE)`).

## Differences from PostgreSQL

- The refusal of a view with dependents has no `DETAIL` or `HINT`, and `CASCADE` gives no `NOTICE`.

## Examples

<!--setup: postgresql
CREATE TABLE emp (id int PRIMARY KEY, name text, salary numeric(8,2));
CREATE VIEW emp_names AS SELECT name FROM emp;
CREATE VIEW emp_pay AS SELECT name, salary FROM emp;
CREATE VIEW well_paid AS SELECT name FROM emp_pay WHERE salary > 3000;
-->

The examples use these views:

```sql
CREATE TABLE emp (id int PRIMARY KEY, name text, salary numeric(8,2));
CREATE VIEW emp_names AS SELECT name FROM emp;
CREATE VIEW emp_pay AS SELECT name, salary FROM emp;
CREATE VIEW well_paid AS SELECT name FROM emp_pay WHERE salary > 3000;
```

### A. Drop a view

<!-- example: postgresql -->
```sql
DROP VIEW emp_names;
DROP VIEW IF EXISTS emp_names;
```

```text
DROP VIEW
NOTICE:  view "emp_names" does not exist, skipping
DROP VIEW
```

### B. A view that another reads

<!-- example: postgresql -->
```sql
DROP VIEW emp_pay;
DROP VIEW emp_pay CASCADE;
SELECT count(*) FROM pg_views WHERE schemaname = 'public';
```

```text
ERROR:  cannot drop view emp_pay because other objects depend on it
DROP VIEW
 count
-------
     0
(1 row)
```

### C. Errors

<!-- example: postgresql -->
```sql
DROP VIEW emp_names;
DROP VIEW emp;
```

```text
ERROR:  view "emp_names" does not exist
ERROR:  "emp" is not a view (use DROP TABLE)
```

## See also

[CREATE VIEW](create-view.md) · [ALTER VIEW](alter-view.md) · [DROP TABLE](drop-table.md)
