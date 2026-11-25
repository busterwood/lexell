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
- A view that reads the graph through [GRAPH_TABLE](graph-table.md) stays, and reading it is ORA-04063 (`view ... has
  errors`) until a graph of that name is made again; its `USER_OBJECTS.STATUS` is `INVALID` while the graph is gone and
  `VALID` as soon as it is back (example B).
- `CASCADE` and `PURGE` after the name are ORA-03049, as in Oracle (example C).
- A graph whose tables are gone can be dropped.

## Differences from Oracle

- `USER_OBJECTS.STATUS` of the view is `VALID` again as soon as the graph is made again; Oracle shows it `INVALID` until
  the view's next use (example B).
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
SELECT object_name, status FROM user_objects WHERE object_name = 'NAMES';
SELECT * FROM names ORDER BY 1;
```

```text
Property graph created.

View created.

Property graph dropped.

ERROR:
ORA-04063: view "SA.NAMES" has errors

OBJECT_NAME STATUS
----------- -------
NAMES       INVALID

1 row selected.

Property graph created.

OBJECT_NAME STATUS
----------- ------
NAMES       VALID

1 row selected.

NAME
----
Ann
Bob

2 rows selected.
```

The view is `INVALID` while the graph is gone and `VALID` as soon as it is back. Oracle shows `INVALID` in the second
query of `USER_OBJECTS` and `VALID` after the view is read.

### C. CASCADE and PURGE

<!-- example: oracle -->
```sql
DROP PROPERTY GRAPH g CASCADE;
DROP PROPERTY GRAPH g PURGE;
DROP PROPERTY GRAPH g;
```

```text
ERROR:
ORA-03049: SQL keyword 'CASCADE' is not syntactically valid following 'DROP PROPERTY GRAPH g '

ERROR:
ORA-03049: SQL keyword 'PURGE' is not syntactically valid following 'DROP PROPERTY GRAPH g '

Property graph dropped.
```

## See also

[CREATE PROPERTY GRAPH](create-property-graph.md) · [GRAPH_TABLE](graph-table.md) · [DROP TABLE](drop-table.md)
