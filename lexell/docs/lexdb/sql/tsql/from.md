# FROM clause plus JOIN and APPLY (Transact-SQL)

Names the tables, views, derived tables and functions a `SELECT`, `UPDATE` or `DELETE` reads, and how they are
joined.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
[ FROM { table_source } [ ,...n ] ]

table_source ::=
{
    table_or_view_name [ [ AS ] table_alias ] [ WITH ( table_hint [ ,...n ] ) ]
  | @table_variable [ [ AS ] table_alias ]
  | #temp_table [ [ AS ] table_alias ]
  | derived_table [ AS ] table_alias [ ( column_alias [ ,...n ] ) ]
  | ( VALUES ( expression [ ,...n ] ) [ ,...n ] ) [ AS ] table_alias [ ( column_alias [ ,...n ] ) ]
  | table_valued_function ( [ argument [ ,...n ] ] ) [ [ AS ] table_alias ]
  | GRAPH_TABLE ( ... ) [ [ AS ] table_alias [ ( column_alias [ ,...n ] ) ] ]
  | table_source MATCH_RECOGNIZE ( ... ) [ [ AS ] table_alias [ ( column_alias [ ,...n ] ) ] ]
  | joined_table
}

joined_table ::=
{
    table_source join_type table_source ON search_condition
  | table_source CROSS JOIN table_source
  | table_source { CROSS | OUTER } APPLY table_source
  | ( joined_table )
}

join_type ::=
    [ INNER | { LEFT | RIGHT | FULL } [ OUTER ] ] JOIN
```

## Arguments

*table_or_view_name*
: A table or view, with its schema and database if wanted: `emp`, `dbo.emp`, `lexdb.dbo.emp`. A catalog view
  (`sys.tables`, `INFORMATION_SCHEMA.COLUMNS`) may be read the same way.

*table_alias*
: A name for the source in the rest of the statement. Once a table has an alias, use the alias.

`WITH (` *table_hint* `)`
: Any list of table hints (`NOLOCK`, `HOLDLOCK`, `UPDLOCK`, `ROWLOCK`, `TABLOCK`, `INDEX (...)` ...) is read and
  ignored. The old form without `WITH` is taken for `(NOLOCK)`, `(READUNCOMMITTED)`, `(HOLDLOCK)`, `(UPDLOCK)`,
  `(ROWLOCK)` and `(TABLOCK)`.

*@table_variable*, *#temp_table*
: A table variable of the batch, or a temporary table of the session.

*derived_table*
: A query in parentheses. It needs an alias.

`VALUES`
: Rows written in the statement. See [Table value constructor](values.md).

*table_valued_function*
: `GENERATE_SERIES (start, stop [, step])`, whose column is `value`, or an inline or multi-statement table-valued
  function of the user's.

`GRAPH_TABLE (...)`
: Matches a pattern over a property graph (SQL/PGQ). See [GRAPH_TABLE](graph-table.md).

`MATCH_RECOGNIZE (...)`
: Matches regular-expression patterns over ordered sequences of rows (SQL:2016 R010). See [MATCH_RECOGNIZE](match-recognize.md).

`INNER JOIN`
: The pairs of rows for which the `ON` condition is true. `JOIN` alone is `INNER JOIN`.

`LEFT [OUTER] JOIN`, `RIGHT [OUTER] JOIN`, `FULL [OUTER] JOIN`
: The inner join's rows, and also each row of the left (right, either) source that matched none, with NULLs for
  the other source's columns.

`CROSS JOIN`
: Every pair of rows. A comma between sources is the same.

`CROSS APPLY`
: Runs the right source once for each row of the left one; the right source may use the left one's columns. Returns
  the pairs, as an inner join does.

`OUTER APPLY`
: As `CROSS APPLY`, but also keeps the left rows for which the right source returned no row, with NULLs.

## Remarks

- A condition on the outer side of an outer join belongs in `ON`; in `WHERE` it removes the NULL rows the join
  added, and the join acts as an inner one.
- Joins bind from left to right; parentheses change that.
- `APPLY` is the usual way to call a table-valued function for each row, or to take the top rows of each group
  (example D).

## Differences from SQL Server

- `PIVOT` and `UNPIVOT` are not supported (error 156, `Incorrect syntax near the keyword 'PIVOT'`).
- Join hints (`INNER LOOP JOIN`, `LEFT HASH JOIN`, `MERGE JOIN`, `REMOTE`) are error 102. A join hint in
  `OPTION (HASH JOIN)` is read and ignored.
- `TABLESAMPLE` is error 156. `OPENROWSET` and `STRING_SPLIT` are not available. (For `OPENJSON` and `JSON_TABLE` see
  [JSON, OPENJSON and FOR JSON](functions-json.md).)
- `VALUES` in `FROM` without column aliases names its columns `column1`, `column2` ...; SQL Server needs the
  aliases (error 8155).
- PostgreSQL's `NATURAL JOIN`, `JOIN ... USING (...)` and `LATERAL` are taken; SQL Server refuses them.

## Examples

<!--setup: tsql
CREATE TABLE dbo.dept (id int PRIMARY KEY, name nvarchar(30) NOT NULL);
CREATE TABLE dbo.emp (id int IDENTITY PRIMARY KEY, name nvarchar(30) NOT NULL, dept_id int REFERENCES dbo.dept (id), salary decimal(10,2));
INSERT dbo.dept VALUES (1, N'Sales'), (2, N'Research'), (3, N'Legal');
INSERT dbo.emp (name, dept_id, salary) VALUES (N'Ann', 1, 5200), (N'Bob', 1, 4100), (N'Cid', 2, 6100), (N'Dee', 2, 6100), (N'Eve', NULL, 3000);
-->

The examples use two tables:

```sql
CREATE TABLE dbo.dept (id int PRIMARY KEY, name nvarchar(30) NOT NULL);
CREATE TABLE dbo.emp (id int IDENTITY PRIMARY KEY, name nvarchar(30) NOT NULL,
                      dept_id int REFERENCES dbo.dept (id), salary decimal(10,2));
INSERT dbo.dept VALUES (1, N'Sales'), (2, N'Research'), (3, N'Legal');
INSERT dbo.emp (name, dept_id, salary) VALUES (N'Ann', 1, 5200), (N'Bob', 1, 4100), (N'Cid', 2, 6100),
  (N'Dee', 2, 6100), (N'Eve', NULL, 3000);
```

### A. Inner and outer joins

<!-- example: tsql -->
```sql
SELECT e.name, d.name AS dept FROM dbo.emp AS e INNER JOIN dbo.dept AS d ON d.id = e.dept_id ORDER BY e.id;
SELECT e.name, d.name AS dept FROM dbo.emp AS e LEFT OUTER JOIN dbo.dept AS d ON d.id = e.dept_id ORDER BY e.id;
```

```text
name dept
---- --------
Ann  Sales
Bob  Sales
Cid  Research
Dee  Research

(4 rows affected)

name dept
---- --------
Ann  Sales
Bob  Sales
Cid  Research
Dee  Research
Eve  NULL

(5 rows affected)
```

### B. FULL JOIN

<!-- example: tsql -->
```sql
SELECT e.name, d.name AS dept
FROM dbo.emp AS e FULL JOIN dbo.dept AS d ON d.id = e.dept_id
ORDER BY d.id, e.id;
```

```text
name dept
---- --------
Eve  NULL
Ann  Sales
Bob  Sales
Cid  Research
Dee  Research
NULL Legal

(6 rows affected)
```

### C. Rows with no match

<!-- example: tsql -->
```sql
SELECT d.name FROM dbo.dept AS d LEFT JOIN dbo.emp AS e ON e.dept_id = d.id WHERE e.id IS NULL;
```

```text
name
-----
Legal

(1 row affected)
```

### D. CROSS APPLY and OUTER APPLY: the best paid of each department

<!-- example: tsql -->
```sql
SELECT d.name AS dept, t.name, t.salary
FROM dbo.dept AS d
CROSS APPLY (SELECT TOP (1) name, salary FROM dbo.emp AS e WHERE e.dept_id = d.id ORDER BY salary DESC, id) AS t
ORDER BY d.id;
SELECT d.name AS dept, t.name
FROM dbo.dept AS d
OUTER APPLY (SELECT TOP (1) name FROM dbo.emp AS e WHERE e.dept_id = d.id ORDER BY id) AS t
ORDER BY d.id;
```

```text
dept     name salary
-------- ---- -------
Sales    Ann  5200.00
Research Cid  6100.00

(2 rows affected)

dept     name
-------- ----
Sales    Ann
Research Cid
Legal    NULL

(3 rows affected)
```

### E. APPLY with VALUES: columns into rows

<!-- example: tsql -->
```sql
SELECT e.name, v.kind, v.amount
FROM dbo.emp AS e
CROSS APPLY (VALUES (N'month', e.salary), (N'year', e.salary * 12)) AS v (kind, amount)
WHERE e.id = 1;
```

```text
name kind  amount
---- ----- --------
Ann  month 5200.00
Ann  year  62400.00

(2 rows affected)
```

### F. A derived table, a table-valued function and a hint

<!-- example: tsql -->
```sql
SELECT s.dept_id, s.n, g.value AS slot
FROM (SELECT dept_id, COUNT(*) AS n FROM dbo.emp WITH (NOLOCK) GROUP BY dept_id) AS s
CROSS APPLY GENERATE_SERIES(1, s.n) AS g
WHERE s.dept_id IS NOT NULL
ORDER BY s.dept_id, slot;
```

```text
dept_id n slot
------- - ----
1       2 1
1       2 2
2       2 1
2       2 2

(4 rows affected)
```

### G. Old-style joins

A comma is a cross join, and the condition goes in `WHERE`.

<!-- example: tsql -->
```sql
SELECT e.name, d.name AS dept FROM dbo.emp e, dbo.dept d WHERE d.id = e.dept_id AND d.id = 2 ORDER BY e.name;
```

```text
name dept
---- --------
Cid  Research
Dee  Research

(2 rows affected)
```

### H. What lexdb does not take

<!-- example: tsql -->
```sql
SELECT e.name FROM dbo.emp AS e INNER LOOP JOIN dbo.dept AS d ON d.id = e.dept_id;
GO
SELECT * FROM (SELECT 1 AS a, 2 AS b) AS s UNPIVOT (v FOR k IN (a, b)) AS u;
GO
```

```text
Msg 102, Level 15, State 1, Line 1
Incorrect syntax near 'LOOP'.
Msg 156, Level 15, State 1, Line 1
Incorrect syntax near the keyword 'UNPIVOT'.
```

## See also

[SELECT](select.md) · [GRAPH_TABLE](graph-table.md) · [Table value constructor](values.md) · [UPDATE](update.md) · [DELETE](delete.md)
