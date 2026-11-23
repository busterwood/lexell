# EXPLAIN

Shows the plan lexdb chooses for a statement; `EXPLAIN ANALYZE` runs a query and adds what it read.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18's statement, with lexdb's own plan text.

## Syntax

```
EXPLAIN statement
EXPLAIN ANALYZE select_statement
```

## Arguments

*statement*
: A `SELECT` (or `WITH ... SELECT`, `VALUES`), `UPDATE`, `DELETE` or `MERGE`. It is planned, not run.

`ANALYZE`
: Runs the query, which must be a `SELECT`, and adds to each scan the rows it read and kept and the batches it
  made, and a last line with the rows returned and the time taken.

## Remarks

- The result is one text column, `QUERY PLAN`, one row per step, in the order the steps run. Indented lines belong
  to the subquery above them.
- The steps:

  | Line | What it means |
  |---|---|
  | `scan t: full scan` | every row of `t`, in key order |
  | `scan t: primary key lookup` | rows found by the primary key (`for each of n values` for an `IN` list) |
  | `scan t: primary key range` | a range of the primary key |
  | `scan t: index i lookup` | rows found by index `i`; `index only` when the index has every column needed; `(filtered)` for a partial index |
  | `rows in key order` | the rows come in the index's order, so no sort is needed |
  | `join t: primary key lookup per row` | a join that looks up `t` for each row before it |
  | `join t: hash on (cols) over ...` | a hash join: `t` is read once into a hash table |
  | `semi join`, `anti join` | `EXISTS`, `IN`, `NOT EXISTS` and `NOT IN` |
  | `aggregate` | grouping and aggregates |
  | `order: sort` | a sort for `ORDER BY` |
  | `subquery n (from): run once` | a subquery in `FROM`, a view or a `WITH` query |
  | `range delete: ...` | a `DELETE` that drops a range of the primary key (see [DELETE](delete.md)) |
  | `(estimated n rows)` | the planner's estimate, where it has statistics |

- Plans depend on the statistics that `ANALYZE` gathers (on its own by default) and on `SET lexdb_planner`: `cost`,
  the default, or `rules` for the older rule-based plans.
- `EXPLAIN` of a `DELETE` evaluates its bounds, so a scalar subquery in them runs.

## Differences from PostgreSQL

- The plan text is lexdb's, not PostgreSQL's tree of nodes with costs (`Seq Scan on t (cost=...)`). Tools that parse
  PostgreSQL's plans cannot read it.
- The options list (`EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) ...`) and `VERBOSE` are syntax errors.
- `EXPLAIN INSERT` is refused (0A000), and `EXPLAIN ANALYZE` takes only `SELECT` (0A000).
- `EXPLAIN ANALYZE`'s times change from run to run, so this page shows none of its output.

## Examples

<!--setup: postgresql
CREATE TABLE dept (id int PRIMARY KEY, name text);
CREATE TABLE emp (id int PRIMARY KEY, name text, dept int, salary int);
CREATE INDEX emp_dept ON emp (dept);
INSERT INTO dept SELECT g, 'd' || g FROM generate_series(0, 9) g;
INSERT INTO emp SELECT g, 'e' || g, g % 10, 1000 + g FROM generate_series(1, 1000) g;
ANALYZE;
-->

The examples use two tables:

```sql
CREATE TABLE dept (id int PRIMARY KEY, name text);
CREATE TABLE emp (id int PRIMARY KEY, name text, dept int, salary int);
CREATE INDEX emp_dept ON emp (dept);
INSERT INTO dept SELECT g, 'd' || g FROM generate_series(0, 9) g;
INSERT INTO emp SELECT g, 'e' || g, g % 10, 1000 + g FROM generate_series(1, 1000) g;
ANALYZE;
```

### A. Scans

<!-- example: postgresql -->
```sql
EXPLAIN SELECT * FROM emp WHERE id = 5;
EXPLAIN SELECT * FROM emp WHERE id IN (1, 2, 3);
EXPLAIN SELECT name FROM emp WHERE dept = 3;
EXPLAIN SELECT count(*) FROM emp WHERE dept = 3;
EXPLAIN SELECT * FROM emp WHERE salary > 1500;
```

```text
          QUERY PLAN
------------------------------
 scan emp: primary key lookup
(1 row)

                    QUERY PLAN
---------------------------------------------------
 scan emp: primary key lookup for each of 3 values
(1 row)

                     QUERY PLAN
----------------------------------------------------
 scan emp: index emp_dept lookup, rows in key order
(1 row)

                 QUERY PLAN
---------------------------------------------
 scan emp: index emp_dept lookup, index only
 aggregate
(2 rows)

     QUERY PLAN
---------------------
 scan emp: full scan
(1 row)
```

### B. A join, grouping and a sort

<!-- example: postgresql -->
```sql
EXPLAIN SELECT d.name, count(*) FROM emp e JOIN dept d ON d.id = e.dept GROUP BY d.name ORDER BY 2 DESC LIMIT 3;
SET lexdb_planner = rules;
EXPLAIN SELECT d.name, count(*) FROM emp e JOIN dept d ON d.id = e.dept GROUP BY d.name ORDER BY 2 DESC LIMIT 3;
RESET lexdb_planner;
```

```text
                QUERY PLAN
------------------------------------------
 scan emp e: full scan
 join dept d: hash on (id) over full scan
 aggregate
 order: sort
(4 rows)

SET
               QUERY PLAN
-----------------------------------------
 scan emp e: full scan
 join dept d: primary key lookup per row
 aggregate
 order: sort
(4 rows)

RESET
```

### C. Subqueries

<!-- example: postgresql -->
```sql
EXPLAIN SELECT * FROM emp e WHERE EXISTS (SELECT 1 FROM dept d WHERE d.id = e.dept AND d.name = 'd3');
EXPLAIN SELECT * FROM dept d WHERE NOT EXISTS (SELECT 1 FROM emp e WHERE e.dept = d.id);
EXPLAIN WITH w AS (SELECT * FROM emp WHERE dept = 1) SELECT count(*) FROM w;
```

```text
                        QUERY PLAN
-----------------------------------------------------------
 scan emp e: full scan
 semi join d: hash on (id) over rows of subquery 1
 subquery 1 (exists): semi join on d.id = e.dept, run once
   scan dept d: full scan
(4 rows)

                          QUERY PLAN
---------------------------------------------------------------
 scan dept d: full scan
 anti join e: index emp_dept lookup, index only per row
 subquery 1 (exists): anti join, looked up per row by the join
(3 rows)

                      QUERY PLAN
------------------------------------------------------
 scan w: rows of subquery 1
 aggregate
 subquery 1 (from): run once
   scan emp: index emp_dept lookup, rows in key order
(4 rows)
```

### D. UPDATE, DELETE and MERGE

<!-- example: postgresql -->
```sql
EXPLAIN UPDATE emp SET salary = salary + 1 WHERE dept = 3;
EXPLAIN DELETE FROM emp WHERE id < 10;
EXPLAIN MERGE INTO emp e USING dept d ON e.id = d.id WHEN MATCHED THEN UPDATE SET name = d.name;
```

```text
                     QUERY PLAN
----------------------------------------------------
 scan emp: index emp_dept lookup, rows in key order
(1 row)

                                            QUERY PLAN
---------------------------------------------------------------------------------------------------
 scan emp: primary key range
 range delete: primary key range, subtrees dropped (0 of 1 indexes cut by range, 1 entry by entry)
(2 rows)

               QUERY PLAN
----------------------------------------
 scan dept d: full scan
 join emp e: primary key lookup per row
(2 rows)
```

### E. Errors

<!-- example: postgresql -->
```sql
EXPLAIN INSERT INTO emp VALUES (2000, 'x', 1, 1);
EXPLAIN ANALYZE UPDATE emp SET salary = 1;
EXPLAIN (FORMAT JSON) SELECT 1;
```

```text
ERROR:  EXPLAIN takes SELECT, UPDATE, DELETE or MERGE
ERROR:  EXPLAIN ANALYZE takes SELECT
ERROR:  syntax error at or near "("
```

## See also

[SELECT](select.md) · [CREATE INDEX](create-index.md) · ANALYZE
