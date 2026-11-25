# DROP PROPERTY GRAPH

Removes a property graph.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
DROP PROPERTY GRAPH [ IF EXISTS ] [ schema. ] graph
```

## Arguments

`IF EXISTS`
: Does nothing when there is no graph of that name.

*graph*
: The graph to drop. One that does not exist is ORA-42421, and so is the name of a table: `DROP PROPERTY GRAPH`
  drops only graphs, and `DROP TABLE` and `DROP VIEW` of a graph's name are ORA-00942.

## Remarks

- The tables the graph names are not touched: their rows, keys and indexes stay.
- A view that reads the graph through [GRAPH_TABLE](graph-table.md) stays, and reading it is ORA-42421 until a graph
  of that name is made again.
- A graph whose tables are gone can be dropped.

## Differences from Oracle

- A view over a dropped graph is ORA-42421 when read, and its `USER_OBJECTS.STATUS` stays `VALID`; Oracle marks the
  view `INVALID` and gives ORA-04063 (`view ... has errors`) (example B).
- `CASCADE` or `PURGE` after the name is ORA-00900; Oracle gives ORA-03049.
- A quoted name is matched without its case: `DROP PROPERTY GRAPH mixg` drops a graph `"MixG"` (Oracle: ORA-42421).

## Examples

<!--setup: oracle
CREATE TABLE people (id NUMBER PRIMARY KEY, name VARCHAR2(20));
INSERT INTO people VALUES (1, 'Ann');
INSERT INTO people VALUES (2, 'Bob');
COMMIT;
-->

The examples use a table of people:

```sql
CREATE TABLE people (id NUMBER PRIMARY KEY, name VARCHAR2(20));
INSERT INTO people VALUES (1, 'Ann');
INSERT INTO people VALUES (2, 'Bob');
COMMIT;
```

### A. Drop a graph

<!-- example: oracle -->
```sql
CREATE PROPERTY GRAPH g VERTEX TABLES (people);
DROP PROPERTY GRAPH g;
SELECT COUNT(*) AS n FROM people;
DROP PROPERTY GRAPH g;
DROP PROPERTY GRAPH IF EXISTS g;
DROP PROPERTY GRAPH people;
```

```text
Property graph created.

Property graph dropped.

N
-
2

1 row selected.

ERROR:
ORA-42421: property graph does not exist

Property graph dropped.

ERROR:
ORA-42421: property graph does not exist
```

### B. A view over a dropped graph

<!-- example: oracle -->
```sql
CREATE PROPERTY GRAPH g VERTEX TABLES (people);
CREATE VIEW names AS SELECT * FROM GRAPH_TABLE (g MATCH (p) COLUMNS (p.name AS name));
DROP PROPERTY GRAPH g;
SELECT * FROM names;
SELECT object_name, status FROM user_objects WHERE object_name = 'NAMES';
CREATE PROPERTY GRAPH g VERTEX TABLES (people);
SELECT * FROM names ORDER BY 1;
```

```text
Property graph created.

View created.

Property graph dropped.

ERROR:
ORA-42421: property graph does not exist

OBJECT_NAME STATUS
----------- ------
NAMES       VALID

1 row selected.

Property graph created.

NAME
----
Ann
Bob

2 rows selected.
```

Oracle gives ORA-04063 for the first read of the view and shows it `INVALID`.

## See also

[CREATE PROPERTY GRAPH](create-property-graph.md) · [GRAPH_TABLE](graph-table.md) · [DROP TABLE](drop-table.md)
