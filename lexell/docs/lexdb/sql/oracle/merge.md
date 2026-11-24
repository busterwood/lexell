# MERGE

Inserts, updates or deletes rows of a target table according to a join with a source.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
MERGE INTO [ schema. ] target [ t_alias ]
    USING { [ schema. ] table | view | ( subquery ) } [ s_alias ]
    ON ( condition )
    [ WHEN MATCHED THEN
        UPDATE SET column = { expr | DEFAULT } [, column = ... ]...
        [ WHERE condition ]
        [ DELETE WHERE condition ] ]
    [ WHEN NOT MATCHED THEN
        INSERT [ ( column [, column ]... ) ] VALUES ( { expr | DEFAULT } [, ...] )
        [ WHERE condition ] ]
```

The two `WHEN` clauses may come in either order.

## Arguments

`INTO` *target*
: The table that changes. *t_alias* names it in the other clauses.

`USING`
: The source: a table, a view, an inline view, or `DUAL` for a single row of constants.

`ON`
: The join condition. A source row that meets it for a target row is *matched*. The condition's columns of the
  target cannot be updated (ORA-38104).

`WHEN MATCHED THEN UPDATE SET`
: For each matched row, sets the columns. Without `WHERE`, every matched row is updated.

`UPDATE ... WHERE`
: Updates only the matched rows for which the condition holds. It may use the source's columns and the target's
  old values.

`DELETE WHERE`
: After the update, deletes the rows for which the condition holds; it sees the new values. The deleted rows are
  those the `UPDATE` also changed, so `DELETE` needs an `UPDATE` clause before it.

`WHEN NOT MATCHED THEN INSERT`
: For each source row that matches no target row, inserts a row. Without a column list the values are for all the
  columns in order. `WHERE` limits the source rows inserted.

## Remarks

- The result is `N rows merged.`: the rows updated, deleted and inserted together. In PL/SQL `SQL%ROWCOUNT` gives
  the same count.
- A target row that two source rows match is ORA-30926.
- The columns of the target are named without an alias in `INSERT ( ... )`; `s.id` there is a syntax error.
- The first `MERGE` begins a transaction, which `COMMIT` or `ROLLBACK` ends. A statement that fails is undone alone.
- Constraint errors are those of `INSERT` and `UPDATE`.
- On a replica, `MERGE` into a table is ORA-16000.

## Differences from Oracle

- A `WHEN MATCHED THEN DELETE` without `UPDATE` (standard SQL's form) is not supported (ORA-02000, "missing UPDATE
  keyword").
- **A subquery in a clause reads rows the `MERGE` has already changed.** `UPDATE` and `DELETE` work every row out
  from the table as the statement found it, as Oracle does; `MERGE` does not yet. `MERGE INTO emp e USING (SELECT
  id FROM emp WHERE mgr_id IS NOT NULL) s ON (e.id = s.id) WHEN MATCHED THEN UPDATE SET e.salary = (SELECT x.salary
  * 2 FROM emp x WHERE x.id = e.mgr_id)` over a chain of managers doubles a salary that the same statement has just
  changed. Use an `UPDATE` where the statement needs the starting rows.
- `LOG ERRORS` is not supported (ORA-00900). `RETURNING` after `MERGE` was not tried.
- A hint after `MERGE` (`/*+ PARALLEL */`) is read as a comment.

## Examples

<!--setup: oracle
CREATE TABLE stock (id NUMBER PRIMARY KEY, name VARCHAR2(20), qty NUMBER);
CREATE TABLE delivery (id NUMBER, name VARCHAR2(20), qty NUMBER);
INSERT INTO stock VALUES (1, 'pencil', 10);
INSERT INTO stock VALUES (2, 'eraser', 5);
INSERT INTO stock VALUES (3, 'ruler', 0);
INSERT INTO delivery VALUES (2, 'eraser', 20);
INSERT INTO delivery VALUES (3, 'ruler', 4);
INSERT INTO delivery VALUES (4, 'stapler', 7);
COMMIT;
-->

The examples use a stock list and a delivery note. Each example ends with `ROLLBACK`.

```sql
CREATE TABLE stock (id NUMBER PRIMARY KEY, name VARCHAR2(20), qty NUMBER);
CREATE TABLE delivery (id NUMBER, name VARCHAR2(20), qty NUMBER);
INSERT INTO stock VALUES (1, 'pencil', 10);
INSERT INTO stock VALUES (2, 'eraser', 5);
INSERT INTO stock VALUES (3, 'ruler', 0);
INSERT INTO delivery VALUES (2, 'eraser', 20);
INSERT INTO delivery VALUES (3, 'ruler', 4);
INSERT INTO delivery VALUES (4, 'stapler', 7);
```

### A. Update what matches, insert what does not

<!-- example: oracle -->
```sql
MERGE INTO stock s USING delivery d ON (s.id = d.id)
WHEN MATCHED THEN UPDATE SET s.qty = s.qty + d.qty
WHEN NOT MATCHED THEN INSERT (id, name, qty) VALUES (d.id, d.name, d.qty);
SELECT * FROM stock ORDER BY id;
ROLLBACK;
```

```text
3 rows merged.

ID NAME    QTY
-- ------- ---
 1 pencil   10
 2 eraser   25
 3 ruler     4
 4 stapler   7

4 rows selected.

Rollback complete.
```

### B. DELETE WHERE

Rows that reach more than 10 after the update are removed.

<!-- example: oracle -->
```sql
MERGE INTO stock s USING delivery d ON (s.id = d.id)
WHEN MATCHED THEN UPDATE SET s.qty = s.qty + d.qty DELETE WHERE (s.qty > 10)
WHEN NOT MATCHED THEN INSERT (id, name, qty) VALUES (d.id, d.name, d.qty);
SELECT * FROM stock ORDER BY id;
ROLLBACK;
```

```text
3 rows merged.

ID NAME    QTY
-- ------- ---
 1 pencil   10
 3 ruler     4
 4 stapler   7

3 rows selected.

Rollback complete.
```

### C. Conditions on UPDATE and INSERT

<!-- example: oracle -->
```sql
MERGE INTO stock s USING delivery d ON (s.id = d.id)
WHEN MATCHED THEN UPDATE SET s.qty = d.qty WHERE d.qty > 4;
SELECT * FROM stock ORDER BY id;
ROLLBACK;
MERGE INTO stock s USING delivery d ON (s.id = d.id)
WHEN NOT MATCHED THEN INSERT (id, name, qty) VALUES (d.id, d.name, d.qty) WHERE d.qty > 10;
SELECT * FROM stock ORDER BY id;
ROLLBACK;
```

```text
1 row merged.

ID NAME   QTY
-- ------ ---
 1 pencil  10
 2 eraser  20
 3 ruler    0

3 rows selected.

Rollback complete.

0 rows merged.

ID NAME   QTY
-- ------ ---
 1 pencil  10
 2 eraser   5
 3 ruler    0

3 rows selected.

Rollback complete.
```

### D. Only one WHEN clause, in either order

<!-- example: oracle -->
```sql
MERGE INTO stock s USING delivery d ON (s.id = d.id) WHEN NOT MATCHED THEN INSERT (id, name) VALUES (d.id, d.name);
SELECT * FROM stock ORDER BY id;
ROLLBACK;
MERGE INTO stock s USING delivery d ON (s.id = d.id)
WHEN NOT MATCHED THEN INSERT (id, name, qty) VALUES (d.id, d.name, d.qty)
WHEN MATCHED THEN UPDATE SET s.qty = d.qty;
SELECT * FROM stock ORDER BY id;
ROLLBACK;
```

```text
1 row merged.

ID NAME    QTY
-- ------- ---
 1 pencil   10
 2 eraser    5
 3 ruler     0
 4 stapler

4 rows selected.

Rollback complete.

3 rows merged.

ID NAME    QTY
-- ------- ---
 1 pencil   10
 2 eraser   20
 3 ruler     4
 4 stapler   7

4 rows selected.

Rollback complete.
```

### E. A subquery or DUAL as the source

<!-- example: oracle -->
```sql
MERGE INTO stock s
USING (SELECT 1 AS id, 'pencil' AS name, 5 AS qty FROM dual UNION ALL SELECT 9, 'glue', 3 FROM dual) d ON (s.id = d.id)
WHEN MATCHED THEN UPDATE SET s.qty = s.qty - d.qty
WHEN NOT MATCHED THEN INSERT VALUES (d.id, d.name, d.qty);
SELECT * FROM stock ORDER BY id;
ROLLBACK;
MERGE INTO stock s USING dual ON (s.id = 50)
WHEN MATCHED THEN UPDATE SET qty = qty + 1
WHEN NOT MATCHED THEN INSERT (id, name, qty) VALUES (50, 'pen', 1);
SELECT * FROM stock WHERE id = 50;
ROLLBACK;
```

```text
2 rows merged.

ID NAME   QTY
-- ------ ---
 1 pencil   5
 2 eraser   5
 3 ruler    0
 9 glue     3

4 rows selected.

Rollback complete.

1 row merged.

ID NAME QTY
-- ---- ---
50 pen    1

1 row selected.

Rollback complete.
```

### F. SQL%ROWCOUNT in PL/SQL

<!-- example: oracle -->
```sql
DECLARE
  n NUMBER;
BEGIN
  MERGE INTO stock s USING delivery d ON (s.id = d.id)
  WHEN MATCHED THEN UPDATE SET s.qty = s.qty + d.qty
  WHEN NOT MATCHED THEN INSERT (id, name, qty) VALUES (d.id, d.name, d.qty);
  n := SQL%ROWCOUNT;
  DBMS_OUTPUT.PUT_LINE('merged ' || n);
  ROLLBACK;
END;
/
```

```text
merged 3

PL/SQL procedure successfully completed.
```

### G. Errors

<!-- example: oracle -->
```sql
MERGE INTO stock s USING delivery d ON (s.id = d.id) WHEN MATCHED THEN UPDATE SET s.id = d.id;
MERGE INTO stock s USING (SELECT 2 AS id, 1 AS qty FROM dual UNION ALL SELECT 2, 2 FROM dual) d ON (s.id = d.id)
WHEN MATCHED THEN UPDATE SET s.qty = d.qty;
MERGE INTO stock s USING delivery d ON (s.id = d.id) WHEN MATCHED THEN UPDATE SET s.nosuch = 1;
MERGE INTO stock s USING delivery d ON (s.id = d.id) WHEN NOT MATCHED THEN INSERT (id, name, qty) VALUES (d.id, 'x', 'y');
MERGE INTO stock s USING delivery d ON (s.id = d.id) WHEN MATCHED THEN DELETE;
MERGE INTO stock s USING delivery d ON (s.id = d.id) WHEN MATCHED THEN UPDATE SET s.qty = d.qty LOG ERRORS INTO e;
MERGE INTO stock s USING delivery d ON (s.id = d.id) WHEN NOT MATCHED THEN INSERT (s.id, s.name, s.qty) VALUES (d.id, d.name, d.qty);
ROLLBACK;
```

```text
ERROR:
ORA-38104: Columns referenced in the ON Clause cannot be updated: "S"."ID"

ERROR:
ORA-30926: The operation attempted to update the same row twice.

ERROR:
ORA-00904: "NOSUCH": invalid identifier

ERROR:
ORA-01722: invalid number

ERROR:
ORA-02000: missing UPDATE keyword

ERROR:
ORA-00900: invalid SQL statement

ERROR:
ORA-00900: invalid SQL statement

Rollback complete.
```

## See also

[INSERT](insert.md) · [UPDATE](update.md) · [DELETE](delete.md) · [SELECT](select.md)
