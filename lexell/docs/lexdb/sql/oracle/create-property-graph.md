# CREATE PROPERTY GRAPH

Creates a property graph: names for the vertices and edges that rows of tables stand for, their labels and their
properties, for [GRAPH_TABLE](graph-table.md) to match patterns over.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai (SQL/PGQ, ISO/IEC 9075-16).

## Syntax

```
CREATE [ OR REPLACE ] PROPERTY GRAPH [ IF NOT EXISTS ] [ schema. ] graph
    VERTEX TABLES ( vertex_table [, vertex_table ]... )
    [ EDGE TABLES ( edge_table [, edge_table ]... ) ]

vertex_table:
    table [ [ AS ] element ] [ KEY ( column [, ...] ) ] [ labels ]

edge_table:
    table [ [ AS ] element ] [ KEY ( column [, ...] ) ]
        SOURCE [ KEY ( column [, ...] ) REFERENCES ] vertex_element [ ( column [, ...] ) ]
        DESTINATION [ KEY ( column [, ...] ) REFERENCES ] vertex_element [ ( column [, ...] ) ]
        [ labels ]

labels:
    { LABEL label | DEFAULT LABEL } [ properties ] [ { LABEL label | DEFAULT LABEL } [ properties ] ]...
  | properties

properties:
    PROPERTIES ( { column | expression AS name } [, ...] )
  | PROPERTIES [ ARE ] ALL COLUMNS [ EXCEPT ( column [, ...] ) ]
  | NO PROPERTIES
```

## Arguments

`OR REPLACE`
: Replaces the graph of that name, if there is one.

`IF NOT EXISTS`
: Does nothing when a graph of that name exists (the client still prints `Property graph created.`).

*graph*
: The graph's name. It shares the namespace of tables, views and sequences: a name one of them has is ORA-00955, and
  so is `CREATE TABLE` of a graph's name.

`VERTEX TABLES`
: The tables whose rows are vertices. Each is an *element* of the graph, named by its alias (`people AS p`) or the
  table's name; two elements of one name are ORA-42404, so a table is two elements under two aliases. A view may be
  one, with a `KEY`.

`EDGE TABLES`
: The tables whose rows are edges. Each row is an edge from the vertex its `SOURCE` columns name to the one its
  `DESTINATION` columns name. A graph may have no edge tables.

`KEY (` *column* ... `)`
: The columns that tell the element's rows apart. The default is the table's primary key; a table without one is
  ORA-42402, a view without `KEY` ORA-42442. A column named twice is ORA-42416.

`SOURCE`, `DESTINATION`
: The two ends of an edge. `KEY (src) REFERENCES people (id)`: the edge's `src` is a vertex's `id`, in the vertex
  element `people` (its element name: with an alias, the alias, ORA-42405 for the table's name). The vertex columns
  are the vertex element's key when left out, and need not be a key. The two lists must have as many columns
  (ORA-42415). Without `KEY ... REFERENCES` (`SOURCE people`), the end is the edge table's foreign key to the vertex
  table; one is needed (ORA-42413 when there is none, ORA-42431 when there are several).

`LABEL` *label*
: A label of the element, with its properties. An element may have several. Vertex and edge labels share one set of
  names.

`DEFAULT LABEL`
: A label named as the element.

*properties*
: The label's properties. `PROPERTIES (name, UPPER(city) AS town)` lists columns and expressions; an expression needs
  `AS` (ORA-42424) and may use only deterministic functions (`SYSDATE` is ORA-42439); a property twice in a label is
  ORA-42407. `ALL COLUMNS` is every column of the table as it is now, `EXCEPT` leaves some out, and `NO PROPERTIES`
  gives none. Without a properties clause a label has all columns.

Without any `LABEL`, an element has the default label (its own name), with the properties given or all columns.

## Remarks

- A label may be on several elements, and then it has the same property names on each (ORA-42409), each of one kind
  of type: a `NUMBER` on one and a `VARCHAR2` on another is ORA-42414 (`VARCHAR2(10)` and `VARCHAR2(20)` agree). A
  pattern `(x IS label)` then matches the rows of all of them (example E).
- The graph keeps names: the tables are not changed, and [GRAPH_TABLE](graph-table.md) reads their rows as they are
  when it runs. A column added after `CREATE` is no property, even under `ALL COLUMNS`.
- A table the graph uses can be dropped or renamed, and a column it names dropped or renamed. The graph stays, its
  `USER_OBJECTS.STATUS` is `INVALID`, and `GRAPH_TABLE` over it is ORA-04045 until a table and columns of those
  names are there again (example G).
- `USER_PROPERTY_GRAPHS`, `USER_PG_ELEMENTS`, `USER_PG_LABELS`, `USER_PG_LABEL_PROPERTIES` and the other `PG_` views
  describe the graph; see [the data dictionary](data-dictionary-tables.md).
- A replica refuses the statement (ORA-16000); it has the master's graphs.
- A graph is dropped with [DROP PROPERTY GRAPH](drop-property-graph.md).

## Differences from Oracle

- `USER_OBJECTS.STATUS` says whether the tables and columns the graph names are there. Oracle marks a graph `INVALID`
  when a column of one of its tables is changed (`ALTER TABLE ... MODIFY`, a column renamed), even when its names are
  all there, and `VALID` again at its next use; `ADD` of a column and `CREATE INDEX` leave it `VALID`.
- `USER_PG_ELEMENTS.OBJECT_NAME`, `USER_PG_PROP_DEFINITIONS.COLUMN_NAME` and the types in
  `USER_PG_LABEL_PROPERTIES` are as they were at `CREATE`; Oracle's follow a rename and an `ALTER TABLE ... MODIFY`.
- `ALTER TABLE ... DROP COLUMN` of a column that a graph names, or that a view reads (directly or through
  `GRAPH_TABLE`), drops it, as in Oracle. The graph is `INVALID`, a view over it is `INVALID` too, and reading the view
  is ORA-04063; `USER_ERRORS` has the view's error, ORA-04045 and its cause (example J). `USER_OBJECTS.STATUS` and
  `USER_ERRORS` say what the view's query does now: Oracle fills `USER_ERRORS` at the view's next use, and when the
  column is back it keeps the graph and the view `INVALID`, with ORA-04063 on every read until the view is compiled
  (`ALTER VIEW v COMPILE`); lexdb's are `VALID`, and the view readable, as soon as the column is back (the last two
  statements of example J).
- `COMMENT ON PROPERTY GRAPH` is accepted and not kept (`USER_PG_COMMENTS.COMMENTS` stays empty), as for every
  `COMMENT ON` in lexdb. `ALTER PROPERTY GRAPH ... COMPILE` is ORA-03001, and privileges on a graph
  (`GRANT READ ON PROPERTY GRAPH`) ORA-00942: `GRAPH_TABLE` reads the tables with the session's privileges.
- The PostgreSQL door also supports property graphs (see [PostgreSQL CREATE PROPERTY GRAPH](../postgresql/create-property-graph.md)). SQL Server has none: the statement is a syntax error in that door (Msg 102).

## Examples

<!--setup: oracle
CREATE TABLE people (id NUMBER PRIMARY KEY, name VARCHAR2(20), city VARCHAR2(20));
CREATE TABLE companies (id NUMBER PRIMARY KEY, name VARCHAR2(20), city VARCHAR2(20));
CREATE TABLE knows (id NUMBER PRIMARY KEY, src NUMBER REFERENCES people (id), dst NUMBER REFERENCES people (id), since NUMBER);
CREATE TABLE works_at (pid NUMBER REFERENCES people (id), cid NUMBER REFERENCES companies (id), role VARCHAR2(10), PRIMARY KEY (pid, cid));
INSERT INTO people VALUES (1, 'Ann', 'Oslo');
INSERT INTO people VALUES (2, 'Bob', 'Rome');
INSERT INTO people VALUES (3, 'Cid', 'Oslo');
INSERT INTO people VALUES (4, 'Dee', 'Pisa');
INSERT INTO companies VALUES (10, 'Acme', 'Oslo');
INSERT INTO companies VALUES (11, 'Bolt', 'Rome');
INSERT INTO knows VALUES (100, 1, 2, 2010);
INSERT INTO knows VALUES (101, 2, 3, 2012);
INSERT INTO knows VALUES (102, 3, 4, 2015);
INSERT INTO knows VALUES (103, 1, 3, 2018);
INSERT INTO works_at VALUES (1, 10, 'dev');
INSERT INTO works_at VALUES (2, 10, 'ops');
INSERT INTO works_at VALUES (3, 11, 'dev');
COMMIT;
-->

The examples use four tables: people, companies, who knows whom, and who works where.

```sql
CREATE TABLE people (id NUMBER PRIMARY KEY, name VARCHAR2(20), city VARCHAR2(20));
CREATE TABLE companies (id NUMBER PRIMARY KEY, name VARCHAR2(20), city VARCHAR2(20));
CREATE TABLE knows (id NUMBER PRIMARY KEY, src NUMBER REFERENCES people (id), dst NUMBER REFERENCES people (id),
                    since NUMBER);
CREATE TABLE works_at (pid NUMBER REFERENCES people (id), cid NUMBER REFERENCES companies (id), role VARCHAR2(10),
                       PRIMARY KEY (pid, cid));
INSERT INTO people VALUES (1, 'Ann', 'Oslo');
INSERT INTO people VALUES (2, 'Bob', 'Rome');
INSERT INTO people VALUES (3, 'Cid', 'Oslo');
INSERT INTO people VALUES (4, 'Dee', 'Pisa');
INSERT INTO companies VALUES (10, 'Acme', 'Oslo');
INSERT INTO companies VALUES (11, 'Bolt', 'Rome');
INSERT INTO knows VALUES (100, 1, 2, 2010);
INSERT INTO knows VALUES (101, 2, 3, 2012);
INSERT INTO knows VALUES (102, 3, 4, 2015);
INSERT INTO knows VALUES (103, 1, 3, 2018);
INSERT INTO works_at VALUES (1, 10, 'dev');
INSERT INTO works_at VALUES (2, 10, 'ops');
INSERT INTO works_at VALUES (3, 11, 'dev');
COMMIT;
```

### A. Keys, ends, labels and properties

<!-- example: oracle -->
```sql
CREATE PROPERTY GRAPH social
  VERTEX TABLES (
    people KEY (id) LABEL person PROPERTIES (id, name, city),
    companies KEY (id) LABEL company PROPERTIES (id, name, city)
  )
  EDGE TABLES (
    knows KEY (id)
      SOURCE KEY (src) REFERENCES people (id)
      DESTINATION KEY (dst) REFERENCES people (id)
      LABEL knows PROPERTIES (since),
    works_at KEY (pid, cid)
      SOURCE KEY (pid) REFERENCES people (id)
      DESTINATION KEY (cid) REFERENCES companies (id)
      LABEL works_at PROPERTIES (role)
  );
SELECT * FROM GRAPH_TABLE (social
  MATCH (a IS person) -[k IS knows]-> (b IS person) -[w IS works_at]-> (c IS company)
  COLUMNS (a.name AS who, b.name AS knows_whom, c.name AS at_company, k.since AS since)
) ORDER BY 1, 2;
SELECT graph_name, edge_tab_name, vertex_tab_name, edge_end, edge_col_name, vertex_col_name
FROM user_pg_edge_relationships ORDER BY 2, 4 DESC;
```

```text
Property graph created.

WHO KNOWS_WHOM AT_COMPANY SINCE
--- ---------- ---------- -----
Ann Bob        Acme        2010
Ann Cid        Bolt        2018
Bob Cid        Bolt        2012

3 rows selected.

GRAPH_NAME EDGE_TAB_NAME VERTEX_TAB_NAME EDGE_END    EDGE_COL_NAME VERTEX_COL_NAME
---------- ------------- --------------- ----------- ------------- ---------------
SOCIAL     KNOWS         PEOPLE          SOURCE      SRC           ID
SOCIAL     KNOWS         PEOPLE          DESTINATION DST           ID
SOCIAL     WORKS_AT      PEOPLE          SOURCE      PID           ID
SOCIAL     WORKS_AT      COMPANIES       DESTINATION CID           ID

4 rows selected.
```

### B. The defaults

Without `KEY` each table's primary key is its key, `SOURCE people` is the edge table's foreign key to `people`, and
each element has one label, its own name, with every column:

<!-- example: oracle -->
```sql
CREATE PROPERTY GRAPH staff
  VERTEX TABLES (people, companies)
  EDGE TABLES (works_at SOURCE people DESTINATION companies);
SELECT label_name, property_name, data_type, property_order
FROM user_pg_label_properties WHERE graph_name = 'STAFF' ORDER BY 1, 4;
SELECT * FROM GRAPH_TABLE (staff
  MATCH (p IS people) -[w IS works_at]-> (c IS companies)
  COLUMNS (p.name AS person, w.role AS role, c.name AS company)
) ORDER BY 1;
```

```text
Property graph created.

LABEL_NAME PROPERTY_NAME DATA_TYPE PROPERTY_ORDER
---------- ------------- --------- --------------
COMPANIES  ID            NUMBER                 1
COMPANIES  NAME          VARCHAR2               2
COMPANIES  CITY          VARCHAR2               3
PEOPLE     ID            NUMBER                 1
PEOPLE     NAME          VARCHAR2               2
PEOPLE     CITY          VARCHAR2               3
WORKS_AT   PID           NUMBER                 1
WORKS_AT   CID           NUMBER                 2
WORKS_AT   ROLE          VARCHAR2               3

9 rows selected.

PERSON ROLE COMPANY
------ ---- -------
Ann    dev  Acme
Bob    ops  Acme
Cid    dev  Bolt

3 rows selected.
```

### C. Aliases, two labels, expressions and no properties

`OR REPLACE` makes `staff` again. `people` is the element `p`, with two labels; `companies` is `c`, with its default
label and no properties:

<!-- example: oracle -->
```sql
CREATE OR REPLACE PROPERTY GRAPH staff
  VERTEX TABLES (
    people AS p KEY (id)
      LABEL person PROPERTIES ALL COLUMNS EXCEPT (city)
      LABEL resident PROPERTIES (city, UPPER(city) AS town),
    companies AS c DEFAULT LABEL NO PROPERTIES
  )
  EDGE TABLES (
    works_at AS w
      SOURCE KEY (pid) REFERENCES p (id)
      DESTINATION KEY (cid) REFERENCES c (id)
      NO PROPERTIES
  );
SELECT element_name, label_name FROM user_pg_element_labels WHERE graph_name = 'STAFF' ORDER BY 1, 2;
SELECT label_name, property_name, property_order FROM user_pg_label_properties
WHERE graph_name = 'STAFF' ORDER BY 1, 3;
SELECT * FROM GRAPH_TABLE (staff
  MATCH (x IS resident) -> (y IS c)
  COLUMNS (x.name AS name, x.town AS town, VERTEX_ID(y) AS company)
) ORDER BY 1;
```

```text
Property graph created.

ELEMENT_NAME LABEL_NAME
------------ ----------
C            C
P            PERSON
P            RESIDENT
W            W

4 rows selected.

LABEL_NAME PROPERTY_NAME PROPERTY_ORDER
---------- ------------- --------------
PERSON     ID                         1
PERSON     NAME                       2
RESIDENT   CITY                       1
RESIDENT   TOWN                       2

4 rows selected.

NAME TOWN COMPANY
---- ---- --------------------------------------------------------------------------------
Ann  OSLO {"GRAPH_OWNER":"SA","GRAPH_NAME":"STAFF","ELEM_TABLE":"C","KEY_VALUE":{"ID":10}}
Bob  ROME {"GRAPH_OWNER":"SA","GRAPH_NAME":"STAFF","ELEM_TABLE":"C","KEY_VALUE":{"ID":10}}
Cid  OSLO {"GRAPH_OWNER":"SA","GRAPH_NAME":"STAFF","ELEM_TABLE":"C","KEY_VALUE":{"ID":11}}

3 rows selected.
```

### D. IF NOT EXISTS, and names already used

<!-- example: oracle -->
```sql
CREATE PROPERTY GRAPH IF NOT EXISTS staff VERTEX TABLES (companies);
SELECT COUNT(*) AS elements FROM user_pg_elements WHERE graph_name = 'STAFF';
CREATE PROPERTY GRAPH staff VERTEX TABLES (companies);
CREATE PROPERTY GRAPH people VERTEX TABLES (companies);
CREATE TABLE staff (x NUMBER);
CREATE SEQUENCE staff;
```

```text
Property graph created.

ELEMENTS
--------
       3

1 row selected.

ERROR:
ORA-00955: name is already used by an existing object

ERROR:
ORA-00955: name is already used by an existing object

ERROR:
ORA-00955: name is already used by an existing object

ERROR:
ORA-00955: name is already used by an existing object
```

### E. A label on two elements

A label on two elements has one set of properties, of one kind of type each:

<!-- example: oracle -->
```sql
CREATE PROPERTY GRAPH named
  VERTEX TABLES (people LABEL entity PROPERTIES (name), companies LABEL entity PROPERTIES (name));
SELECT * FROM GRAPH_TABLE (named MATCH (x IS entity) COLUMNS (x.name AS name)) ORDER BY 1;
CREATE PROPERTY GRAPH bad
  VERTEX TABLES (people LABEL entity PROPERTIES (name), companies LABEL entity PROPERTIES (name, city));
CREATE PROPERTY GRAPH bad
  VERTEX TABLES (people LABEL entity PROPERTIES (id AS v), companies LABEL entity PROPERTIES (name AS v));
```

```text
Property graph created.

NAME
----
Acme
Ann
Bob
Bolt
Cid
Dee

6 rows selected.

ERROR:
ORA-42409: label ENTITY already defined

ERROR:
ORA-42414: cannot use mixed type for property V of label ENTITY
```

### F. A view, and a table without a primary key

<!-- example: oracle -->
```sql
CREATE VIEW oslo AS SELECT id, name FROM people WHERE city = 'Oslo';
CREATE PROPERTY GRAPH g_oslo VERTEX TABLES (oslo);
CREATE PROPERTY GRAPH g_oslo VERTEX TABLES (oslo KEY (id));
SELECT * FROM GRAPH_TABLE (g_oslo MATCH (v) COLUMNS (v.name AS name)) ORDER BY 1;
CREATE TABLE visits (person_id NUMBER, city VARCHAR2(20));
CREATE PROPERTY GRAPH g_visits VERTEX TABLES (visits);
```

```text
View created.

ERROR:
ORA-42442: KEY is not specified for view graph element table OSLO.

Property graph created.

NAME
----
Ann
Cid

2 rows selected.

Table created.

ERROR:
ORA-42402: cannot infer key for graph element table VISITS
```

### G. When a table goes

<!-- example: oracle -->
```sql
CREATE TABLE offices (id NUMBER PRIMARY KEY, town VARCHAR2(20));
INSERT INTO offices VALUES (1, 'Oslo');
CREATE PROPERTY GRAPH g_offices VERTEX TABLES (offices);
DROP TABLE offices;
SELECT * FROM GRAPH_TABLE (g_offices MATCH (o) COLUMNS (o.town AS town));
SELECT object_name, status FROM user_objects WHERE object_type = 'PROPERTY GRAPH' ORDER BY 1;
CREATE TABLE offices (id NUMBER PRIMARY KEY, town VARCHAR2(20));
INSERT INTO offices VALUES (2, 'Rome');
SELECT * FROM GRAPH_TABLE (g_offices MATCH (o) COLUMNS (o.town AS town));
ALTER TABLE offices RENAME COLUMN town TO city;
SELECT * FROM GRAPH_TABLE (g_offices MATCH (o) COLUMNS (o.town AS town));
ALTER TABLE offices RENAME COLUMN city TO town;
SELECT * FROM GRAPH_TABLE (g_offices MATCH (o) COLUMNS (o.town AS town));
```

```text
Table created.

1 row created.

Property graph created.

Table dropped.

ERROR:
ORA-04045: errors during recompilation or revalidation of SA.G_OFFICES
ORA-00942: table or view "SA"."OFFICES" does not exist

OBJECT_NAME STATUS
----------- -------
G_OFFICES   INVALID
G_OSLO      VALID
NAMED       VALID
SOCIAL      VALID
STAFF       VALID

5 rows selected.

Table created.

1 row created.

TOWN
----
Rome

1 row selected.

Table altered.

ERROR:
ORA-04045: errors during recompilation or revalidation of SA.G_OFFICES
ORA-00904: "TOWN": invalid identifier

Table altered.

TOWN
----
Rome

1 row selected.
```

### H. Errors

<!-- example: oracle -->
```sql
CREATE PROPERTY GRAPH bad VERTEX TABLES (nosuch);
CREATE PROPERTY GRAPH bad VERTEX TABLES (people, people);
CREATE PROPERTY GRAPH bad VERTEX TABLES (people KEY (nosuch));
CREATE PROPERTY GRAPH bad VERTEX TABLES (people PROPERTIES (UPPER(name)));
CREATE PROPERTY GRAPH bad VERTEX TABLES (people PROPERTIES (name, SYSDATE AS today));
CREATE PROPERTY GRAPH bad VERTEX TABLES (people AS p)
  EDGE TABLES (knows SOURCE KEY (src) REFERENCES people (id) DESTINATION KEY (dst) REFERENCES p (id));
CREATE PROPERTY GRAPH bad VERTEX TABLES (people)
  EDGE TABLES (knows SOURCE KEY (src, dst) REFERENCES people (id) DESTINATION KEY (dst) REFERENCES people (id));
CREATE PROPERTY GRAPH bad VERTEX TABLES (people, companies)
  EDGE TABLES (knows SOURCE companies DESTINATION people);
CREATE PROPERTY GRAPH bad VERTEX TABLES (people) EDGE TABLES (knows SOURCE KEY (src) REFERENCES people (id));
```

```text
ERROR:
ORA-00942: table or view "NOSUCH" does not exist

ERROR:
ORA-42404: graph element table name PEOPLE already defined

ERROR:
ORA-00904: "NOSUCH": invalid identifier

ERROR:
ORA-42424: An expression based label property definition must use the AS clause.

ERROR:
ORA-42439: only pure functions can be specified in a column expression used to define a property

ERROR:
ORA-42405: Referenced vertex table PEOPLE does not exist.

ERROR:
ORA-42415: missing key column in edge reference definition

ERROR:
ORA-42413: cannot infer edge relationship for edge table KNOWS

ERROR:
ORA-02000: missing DESTINATION keyword
```

### I. Where lexdb differs

<!-- example: oracle -->
```sql
CREATE PROPERTY GRAPH bad VERTEX TABLES (people) EDGE TABLES (knows SOURCE people DESTINATION people);
COMMENT ON PROPERTY GRAPH social IS 'who knows whom';
SELECT graph_name, comments FROM user_pg_comments WHERE graph_name = 'SOCIAL';
ALTER PROPERTY GRAPH social COMPILE;
GRANT READ ON PROPERTY GRAPH social TO PUBLIC;
```

```text
ERROR:
ORA-42431: ambiguous edge relationship for graph edge table KNOWS

Comment created.

GRAPH_NAME COMMENTS
---------- --------
SOCIAL

1 row selected.

ERROR:
ORA-03001: unimplemented feature: only ALTER TABLE, ALTER INDEX and ALTER SCHEMA are supported

ERROR:
ORA-00942: table or view does not exist
```

The first statement is ORA-42431 as in Oracle (`knows` has two foreign keys to `people`). Oracle also keeps the comment
and runs the last two.

### J. DROP COLUMN under a view over GRAPH_TABLE

<!-- example: oracle -->
```sql
CREATE TABLE dc_rooms (id NUMBER PRIMARY KEY, town VARCHAR2(20), floor_no NUMBER);
INSERT INTO dc_rooms VALUES (1, 'Oslo', 3);
CREATE PROPERTY GRAPH g_rooms VERTEX TABLES (dc_rooms KEY (id) PROPERTIES (town, floor_no));
CREATE VIEW v_towns AS SELECT * FROM GRAPH_TABLE (g_rooms MATCH (r) COLUMNS (r.town AS town));
ALTER TABLE dc_rooms DROP COLUMN floor_no;
SELECT * FROM v_towns;
SELECT name, type, text FROM user_errors WHERE name = 'V_TOWNS' ORDER BY sequence;
ALTER TABLE dc_rooms ADD (floor_no NUMBER);
SELECT * FROM v_towns;
SELECT object_name, status FROM user_objects WHERE object_name IN ('G_ROOMS', 'V_TOWNS') ORDER BY object_name;
```

```text
Table created.

1 row created.

Property graph created.

View created.

Table altered.

ERROR:
ORA-04063: view "SA.V_TOWNS" has errors

NAME    TYPE TEXT
------- ---- ---------------------------------------------------------------------
V_TOWNS VIEW ORA-04045: errors during recompilation or revalidation of SA.G_ROOMS
V_TOWNS VIEW ORA-00904: "FLOOR_NO": invalid identifier

2 rows selected.

Table altered.

TOWN
----
Oslo

1 row selected.

OBJECT_NAME STATUS
----------- ------
G_ROOMS     VALID
V_TOWNS     VALID

2 rows selected.
```

## See also

[GRAPH_TABLE](graph-table.md) · [DROP PROPERTY GRAPH](drop-property-graph.md) ·
[Data dictionary](data-dictionary-tables.md) · [CREATE TABLE](create-table.md) · [CREATE VIEW](create-view.md)
