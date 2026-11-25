# UPDATE (Transact-SQL)

Changes the values of rows in a table or a table variable.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
[ WITH common_table_expression [ ,...n ] ]
UPDATE
    [ TOP ( expression ) ]
    { table_name | table_alias | @table_variable | #temp_table }
    [ WITH ( table_hint [ ,...n ] ) ]
    SET
        { column_name = { expression | DEFAULT | NULL }
        | column_name { += | -= | *= | /= | %= | &= | ^= | |= } expression
        } [ ,...n ]
    [ OUTPUT output_list [ INTO { @table_variable | table_name } [ ( column_list ) ] ] ]
    [ FROM table_source [ ,...n ] ]
    [ WHERE search_condition ]
    [ OPTION ( query_hint [ ,...n ] ) ]
    [ WITH ( batch_rows n ) ]
[ ; ]
```

## Arguments

*common_table_expression*
: A named query the statement can read in `FROM`, `WHERE` or `SET`. See [WITH](with.md).

`TOP (` *expression* `)`
: Changes at most this many rows, picked in no order. See [TOP](top.md).

*table_name*
: The table to change: `t`, `dbo.t`, `lexdb.dbo.t`, or `[my table]`.

*table_alias*
: With `FROM`, the alias of the table to change, as `FROM` names it (`UPDATE e SET ... FROM dbo.emp AS e ...`).

`WITH (` *table_hint* `)`
: Read and ignored.

`SET` *column_name* `=` *expression*
: The column's new value. The expression sees the row's values before the change, so `SET a = b, b = a` swaps
  them. `DEFAULT` gives the column its default, or NULL.

*column_name* `+=` *expression* ...
: Compound assignment: `SET qty += 1` is `SET qty = qty + 1`.

`OUTPUT`
: Returns the rows as they were (`DELETED`) and as they are (`INSERTED`), or puts them into a table. See
  [OUTPUT](output.md).

`FROM` *table_source*
: Other tables to join to the target, for its `SET` and `WHERE`. When the target is named in `FROM`, `UPDATE` names
  its alias; when it is not, the other tables are joined to it by the `WHERE` clause. See
  [FROM, JOIN and APPLY](from.md).

`WHERE` *search_condition*
: The rows to change. Without `WHERE`, every row changes.

`OPTION (` *query_hint* `)`
: As in [SELECT](select.md).

`WITH ( batch_rows` *n* `)`
: lexdb's own, at the end of the statement: commits each *n* rows as a transaction of its own, so a large update
  holds the writes of *n* rows at a time, not all of them. It cannot run inside a transaction, and a batch that
  fails keeps the batches committed before it.

## Remarks

- Values are converted to the column's type on assignment: a string too long for `varchar(n)` is error 2628, a
  decimal is rounded to the column's scale.
- `NOT NULL` (515), `CHECK` and `FOREIGN KEY` (547), and unique keys (2627) are checked. A failed `UPDATE` changes
  no row; the batch goes on with the next statement unless `SET XACT_ABORT ON` or a `TRY ... CATCH` says
  otherwise. An `UPDATE` tests the `CHECK` constraints that read a column it sets (in an explicit transaction,
  with `OUTPUT ... INTO` and in `MERGE` too), which differs from testing every `CHECK` of the row only for a row that
  already breaks a constraint that is not trusted (see [ALTER TABLE](alter-table.md), example H).
- An `IDENTITY` column cannot be updated (error 544). A computed column cannot be set.
- `@@ROWCOUNT` is the number of rows changed. With `SET NOCOUNT ON` the client gets no `(n rows affected)`.
- A subquery in `SET` or `OUTPUT` sees the table as it was when the statement began, not the rows the statement has
  already changed (example D).
- With `FROM`, a target row that joins to several rows is changed once, with the values of one of them.
- Every read-write transaction is serializable: an `UPDATE` whose rows another transaction changed and committed
  meanwhile fails with error 1205, to be run again.
- On a replica, `UPDATE` of a table is error 3906; `#temp` tables and table variables can be changed there.

## Differences from SQL Server

- A common table expression or a view cannot be the target: a CTE gives error 208, a view error 50000 ("cannot
  update view ... (lexdb's views are read-only)"). Name the table, and read the CTE in `WHERE`.
- `UPDATE TOP (n) PERCENT` is error 102; SQL Server accepts it.
- A column set twice in one `SET` takes the last value; SQL Server refuses it (error 264).
- `WITH ( batch_rows n )` is lexdb's, not SQL Server's.
- `SET @variable = expression` and `SET @variable = column = expression`, which set a variable for each row, are
  error 102.
- `SET column.WRITE (...)` is error 102.
- Setting an identity column gives error 544, with lexdb's text; SQL Server gives 8102 ("Cannot update identity
  column").
- `WHERE CURRENT OF` is not supported: lexdb has no cursors. There are no triggers.
- Most error messages are SQL Server's; those with number 50000 carry lexdb's text.

## Examples

<!--setup: tsql
CREATE TABLE dbo.dept (id int PRIMARY KEY, name nvarchar(30) NOT NULL);
CREATE TABLE dbo.emp (id int IDENTITY PRIMARY KEY, name nvarchar(30) NOT NULL, dept_id int REFERENCES dbo.dept (id), salary decimal(10,2) CHECK (salary > 0), bonus int DEFAULT 0);
INSERT dbo.dept VALUES (1, N'Sales'), (2, N'Research');
INSERT dbo.emp (name, dept_id, salary, bonus) VALUES (N'Ann', 1, 5200, 10), (N'Bob', 1, 4100, 20), (N'Cid', 2, 6100, 30), (N'Dee', 2, 6100, 40);
-->

The examples use two tables:

```sql
CREATE TABLE dbo.dept (id int PRIMARY KEY, name nvarchar(30) NOT NULL);
CREATE TABLE dbo.emp (id int IDENTITY PRIMARY KEY, name nvarchar(30) NOT NULL, dept_id int REFERENCES dbo.dept (id),
                      salary decimal(10,2) CHECK (salary > 0), bonus int DEFAULT 0);
INSERT dbo.dept VALUES (1, N'Sales'), (2, N'Research');
INSERT dbo.emp (name, dept_id, salary, bonus) VALUES (N'Ann', 1, 5200, 10), (N'Bob', 1, 4100, 20),
  (N'Cid', 2, 6100, 30), (N'Dee', 2, 6100, 40);
```

### A. Change some rows

<!-- example: tsql -->
```sql
UPDATE dbo.emp SET salary = salary * 1.05 WHERE dept_id = 2;
SELECT name, salary FROM dbo.emp ORDER BY id;
```

```text
(2 rows affected)

name salary
---- -------
Ann  5200.00
Bob  4100.00
Cid  6405.00
Dee  6405.00

(4 rows affected)
```

### B. Several columns, DEFAULT and compound assignment

<!-- example: tsql -->
```sql
UPDATE dbo.emp SET bonus = DEFAULT, salary += 100 WHERE name = N'Bob';
UPDATE dbo.emp SET bonus *= 2 WHERE bonus >= 30;
SELECT name, salary, bonus FROM dbo.emp ORDER BY id;
SELECT @@ROWCOUNT AS rows_read;
```

```text
(1 row affected)

(2 rows affected)

name salary  bonus
---- ------- -----
Ann  5200.00 10
Bob  4200.00 0
Cid  6405.00 60
Dee  6405.00 80

(4 rows affected)

rows_read
---------
4

(1 row affected)
```

### C. Values from other tables: FROM and a join

<!-- example: tsql -->
```sql
UPDATE e SET e.bonus = e.bonus + 5
FROM dbo.emp AS e
JOIN dbo.dept AS d ON d.id = e.dept_id
WHERE d.name = N'Sales';
SELECT name, bonus FROM dbo.emp WHERE dept_id = 1 ORDER BY id;
```

```text
(2 rows affected)

name bonus
---- -----
Ann  15
Bob  5

(2 rows affected)
```

### D. FROM without the target, and a subquery

<!-- example: tsql -->
```sql
UPDATE dbo.emp SET bonus = 0 FROM dbo.dept AS d WHERE d.id = dbo.emp.dept_id AND d.name = N'Research';
UPDATE dbo.emp SET salary = (SELECT MAX(salary) FROM dbo.emp) WHERE name = N'Ann';
SELECT name, salary, bonus FROM dbo.emp ORDER BY id;
```

```text
(2 rows affected)

(1 row affected)

name salary  bonus
---- ------- -----
Ann  6405.00 15
Bob  4200.00 5
Cid  6405.00 0
Dee  6405.00 0

(4 rows affected)
```

A subquery reads the table as the statement found it. Here each employee takes twice the pay of the manager, and the
managers change in the same statement:

<!-- example: tsql -->
```sql
CREATE TABLE dbo.staff (id int PRIMARY KEY, boss int, pay int);
INSERT dbo.staff VALUES (1, NULL, 100), (2, 1, 200), (3, 2, 300), (4, 3, 400);
UPDATE s SET pay = (SELECT b.pay * 2 FROM dbo.staff AS b WHERE b.id = s.boss)
OUTPUT inserted.id, inserted.pay
FROM dbo.staff AS s WHERE s.boss IS NOT NULL;
SELECT id, pay FROM dbo.staff ORDER BY id;
```

```text
(4 rows affected)

id pay
-- ---
2  200
3  400
4  600

(3 rows affected)

id pay
-- ---
1  100
2  200
3  400
4  600

(4 rows affected)
```

### E. TOP, and OUTPUT

<!-- example: tsql -->
```sql
UPDATE TOP (1) dbo.emp SET bonus = 99 WHERE dept_id = 2;
UPDATE dbo.emp SET salary = salary - 50
OUTPUT INSERTED.name, DELETED.salary AS before, INSERTED.salary AS after
WHERE name = N'Bob';
```

```text
(1 row affected)

name before  after
---- ------- -------
Bob  4200.00 4150.00

(1 row affected)
```

### F. A table variable

<!-- example: tsql -->
```sql
DECLARE @raise TABLE (dept_id int, pct decimal(4,2));
INSERT @raise VALUES (1, 0.10), (2, 0.00);
UPDATE @raise SET pct = 0.05 WHERE dept_id = 2;
UPDATE e SET salary = salary * (1 + r.pct) FROM dbo.emp AS e JOIN @raise AS r ON r.dept_id = e.dept_id;
SELECT name, salary FROM dbo.emp ORDER BY id;
```

```text
(2 rows affected)

(1 row affected)

(4 rows affected)

name salary
---- -------
Ann  7045.50
Bob  4565.00
Cid  6725.25
Dee  6725.25

(4 rows affected)
```

### G. Errors

Each failed statement changes nothing, and the batch goes on.

<!-- example: tsql -->
```sql
UPDATE dbo.emp SET salary = -1 WHERE id = 1;
UPDATE dbo.emp SET dept_id = 9 WHERE id = 1;
UPDATE dbo.emp SET name = NULL WHERE id = 1;
UPDATE dbo.emp SET id = 10 WHERE id = 1;
UPDATE dbo.emp SET name = N'a name that is far too long for thirty characters' WHERE id = 1;
PRINT 'the batch went on';
```

```text
Msg 547, Level 16, State 1, Line 1
The UPDATE statement conflicted with the CHECK constraint "emp_salary_check". The conflict occurred in database "lexdb", table "dbo.emp", column 'salary'.
Msg 547, Level 16, State 1, Line 2
The UPDATE statement conflicted with the FOREIGN KEY constraint "emp_dept_id_fkey". The conflict occurred in database "lexdb", table "dbo.dept", column 'id'.
Msg 515, Level 16, State 1, Line 3
Cannot insert the value NULL into column 'name', table 'lexdb.dbo.emp'; column does not allow nulls. UPDATE fails.
Msg 544, Level 16, State 1, Line 4
column "id" can only be updated to DEFAULT
Msg 2628, Level 16, State 1, Line 5
value too long for type character varying(30)
the batch went on
```

### H. lexdb's batch_rows

<!-- example: tsql -->
```sql
UPDATE dbo.emp SET bonus = bonus + 1 WITH (batch_rows 2);
BEGIN TRANSACTION;
UPDATE dbo.emp SET bonus = bonus + 1 WITH (batch_rows 2);
ROLLBACK;
```

```text
(4 rows affected)

Msg 50000, Level 16, State 1, Line 3
lexdb: UPDATE with batch_rows cannot run inside a transaction block
```

### I. What lexdb does not take

<!-- example: tsql -->
```sql
WITH s AS (SELECT * FROM dbo.emp WHERE dept_id = 1) UPDATE s SET bonus = 1;
GO
DECLARE @total decimal(12,2) = 0;
UPDATE dbo.emp SET @total = @total + salary;
GO
```

```text
Msg 208, Level 16, State 1, Line 1
Invalid object name 's'.
Msg 102, Level 15, State 1, Line 2
Incorrect syntax near '@total'.
```

## See also

[INSERT](insert.md) · [DELETE](delete.md) · [MERGE](merge.md) · [OUTPUT clause](output.md) · [TOP](top.md) ·
[FROM, JOIN and APPLY](from.md)
