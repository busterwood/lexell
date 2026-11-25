# DROP PROPERTY GRAPH (Transact-SQL)

Removes a property graph.

**Door:** SQL Server (TDS). **Follows:** SQL:2023 property graph queries (SQL/PGQ, ISO/IEC 9075-16). SQL Server has no
`DROP PROPERTY GRAPH`; lexdb adds the standard statement to this door.

## Syntax

```
DROP PROPERTY GRAPH [ IF EXISTS ] [ schema_name . ] graph_name [ RESTRICT | CASCADE ]
[ ; ]
```

## Arguments

`IF EXISTS`
: Does nothing when there is no graph of that name.

*graph_name*
: The graph to drop. One that does not exist is error 3701 (`Cannot drop the property graph 'g', because it does not
  exist or you do not have permission.`, severity 11), and so is the name of a table: `DROP PROPERTY GRAPH` drops only
  graphs, and `DROP TABLE` or `DROP VIEW` of a graph's name is error 3701.

`RESTRICT`, `CASCADE`
: Accepted as optional SQL standard clauses.

## Remarks

- The tables the graph names are not touched: their rows, keys and indexes stay.
- A view that reads the graph through [GRAPH_TABLE](graph-table.md) stays; reading it fails with error 208 until a graph
  of that name is created again (example B).
- A graph whose underlying tables have been dropped can still be dropped.
- A graph created in the PostgreSQL or Oracle door can be dropped here, and one created here can be dropped from those
  doors.

## Examples

<!--setup: tsql
CREATE TABLE dbo.people (id int PRIMARY KEY, name nvarchar(30));
INSERT dbo.people VALUES (1, N'Ann'), (2, N'Bob');
-->

The examples use a table of people:

```sql
CREATE TABLE dbo.people (id int PRIMARY KEY, name nvarchar(30));
INSERT dbo.people VALUES (1, N'Ann'), (2, N'Bob');
```

### A. Drop a graph

<!-- example: tsql -->
```sql
CREATE PROPERTY GRAPH dbo.g VERTEX TABLES (dbo.people);
DROP PROPERTY GRAPH dbo.g;
SELECT COUNT(*) AS n FROM dbo.people;
GO
DROP PROPERTY GRAPH dbo.g;
GO
DROP PROPERTY GRAPH IF EXISTS dbo.g;
GO
DROP PROPERTY GRAPH dbo.people;
```

```text
n
-
2

(1 row affected)

Msg 3701, Level 11, State 1, Line 1
Cannot drop the property graph 'g', because it does not exist or you do not have permission.
Msg 3701, Level 11, State 1, Line 1
Cannot drop the property graph 'people', because it does not exist or you do not have permission.
```

### B. A view over a dropped graph

<!-- example: tsql -->
```sql
CREATE PROPERTY GRAPH dbo.g VERTEX TABLES (dbo.people);
GO
CREATE VIEW dbo.names AS SELECT * FROM GRAPH_TABLE (dbo.g MATCH (p) COLUMNS (p.name));
GO
DROP PROPERTY GRAPH dbo.g;
SELECT * FROM dbo.names;
GO
CREATE PROPERTY GRAPH dbo.g VERTEX TABLES (dbo.people);
SELECT * FROM dbo.names ORDER BY name;
DROP VIEW dbo.names;
DROP PROPERTY GRAPH dbo.g RESTRICT;
```

```text
Msg 208, Level 16, State 1, Line 2
Invalid object name 'g'.
name
----
Ann
Bob

(2 rows affected)
```

## See also

[CREATE PROPERTY GRAPH](create-property-graph.md) · [GRAPH_TABLE](graph-table.md) · [DROP TABLE](drop-table.md)
