# MERGE (Transact-SQL)

Inserts, updates or deletes rows of a target table by how they match the rows of a source, in one statement.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
[ WITH common_table_expression [ ,...n ] ]
MERGE
    [ TOP ( expression ) ]
    [ INTO ] target_table [ WITH ( table_hint [ ,...n ] ) ] [ [ AS ] table_alias ]
    USING table_source [ [ AS ] table_alias ]
    ON merge_search_condition
    [ WHEN MATCHED [ AND clause_search_condition ]
        THEN { UPDATE SET set_clause | DELETE } ] [ ...n ]
    [ WHEN NOT MATCHED [ BY TARGET ] [ AND clause_search_condition ]
        THEN INSERT [ ( column_list ) ] { VALUES ( values_list ) | DEFAULT VALUES } ]
    [ WHEN NOT MATCHED BY SOURCE [ AND clause_search_condition ]
        THEN { UPDATE SET set_clause | DELETE } ] [ ...n ]
    [ OUTPUT output_list [ INTO { @table_variable | table_name } [ ( column_list ) ] ] ]
    [ OPTION ( query_hint [ ,...n ] ) ]
;
```

## Arguments

`TOP (` *expression* `)`
: Changes at most this many rows. See [TOP](top.md).

*target_table*
: The table whose rows change: a table, a `#temp` table or a table variable.

`USING` *table_source*
: The source rows: a table, a view, a derived table, `VALUES` with column aliases, or a common table expression.

`ON` *merge_search_condition*
: How a source row matches a target row. Keep it to the columns that match them; put other conditions in the
  `WHEN` clauses.

`WHEN MATCHED [AND ...] THEN UPDATE | DELETE`
: For a target row with a matching source row. There may be two such clauses; the first must then have an `AND`
  condition.

`WHEN NOT MATCHED [BY TARGET] THEN INSERT`
: For a source row with no matching target row. The `VALUES` may use the source's columns.

`WHEN NOT MATCHED BY SOURCE THEN UPDATE | DELETE`
: For a target row that no source row matches.

`OUTPUT`
: Returns a row for each row changed, with `$action` (`INSERT`, `UPDATE` or `DELETE`), `INSERTED`, `DELETED`, and
  the source's columns. See [OUTPUT](output.md).

## Remarks

- `MERGE` must end with a semicolon (error 10713).
- A target row matched by more than one source row is error 8672, and nothing changes.
- A `WHEN MATCHED` clause with a condition after one without is error 5324.
- `@@ROWCOUNT` is the number of rows inserted, updated and deleted together.
- `NOT NULL`, `CHECK`, foreign key and unique constraints are checked as for `INSERT`, `UPDATE` and `DELETE`.

## Differences from SQL Server

- The target cannot be a view or a common table expression: a view gives error 50000 ("cannot merge into view ...
  (lexdb's views are read-only)"), a common table expression error 208.
- `MERGE TOP (n) PERCENT` is error 50000 ("lexdb: MERGE TOP ... PERCENT is not supported").
- The text of many error messages is lexdb's, with SQL Server's number and severity; 8672, 5324 and 10713 have SQL
  Server's text.

## Examples

<!--setup: tsql
CREATE TABLE dbo.stock (id int PRIMARY KEY, name nvarchar(20), qty int);
CREATE TABLE dbo.delivery (id int PRIMARY KEY, name nvarchar(20), qty int);
INSERT dbo.stock VALUES (1, N'bolt', 10), (2, N'nut', 20), (3, N'gear', 30);
INSERT dbo.delivery VALUES (2, N'nut', 25), (3, N'gear', 0), (4, N'cog', 40);
-->

The examples use two tables:

```sql
CREATE TABLE dbo.stock (id int PRIMARY KEY, name nvarchar(20), qty int);
CREATE TABLE dbo.delivery (id int PRIMARY KEY, name nvarchar(20), qty int);
INSERT dbo.stock VALUES (1, N'bolt', 10), (2, N'nut', 20), (3, N'gear', 30);
INSERT dbo.delivery VALUES (2, N'nut', 25), (3, N'gear', 0), (4, N'cog', 40);
```

### A. Insert, update and delete, with OUTPUT $action

<!-- example: tsql -->
```sql
MERGE dbo.stock AS t
USING dbo.delivery AS s ON t.id = s.id
WHEN MATCHED AND s.qty = 0 THEN DELETE
WHEN MATCHED THEN UPDATE SET t.qty = t.qty + s.qty
WHEN NOT MATCHED BY TARGET THEN INSERT (id, name, qty) VALUES (s.id, s.name, s.qty)
OUTPUT $action, DELETED.qty AS old_qty, INSERTED.id, INSERTED.qty AS new_qty;
SELECT * FROM dbo.stock ORDER BY id;
```

```text
$action old_qty id   new_qty
------- ------- ---- -------
UPDATE  20      2    45
DELETE  30      NULL NULL
INSERT  NULL    4    40

(3 rows affected)

id name qty
-- ---- ---
1  bolt 10
2  nut  45
4  cog  40

(3 rows affected)
```

### B. WHEN NOT MATCHED BY SOURCE

<!-- example: tsql -->
```sql
MERGE INTO dbo.stock AS t
USING (VALUES (2, N'nut'), (4, N'cog')) AS s (id, name) ON t.id = s.id
WHEN NOT MATCHED BY SOURCE THEN UPDATE SET qty = 0;
SELECT * FROM dbo.stock ORDER BY id;
```

```text
(1 row affected)

id name qty
-- ---- ---
1  bolt 0
2  nut  45
4  cog  40

(3 rows affected)
```

### C. Upsert one row from variables

<!-- example: tsql -->
```sql
DECLARE @id int = 5, @name nvarchar(20) = N'axle', @qty int = 7;
MERGE dbo.stock AS t
USING (SELECT @id AS id, @name AS name, @qty AS qty) AS s ON t.id = s.id
WHEN MATCHED THEN UPDATE SET qty = s.qty
WHEN NOT MATCHED THEN INSERT VALUES (s.id, s.name, s.qty);
SELECT @@ROWCOUNT AS merged;
SELECT * FROM dbo.stock WHERE id = 5;
```

```text
(1 row affected)

merged
------
1

(1 row affected)

id name qty
-- ---- ---
5  axle 7

(1 row affected)
```

### D. OUTPUT INTO a table variable, with the source's columns

<!-- example: tsql -->
```sql
DECLARE @log TABLE (act nvarchar(10), src_id int, qty int);
MERGE dbo.stock AS t
USING dbo.delivery AS s ON t.id = s.id
WHEN MATCHED THEN UPDATE SET qty = s.qty
OUTPUT $action, s.id, INSERTED.qty INTO @log;
SELECT * FROM @log ORDER BY src_id;
```

```text
(2 rows affected)

act    src_id qty
------ ------ ---
UPDATE 2      25
UPDATE 4      40

(2 rows affected)
```

### E. Errors

<!-- example: tsql -->
```sql
CREATE TABLE dbo.twice (id int, qty int);
INSERT dbo.twice VALUES (1, 1), (1, 2);
MERGE dbo.stock AS t USING dbo.twice AS s ON t.id = s.id WHEN MATCHED THEN UPDATE SET qty = s.qty;
GO
MERGE dbo.stock AS t USING dbo.delivery AS s ON t.id = s.id WHEN MATCHED THEN UPDATE SET qty = 1
GO
MERGE dbo.stock AS t USING dbo.delivery AS s ON t.id = s.id
WHEN MATCHED THEN UPDATE SET qty = 1 WHEN MATCHED AND s.qty > 5 THEN DELETE;
GO
```

```text
(2 rows affected)

Msg 8672, Level 16, State 1, Line 3
The MERGE statement attempted to UPDATE or DELETE the same row more than once. This happens when a target row matches more than one source row. A MERGE statement cannot UPDATE/DELETE the same row of the target table multiple times. Refine the ON clause to ensure a target row matches at most one source row, or use the GROUP BY clause to group the source rows.
Msg 10713, Level 15, State 1, Line 2
A MERGE statement must be terminated by a semi-colon (;).
Msg 5324, Level 16, State 1, Line 2
In a MERGE statement, a 'WHEN MATCHED' clause with a search condition cannot appear after a 'WHEN MATCHED' clause with no search condition.
```

## See also

[INSERT](insert.md) · [UPDATE](update.md) · [DELETE](delete.md) · [OUTPUT clause](output.md) ·
[Table value constructor](values.md)
