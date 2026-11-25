# DROP PROPERTY GRAPH

Removes a property graph.

**Door:** PostgreSQL. **Follows:** SQL:2023 property graph queries (SQL/PGQ, ISO/IEC 9075-16). PostgreSQL 18 has no
property graphs; lexdb adds them to this door.

## Syntax

```
DROP PROPERTY GRAPH [ IF EXISTS ] [ schema. ] graph [ RESTRICT | CASCADE ]
```

## Arguments

`IF EXISTS`
: Does nothing when there is no graph of that name.

*graph*
: The graph to drop. One that does not exist is 42704 (`property graph does not exist`), and so is the name of a table:
  `DROP PROPERTY GRAPH` drops only graphs, and `DROP TABLE` or `DROP VIEW` of a graph's name is 42P01.

`RESTRICT`, `CASCADE`
: Accepted as optional SQL standard clauses.

## Remarks

- The tables the graph names are not touched: their rows, keys and indexes stay.
- A view that reads the graph through [GRAPH_TABLE](graph-table.md) stays; reading it fails with 42704 until a graph of
  that name is created again (example B).
- A graph whose underlying tables have been dropped can still be dropped.
- A quoted name is exact: `DROP PROPERTY GRAPH mixg` is 42704 for a graph `"MixG"`.

## Examples

<!-- setup: postgresql
CREATE TABLE people (id int PRIMARY KEY, name text);
INSERT INTO people VALUES (1, 'Ann'), (2, 'Bob');
-->

The examples use a table of people:

```sql
CREATE TABLE people (id int PRIMARY KEY, name text);
INSERT INTO people VALUES (1, 'Ann'), (2, 'Bob');
```

### A. Drop a graph

<!-- example: postgresql -->
```sql
CREATE PROPERTY GRAPH g VERTEX TABLES (people);
DROP PROPERTY GRAPH g;
SELECT count(*) AS n FROM people;
DROP PROPERTY GRAPH g;
DROP PROPERTY GRAPH IF EXISTS g;
DROP PROPERTY GRAPH people;
```

```text
CREATE PROPERTY GRAPH
DROP PROPERTY GRAPH
 n
---
 2
(1 row)

ERROR:  property graph does not exist
DROP PROPERTY GRAPH
ERROR:  property graph does not exist
```

### B. A view over a dropped graph

<!-- example: postgresql -->
```sql
CREATE PROPERTY GRAPH g VERTEX TABLES (people);
CREATE VIEW names AS SELECT * FROM GRAPH_TABLE (g MATCH (p) COLUMNS (p.name));
DROP PROPERTY GRAPH g;
SELECT * FROM names;
CREATE PROPERTY GRAPH g VERTEX TABLES (people);
SELECT * FROM names ORDER BY name;
DROP VIEW names;
DROP PROPERTY GRAPH g RESTRICT;
```

```text
CREATE PROPERTY GRAPH
CREATE VIEW
DROP PROPERTY GRAPH
ERROR:  property graph does not exist
CREATE PROPERTY GRAPH
 name
------
 Ann
 Bob
(2 rows)

DROP VIEW
DROP PROPERTY GRAPH
```

## See also

[CREATE PROPERTY GRAPH](create-property-graph.md) · [GRAPH_TABLE](graph-table.md) · [DROP TABLE](drop-table.md)
