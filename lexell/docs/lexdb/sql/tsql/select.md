# SELECT (Transact-SQL)

Reads rows from tables, views, derived tables and table-valued functions, and returns them as a result set.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
[ WITH common_table_expression [ ,...n ] ]
query_expression
[ ORDER BY order_by_expression [ ,...n ] [ OFFSET ... [ FETCH ... ] ] ]
[ OPTION ( query_hint [ ,...n ] ) ]
[ ; ]

query_expression ::=
    { query_specification | ( query_expression ) }
    [ { UNION [ ALL ] | EXCEPT | INTERSECT } { query_specification | ( query_expression ) } ] [ ...n ]

query_specification ::=
SELECT [ ALL | DISTINCT ]
    [ TOP ( expression ) [ PERCENT ] [ WITH TIES ] ]
    select_list
    [ INTO new_table ]
    [ FROM table_source [ ,...n ] ]
    [ WHERE search_condition ]
    [ GROUP BY group_by_spec ]
    [ HAVING search_condition ]
    [ WINDOW window_name AS ( window_spec ) [ ,...n ] ]

select_list ::=
    { *
    | { table_name | view_name | table_alias }.*
    | { column_name | expression } [ [ AS ] column_alias ]
    | column_alias = expression
    } [ ,...n ]
```

## Arguments

*common_table_expression*
: A named query the statement can read. See [WITH](with.md).

`ALL`
: Keeps duplicate rows. This is the default.

`DISTINCT`
: Keeps one row of each set of equal rows. NULLs are equal here.

`TOP`
: Returns only the first rows. See [TOP](top.md).

*select_list*
: The columns of the result. `*` is every column of the `FROM` sources; `t.*` every column of `t`. A column takes
  its name from `AS` *column_alias*, from *column_alias* `=`, or from the column it shows. An expression with no
  name has none: the client shows `(No column name)`. An alias may be a bracketed name (`[Employee Name]`), a
  quoted name or a string literal.

`INTO` *new_table*
: Makes a new table from the result. See [SELECT INTO](select-into.md).

`FROM` *table_source*
: Where the rows come from: tables, views, derived tables, `VALUES`, table variables, `#temp` tables, table-valued
  functions, and their joins. See [FROM, JOIN and APPLY](from.md). Without `FROM`, the statement returns one row.

`WHERE` *search_condition*
: Keeps the rows for which the condition is true.

`GROUP BY`, `HAVING`
: Groups the rows and filters the groups. See [GROUP BY](select-group-by.md).

`WINDOW`
: Names window specifications that `OVER` clauses use (SQL Server 2022). See [OVER](over.md).

`UNION`, `EXCEPT`, `INTERSECT`
: Combine the rows of two queries. See [Set operators](set-operators.md).

`ORDER BY`, `OFFSET`, `FETCH`
: Sort the result and return a page of it. See [ORDER BY](order-by.md).

`OPTION (` *query_hint* `)`
: Query hints. `MAXRECURSION n` limits a recursive common table expression (see [WITH](with.md)). `RECOMPILE`,
  `MAXDOP n`, `HASH JOIN`, `OPTIMIZE FOR ...`, `USE HINT (...)` and SQL Server's other hints are read and ignored.
  A word that is not a SQL Server hint is error 102.

## Remarks

- The clauses are worked in this order: `FROM`, `WHERE`, `GROUP BY`, `HAVING`, window functions, the select list,
  `DISTINCT`, `ORDER BY`, `OFFSET` and `TOP`. So `WHERE` cannot use a column alias, and `ORDER BY` can.
- A subquery may stand for a value (one row and one column; no row gives NULL, more than one is error 512), and
  may be used with `IN`, `NOT IN`, `EXISTS`, and with `ANY`, `SOME` and `ALL` after a comparison. A subquery may
  refer to the columns of the query around it.
- Names are resolved without regard to case. A table name may carry its schema (`dbo.emp`) and the database
  (`lexdb.dbo.emp`); the default schema is `dbo`. Names in brackets (`[order]`) or double quotes may be keywords or
  hold spaces.
- Strings compare as their column's collation says. The default collation is case-insensitive, so `'ANN'` equals
  `'Ann'`. `COLLATE` changes it for one comparison or sort.
- Table hints in `FROM` (`WITH (NOLOCK)`, `(NOLOCK)`, `WITH (UPDLOCK, ROWLOCK)`, `WITH (INDEX(...))`) are read and
  ignored. Every read-write transaction is serializable, whatever the isolation level says.
- A syntax error anywhere in a batch stops the whole batch before it runs, as in SQL Server. An error 207 or 208
  (unknown column or table) ends the batch at that statement. Other errors end only their statement.
- `SET ROWCOUNT n` makes a `SELECT` return at most *n* rows.

## Differences from SQL Server

- `PIVOT` and `UNPIVOT`, `FOR XML`, `FOR JSON`, `FOR BROWSE`, `TABLESAMPLE`, `$IDENTITY` and `$ROWGUID` are not
  supported: each is error 102.
- Some errors carry 50000 and lexdb's text where SQL Server has a number of its own: an ambiguous column (SQL
  Server 209), a column that is neither grouped nor in an aggregate (8120), a window function in `WHERE` (4108),
  `ORDER BY` with `DISTINCT` on a column not in the list (145).
- A derived table, a view or a common table expression may have an `ORDER BY` without `TOP` or `OFFSET` (SQL Server
  1033). The order is not kept.
- PostgreSQL's forms are taken too: `NATURAL JOIN`, `JOIN ... USING (...)`, `LATERAL`, `VALUES` on its own as a
  statement, and `WITH RECURSIVE`. SQL Server refuses them.
- `XMLNAMESPACES` in `WITH` is not supported.

## Examples

<!--setup: tsql
CREATE TABLE dbo.dept (id int PRIMARY KEY, name nvarchar(30) NOT NULL);
CREATE TABLE dbo.emp (id int IDENTITY PRIMARY KEY, name nvarchar(30) NOT NULL, dept_id int REFERENCES dbo.dept (id), salary decimal(10,2), hired date);
INSERT dbo.dept VALUES (1, N'Sales'), (2, N'Research'), (3, N'Legal');
INSERT dbo.emp (name, dept_id, salary, hired) VALUES (N'Ann', 1, 5200, '2019-03-01'), (N'Bob', 1, 4100, '2021-07-15'), (N'Cid', 2, 6100, '2018-01-10'), (N'Dee', 2, 6100, '2022-05-02'), (N'Eve', NULL, 3000, '2024-09-30');
-->

The examples use two tables:

```sql
CREATE TABLE dbo.dept (id int PRIMARY KEY, name nvarchar(30) NOT NULL);
CREATE TABLE dbo.emp (id int IDENTITY PRIMARY KEY, name nvarchar(30) NOT NULL,
                      dept_id int REFERENCES dbo.dept (id), salary decimal(10,2), hired date);
INSERT dbo.dept VALUES (1, N'Sales'), (2, N'Research'), (3, N'Legal');
INSERT dbo.emp (name, dept_id, salary, hired) VALUES (N'Ann', 1, 5200, '2019-03-01'), (N'Bob', 1, 4100, '2021-07-15'),
  (N'Cid', 2, 6100, '2018-01-10'), (N'Dee', 2, 6100, '2022-05-02'), (N'Eve', NULL, 3000, '2024-09-30');
```

### A. Columns, aliases and a condition

<!-- example: tsql -->
```sql
SELECT name AS [Employee Name], salary * 12 AS yearly, raised = salary + 100
FROM dbo.emp
WHERE salary > 4000 AND hired < '2020-01-01'
ORDER BY name;
```

```text
Employee Name yearly   raised
------------- -------- -------
Ann           62400.00 5300.00
Cid           73200.00 6200.00

(2 rows affected)
```

### B. Every column, and DISTINCT

<!-- example: tsql -->
```sql
SELECT * FROM dbo.dept ORDER BY id;
SELECT DISTINCT dept_id FROM dbo.emp ORDER BY dept_id;
```

```text
id name
-- --------
1  Sales
2  Research
3  Legal

(3 rows affected)

dept_id
-------
NULL
1
2

(3 rows affected)
```

### C. A SELECT without FROM

<!-- example: tsql -->
```sql
SELECT 1 + 1 AS two, N'text', UPPER(N'abc'), NULL;
```

```text
two (No column name) (No column name) (No column name)
--- ---------------- ---------------- ----------------
2   text             ABC              NULL

(1 row affected)
```

### D. A join

<!-- example: tsql -->
```sql
SELECT e.name, d.name AS dept
FROM dbo.emp AS e
JOIN dbo.dept AS d ON d.id = e.dept_id
ORDER BY e.id;
```

```text
name dept
---- --------
Ann  Sales
Bob  Sales
Cid  Research
Dee  Research

(4 rows affected)
```

### E. Subqueries

<!-- example: tsql -->
```sql
SELECT name, salary, (SELECT MAX(salary) FROM dbo.emp) AS top_salary
FROM dbo.emp
WHERE salary = (SELECT MIN(salary) FROM dbo.emp);
SELECT name FROM dbo.emp AS e
WHERE EXISTS (SELECT 1 FROM dbo.dept AS d WHERE d.id = e.dept_id AND d.name LIKE N'S%');
SELECT name FROM dbo.emp WHERE salary > ALL (SELECT salary FROM dbo.emp WHERE dept_id = 1);
```

```text
name salary  top_salary
---- ------- ----------
Eve  3000.00 6100.00

(1 row affected)

name
----
Ann
Bob

(2 rows affected)

name
----
Cid
Dee

(2 rows affected)
```

### F. CASE, IIF and LIKE patterns

<!-- example: tsql -->
```sql
SELECT name,
       CASE WHEN salary >= 6000 THEN 'high' WHEN salary >= 4000 THEN 'middle' ELSE 'low' END AS band,
       IIF(dept_id IS NULL, 'none', 'some') AS has_dept
FROM dbo.emp
WHERE name LIKE '[A-D]%' AND name NOT LIKE '_o%'
ORDER BY name;
```

```text
name band   has_dept
---- ------ --------
Ann  middle some
Cid  high   some
Dee  high   some

(3 rows affected)
```

### G. Case-insensitive comparison, and COLLATE

<!-- example: tsql -->
```sql
SELECT name FROM dbo.emp WHERE name = 'ANN';
SELECT name FROM dbo.emp WHERE name = 'ANN' COLLATE Latin1_General_CS_AS;
```

```text
name
----
Ann

(1 row affected)

name
----

(0 rows affected)
```

### H. Table hints and query hints

Both are read and ignored.

<!-- example: tsql -->
```sql
SELECT name FROM dbo.emp WITH (NOLOCK) WHERE id = 1;
SELECT name FROM lexdb.dbo.emp (NOLOCK) WHERE id = 2 OPTION (RECOMPILE, MAXDOP 1);
```

```text
name
----
Ann

(1 row affected)

name
----
Bob

(1 row affected)
```

### I. Errors

<!-- example: tsql -->
```sql
SELECT name FROM dbo.emp WHERE salary = (SELECT salary FROM dbo.emp);
GO
SELECT name FROM dbo.emp e, dbo.dept d WHERE d.id = e.dept_id;
GO
SELECT nme FROM dbo.emp;
PRINT 'not reached';
GO
SELECT * FROM dbo.employee;
GO
```

```text
Msg 512, Level 16, State 1, Line 1
Subquery returned more than 1 value. This is not permitted when the subquery follows =, !=, <, <= , >, >= or when the subquery is used as an expression.
Msg 50000, Level 16, State 1, Line 1
column reference "name" is ambiguous
Msg 207, Level 16, State 1, Line 1
Invalid column name 'nme'.
Msg 208, Level 16, State 1, Line 1
Invalid object name 'employee'.
```

### J. What lexdb does not take

<!-- example: tsql -->
```sql
SELECT * FROM (SELECT dept_id, salary FROM dbo.emp) AS s
PIVOT (SUM(salary) FOR dept_id IN ([1], [2])) AS p;
GO
SELECT TOP 1 name FROM dbo.emp FOR JSON PATH;
GO
```

```text
Msg 102, Level 15, State 1, Line 2
Incorrect syntax near 'pivot'.
Msg 102, Level 15, State 1, Line 1
Incorrect syntax near 'JSON'.
```

## See also

[TOP](top.md) · [FROM, JOIN and APPLY](from.md) · [GROUP BY](select-group-by.md) · [OVER](over.md) ·
[ORDER BY](order-by.md) · [SELECT INTO](select-into.md) · [Set operators](set-operators.md) · [WITH](with.md) ·
[Table value constructor](values.md)
