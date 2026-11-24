# OUTPUT clause (Transact-SQL)

Returns the rows an `INSERT`, `UPDATE`, `DELETE` or `MERGE` changed, as they were and as they are, either to the
client as a result set or into a table.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
OUTPUT dml_select_list [ INTO { @table_variable | table_name | #temp_table } [ ( column_list ) ] ]

dml_select_list ::=
{ column_name | scalar_expression } [ [ AS ] column_alias ] [ ,...n ]

column_name ::=
{ DELETED | INSERTED | from_table_name } . { * | column_name }
| $action
```

## Arguments

`INSERTED.`*column*, `INSERTED.*`
: The row as the statement left it: the new row of an `INSERT`, the row after an `UPDATE`. Identity values,
  defaults and computed columns are filled in.

`DELETED.`*column*, `DELETED.*`
: The row as it was before an `UPDATE` or a `DELETE`.

*from_table_name*`.`*column*
: A column of another table the statement reads: the source of a `MERGE`, or a table of an `UPDATE`'s or a
  `DELETE`'s `FROM`.

`$action`
: In `MERGE` only: `INSERT`, `UPDATE` or `DELETE`.

*scalar_expression*
: Any expression of these columns, constants and functions (`INSERTED.qty - DELETED.qty`).

`INTO` *target* [ `(` *column_list* `)` ]
: Inserts the rows into a table variable, a `#temp` table or a table instead of returning them. The target must
  exist (error 208, or 1087 for an undeclared table variable). Without *column_list*, the values go to the target's
  columns in order.

## Remarks

- With `INTO`, the statement returns no result set; its `(n rows affected)` counts the rows it changed. The statement
  and the insert of its output are one: if the insert fails, the statement is undone too.
- In an `INSERT`, the rows are those of the `VALUES`, the query or the `EXEC`; `DELETED` belongs to `UPDATE`,
  `DELETE` and `MERGE`.
- `OUTPUT` is the way to get the identity values of many inserted rows, where `SCOPE_IDENTITY()` gives only the last.
- The order of the output rows is not defined.
- `OUTPUT` takes no subquery, in any of the four statements: it is error 10705, as in SQL Server. Read the other
  table in a join or the `MERGE` source, and use `INSERTED` and `DELETED` for the changed row.

## Differences from SQL Server

- `OUTPUT ... INTO` followed by a second `OUTPUT` that returns the rows is not supported (error 50000, "lexdb: OUTPUT
  INTO followed by an OUTPUT clause that returns rows is not supported yet").
- `DELETED` in an `INSERT` gives the inserted row's values; SQL Server refuses it (error 4104).
- There are no triggers, so the rules SQL Server has for `OUTPUT` to a client on a table with triggers do not
  apply.

## Examples

<!--setup: tsql
CREATE TABLE dbo.item (id int IDENTITY PRIMARY KEY, name nvarchar(20) NOT NULL, qty int DEFAULT 0);
CREATE TABLE dbo.audit (act nvarchar(10), item_id int, old_qty int, new_qty int);
INSERT dbo.item (name, qty) VALUES (N'bolt', 10), (N'nut', 20), (N'gear', 5);
-->

The examples use two tables:

```sql
CREATE TABLE dbo.item (id int IDENTITY PRIMARY KEY, name nvarchar(20) NOT NULL, qty int DEFAULT 0);
CREATE TABLE dbo.audit (act nvarchar(10), item_id int, old_qty int, new_qty int);
INSERT dbo.item (name, qty) VALUES (N'bolt', 10), (N'nut', 20), (N'gear', 5);
```

### A. The new identity values of an INSERT

<!-- example: tsql -->
```sql
INSERT dbo.item (name) OUTPUT INSERTED.* VALUES (N'cog'), (N'axle');
```

```text
id name qty
-- ---- ---
4  cog  0
5  axle 0

(2 rows affected)
```

### B. Before and after in an UPDATE

<!-- example: tsql -->
```sql
UPDATE dbo.item SET qty = qty * 2
OUTPUT INSERTED.id, DELETED.qty AS before, INSERTED.qty AS after, INSERTED.qty - DELETED.qty AS change
WHERE qty > 0;
```

```text
id before after change
-- ------ ----- ------
1  10     20    10
2  20     40    20
3  5      10    5

(3 rows affected)
```

### C. The removed rows of a DELETE

<!-- example: tsql -->
```sql
DELETE FROM dbo.item OUTPUT DELETED.id, UPPER(DELETED.name) AS name WHERE qty = 0;
```

```text
id name
-- ----
4  COG
5  AXLE

(2 rows affected)
```

### D. INTO a table, with a column list

<!-- example: tsql -->
```sql
UPDATE dbo.item SET qty = qty + 1
OUTPUT N'update', INSERTED.id, DELETED.qty, INSERTED.qty INTO dbo.audit
WHERE id = 1;
DELETE FROM dbo.item
OUTPUT N'delete', DELETED.id, DELETED.qty INTO dbo.audit (act, item_id, old_qty)
WHERE name = N'gear';
SELECT * FROM dbo.audit ORDER BY item_id;
```

```text
(1 row affected)

(1 row affected)

act    item_id old_qty new_qty
------ ------- ------- -------
update 1       20      21
delete 3       10      NULL

(2 rows affected)
```

### E. INTO a table variable, from MERGE with the source's columns

<!-- example: tsql -->
```sql
DECLARE @log TABLE (act nvarchar(10), src_id int, id int, name nvarchar(20));
MERGE dbo.item AS t
USING (VALUES (1, N'bolt'), (50, N'pin')) AS s (id, name) ON t.id = s.id
WHEN MATCHED THEN UPDATE SET qty = 0
WHEN NOT MATCHED THEN INSERT (name) VALUES (s.name)
OUTPUT $action, s.id, INSERTED.id, INSERTED.name INTO @log;
SELECT * FROM @log ORDER BY src_id;
```

```text
(2 rows affected)

act    src_id id name
------ ------ -- ----
UPDATE 1      1  bolt
INSERT 50     6  pin

(2 rows affected)
```

### F. Errors

<!-- example: tsql -->
```sql
UPDATE dbo.item SET qty = 1 OUTPUT INSERTED.id INTO #missing WHERE id = 1;
GO
UPDATE dbo.item SET qty = 1 OUTPUT INSERTED.id INTO dbo.audit (item_id) OUTPUT INSERTED.name WHERE id = 1;
GO
UPDATE dbo.item SET qty = 1 OUTPUT INSERTED.id, (SELECT COUNT(*) FROM dbo.audit) AS audited WHERE id = 1;
GO
```

```text
Msg 208, Level 16, State 1, Line 1
Invalid object name '#missing'.
Msg 50000, Level 16, State 1, Line 1
lexdb: OUTPUT INTO followed by an OUTPUT clause that returns rows is not supported yet
Msg 10705, Level 16, State 1, Line 1
Subqueries are not allowed in the OUTPUT clause.
```

## See also

[INSERT](insert.md) · [UPDATE](update.md) · [DELETE](delete.md) · [MERGE](merge.md)
