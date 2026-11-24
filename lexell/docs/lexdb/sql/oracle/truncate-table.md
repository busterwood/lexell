# TRUNCATE TABLE

Removes all rows of a table at once.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
TRUNCATE TABLE [ schema. ] table [ CASCADE ]
```

`TABLE` may be left out in lexdb (`TRUNCATE emp`).

## Arguments

*table*
: The table to empty. It must be a table, not a view.

`CASCADE`
: Also empties the tables that have a foreign key to this table.

## Remarks

- `TRUNCATE` is a DDL statement as in Oracle: it ends the transaction that is open (it commits), and it cannot
  be rolled back. After `TRUNCATE TABLE emp; ROLLBACK;` the table is still empty.
- The table, its indexes and constraints stay. An identity column goes on from its last value (example A).
- A table that another table's foreign key points at cannot be truncated without `CASCADE` (ORA-03001; Oracle
  gives ORA-02266).
- Inside PL/SQL, write the statement as `EXECUTE IMMEDIATE 'TRUNCATE TABLE emp'`.
- On a replica, `TRUNCATE` of a table is ORA-16000.

## Differences from Oracle

- Oracle's storage clauses (`DROP STORAGE`, `REUSE STORAGE`, `DROP ALL STORAGE`) and `PRESERVE MATERIALIZED VIEW
  LOG` are not supported (ORA-00900), nor is `TRUNCATE CLUSTER`.
- `CASCADE` empties the tables with a foreign key to the table, whether or not the key is `ON DELETE CASCADE`.
  Oracle's `CASCADE` follows only keys declared `ON DELETE CASCADE`.
- The table is found in the current schema (the login's own, or the one `ALTER SESSION SET CURRENT_SCHEMA` set), then
  in `public`, the PostgreSQL door's schema. `TRUNCATE TABLE sa.emp` works for a table that `SA` made, and
  `public.emp` for one the PostgreSQL door made. A table made in another user's schema is named `user.table`.

## Examples

<!--setup: oracle
CREATE TABLE dept (id NUMBER(4) PRIMARY KEY, name VARCHAR2(30) NOT NULL);
CREATE TABLE emp (id NUMBER(4) PRIMARY KEY, name VARCHAR2(30) NOT NULL, dept_id NUMBER(4) REFERENCES dept (id));
INSERT INTO dept VALUES (1, 'Sales');
INSERT INTO dept VALUES (2, 'Research');
INSERT INTO emp VALUES (1, 'Ann', 1);
INSERT INTO emp VALUES (2, 'Bob', 2);
COMMIT;
-->

The examples use a department table and an employee table that points at it.

### A. Empty a table

<!-- example: oracle -->
```sql
CREATE TABLE log_line (id NUMBER GENERATED ALWAYS AS IDENTITY, msg VARCHAR2(20));
INSERT INTO log_line (msg) VALUES ('a');
INSERT INTO log_line (msg) VALUES ('b');
TRUNCATE TABLE log_line;
SELECT COUNT(*) AS n FROM log_line;
INSERT INTO log_line (msg) VALUES ('c');
SELECT id, msg FROM log_line;
```

```text
Table created.

1 row created.

1 row created.

Table truncated.

N
-
0

1 row selected.

1 row created.

ID MSG
-- ---
 3 c

1 row selected.
```

### B. TRUNCATE cannot be rolled back

<!-- example: oracle -->
```sql
INSERT INTO emp VALUES (3, 'Cid', 1);
TRUNCATE TABLE emp;
ROLLBACK;
SELECT COUNT(*) AS n FROM emp;
```

```text
1 row created.

Table truncated.

Rollback complete.

N
-
0

1 row selected.
```

### C. A table with a foreign key to it

<!-- example: oracle -->
```sql
INSERT INTO emp VALUES (1, 'Ann', 1);
COMMIT;
TRUNCATE TABLE dept;
TRUNCATE TABLE dept CASCADE;
SELECT COUNT(*) AS depts FROM dept;
SELECT COUNT(*) AS emps FROM emp;
```

```text
1 row created.

Commit complete.

ERROR:
ORA-03001: unimplemented feature: cannot truncate a table referenced in a foreign key constraint: Table "emp" references "dept". Truncate table "emp" at the same time, or use TRUNCATE ... CASCADE.

Table truncated.

DEPTS
-----
    0

1 row selected.

EMPS
----
   0

1 row selected.
```

### D. In PL/SQL, and errors

<!-- example: oracle -->
```sql
BEGIN
  EXECUTE IMMEDIATE 'TRUNCATE TABLE emp';
  DBMS_OUTPUT.PUT_LINE('truncated');
END;
/
TRUNCATE TABLE nosuch;
CREATE VIEW emp_v AS SELECT * FROM emp;
TRUNCATE TABLE emp_v;
TRUNCATE TABLE emp DROP STORAGE;
```

```text
truncated

PL/SQL procedure successfully completed.

ERROR:
ORA-00942: table or view "SA"."NOSUCH" does not exist

View created.

ERROR:
ORA-20000: "emp_v" is not a table

ERROR:
ORA-00900: invalid SQL statement
```

## See also

[DELETE](delete.md) · [INSERT](insert.md) · [CREATE TABLE](create-table.md) · [DROP TABLE](drop-table.md)
