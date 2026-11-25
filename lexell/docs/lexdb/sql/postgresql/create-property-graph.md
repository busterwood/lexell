# CREATE PROPERTY GRAPH

Creates a property graph: names for the vertices and edges that rows of tables stand for, their labels and their
properties, for [GRAPH_TABLE](graph-table.md) to match patterns over.

**Door:** PostgreSQL. **Follows:** SQL:2023 property graph queries (SQL/PGQ, ISO/IEC 9075-16). PostgreSQL 18 has no
property graphs; lexdb adds them to this door with PostgreSQL's identifier folding, types, expressions and SQLSTATEs.

## Syntax

```
CREATE [ OR REPLACE ] PROPERTY GRAPH [ IF NOT EXISTS ] [ schema. ] graph
    { VERTEX | NODE } TABLES ( vertex_table [, vertex_table ]... )
    [ { EDGE | RELATIONSHIP } TABLES ( edge_table [, edge_table ]... ) ]

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
: Does nothing when a graph of that name exists (the command tag is still `CREATE PROPERTY GRAPH`). A table, view or
  sequence of the same name is still 42P07.

*graph*
: The graph's name. It shares the namespace of tables, views and sequences: a name one of them has is 42P07, and so is
  `CREATE TABLE` of a graph's name. Unquoted names fold to lower case; double-quoted names keep their case.

`VERTEX TABLES` (`NODE TABLES`)
: The tables whose rows are vertices. Each is an *element* of the graph, named by its alias (`people AS p`) or the
  table's name; two elements of one name are 42710, so a table is two elements under two aliases. A view may be one,
  with a `KEY`. `NODE TABLES` is accepted as the SQL:2023 synonym for `VERTEX TABLES`.

`EDGE TABLES` (`RELATIONSHIP TABLES`)
: The tables whose rows are edges. Each row is an edge from the vertex its `SOURCE` columns name to the one its
  `DESTINATION` columns name. A graph may have no edge tables. `RELATIONSHIP TABLES` is accepted as the SQL:2023
  synonym for `EDGE TABLES`.

`KEY (` *column* ... `)`
: The columns that tell the element's rows apart. The default is the table's primary key; a table without one or a view
  without `KEY` is 42P10. A column named twice is 42701.

`SOURCE`, `DESTINATION`
: The two ends of an edge. `KEY (src) REFERENCES people (id)`: the edge's `src` is a vertex's `id`, in the vertex
  element `people` (its element name: with an alias, the alias; an unknown vertex element is 42P01). The vertex columns
  are the vertex element's key when left out, and need not be a key. The two lists must have as many columns (42P10).
  Without `KEY ... REFERENCES` (`SOURCE people`), the end is the edge table's foreign key to the vertex table; exactly
  one is needed (42P10 when there is none or more than one).

`LABEL` *label*
: A label of the element, with its properties. An element may have several. Vertex and edge labels share one set of
  names.

`DEFAULT LABEL`
: A label named as the element.

*properties*
: The label's properties. `PROPERTIES (name, upper(city) AS town)` lists columns and expressions; an expression needs
  `AS` (42601) and may use only immutable functions (`now()`, `random()`, `gen_random_uuid()` and the like are 42P17);
  a property twice in a label is 42701. `ALL COLUMNS` is every column of the table as it is now, `EXCEPT` leaves some
  out, and `NO PROPERTIES` gives none. Without a properties clause a label has all columns.

Without any `LABEL`, an element has the default label (its own name), with the properties given or all columns.

## Remarks

- A label may be on several elements, and then it has the same property names on each (42710), each of one kind of
  type: an `integer` on one and `text` on another is 42804 (`integer` and `numeric` agree). A pattern `(x IS label)`
  then matches the rows of all of them (example E).
- The graph keeps names: the tables are not changed, and [GRAPH_TABLE](graph-table.md) reads their rows as they are
  when it runs. A column added after `CREATE` is no property, even under `ALL COLUMNS`.
- A table the graph uses can be dropped or renamed, and a column it names dropped or renamed. The graph stays, and
  `GRAPH_TABLE` over it fails (42P01 for a missing table, 42703 for a missing column) until a table and columns of
  those names are there again.
- Bind parameters (`$1`) are not allowed in `CREATE PROPERTY GRAPH` (42P02).
- A replica refuses the statement (25006); it has the master's graphs.
- A graph is dropped with [DROP PROPERTY GRAPH](drop-property-graph.md).

## Differences from the standard

- There is no `ALTER PROPERTY GRAPH`, and no `pg_catalog` or `information_schema` property-graph views yet (`pg_dump`
  does not include property graphs).
- `GRAPH_TABLE` reads the underlying tables with the session's own table privileges; there are no separate privileges
  on a property graph object.
- The Oracle door has the same statement (see [Oracle CREATE PROPERTY GRAPH](../oracle/create-property-graph.md)); the
  SQL Server door has no property graphs.

## Examples

<!-- setup: postgresql
CREATE TABLE people (id int PRIMARY KEY, name text, city text);
CREATE TABLE companies (id int PRIMARY KEY, name text, city text);
CREATE TABLE knows (id int PRIMARY KEY, src int REFERENCES people (id), dst int REFERENCES people (id), since int);
CREATE TABLE works_at (pid int REFERENCES people (id), cid int REFERENCES companies (id), role text, PRIMARY KEY (pid, cid));
INSERT INTO people VALUES (1, 'Ann', 'Oslo'), (2, 'Bob', 'Rome'), (3, 'Cid', 'Oslo'), (4, 'Dee', 'Pisa');
INSERT INTO companies VALUES (10, 'Acme', 'Oslo'), (11, 'Bolt', 'Rome');
INSERT INTO knows VALUES (100, 1, 2, 2010), (101, 2, 3, 2012), (102, 3, 4, 2015), (103, 1, 3, 2018);
INSERT INTO works_at VALUES (1, 10, 'dev'), (2, 10, 'ops'), (3, 11, 'dev');
-->

The examples use four tables: people, companies, who knows whom, and who works where.

```sql
CREATE TABLE people (id int PRIMARY KEY, name text, city text);
CREATE TABLE companies (id int PRIMARY KEY, name text, city text);
CREATE TABLE knows (id int PRIMARY KEY, src int REFERENCES people (id), dst int REFERENCES people (id), since int);
CREATE TABLE works_at (pid int REFERENCES people (id), cid int REFERENCES companies (id), role text, PRIMARY KEY (pid, cid));
INSERT INTO people VALUES (1, 'Ann', 'Oslo'), (2, 'Bob', 'Rome'), (3, 'Cid', 'Oslo'), (4, 'Dee', 'Pisa');
INSERT INTO companies VALUES (10, 'Acme', 'Oslo'), (11, 'Bolt', 'Rome');
INSERT INTO knows VALUES (100, 1, 2, 2010), (101, 2, 3, 2012), (102, 3, 4, 2015), (103, 1, 3, 2018);
INSERT INTO works_at VALUES (1, 10, 'dev'), (2, 10, 'ops'), (3, 11, 'dev');
```

### A. Vertices, edges, labels and computed properties

<!-- example: postgresql -->
```sql
CREATE PROPERTY GRAPH social
  VERTEX TABLES (
    people KEY (id)
      LABEL person PROPERTIES (id, name, upper(city) AS town),
    companies KEY (id)
      LABEL company PROPERTIES (id, name, city)
  )
  EDGE TABLES (
    knows
      SOURCE KEY (src) REFERENCES people (id)
      DESTINATION KEY (dst) REFERENCES people (id)
      LABEL knows PROPERTIES (since),
    works_at
      SOURCE KEY (pid) REFERENCES people (id)
      DESTINATION KEY (cid) REFERENCES companies (id)
      LABEL works_at PROPERTIES (role)
  );

SELECT * FROM GRAPH_TABLE (social
  MATCH (p IS person) -[w IS works_at]-> (c IS company)
  COLUMNS (p.name AS person, p.town, c.name AS company, w.role)
) ORDER BY person;
```

```text
CREATE PROPERTY GRAPH
 person | town | company | role
--------+------+---------+------
 Ann    | OSLO | Acme    | dev
 Bob    | ROME | Acme    | ops
 Cid    | OSLO | Bolt    | dev
(3 rows)
```

### B. Defaults: primary keys, foreign keys and `NODE` / `RELATIONSHIP` synonyms

`works_at` has one foreign key to `people` and one to `companies`, so `SOURCE` and `DESTINATION` need only the vertex
element names. `NODE TABLES` and `RELATIONSHIP TABLES` are SQL:2023 synonyms for `VERTEX TABLES` and `EDGE TABLES`.

<!-- example: postgresql -->
```sql
CREATE PROPERTY GRAPH staff
  NODE TABLES (people, companies)
  RELATIONSHIP TABLES (works_at SOURCE people DESTINATION companies);

SELECT * FROM GRAPH_TABLE (staff
  MATCH (p IS people) -[w IS works_at]-> (c IS companies)
  COLUMNS (p.name AS person, c.name AS company, w.role)
) ORDER BY person;
```

```text
CREATE PROPERTY GRAPH
 person | company | role
--------+---------+------
 Ann    | Acme    | dev
 Bob    | Acme    | ops
 Cid    | Bolt    | dev
(3 rows)
```

### C. `OR REPLACE`, `ALL COLUMNS EXCEPT` and `NO PROPERTIES`

<!-- example: postgresql -->
```sql
CREATE OR REPLACE PROPERTY GRAPH staff
  VERTEX TABLES (
    people PROPERTIES ARE ALL COLUMNS EXCEPT (city),
    companies DEFAULT LABEL PROPERTIES (id, name)
  )
  EDGE TABLES (
    works_at SOURCE people DESTINATION companies NO PROPERTIES
  );

SELECT * FROM GRAPH_TABLE (staff
  MATCH (p IS people) -[w IS works_at]-> (c IS companies)
  COLUMNS (p.name AS person, c.name AS company)
) ORDER BY person;
```

```text
CREATE PROPERTY GRAPH
 person | company
--------+---------
 Ann    | Acme
 Bob    | Acme
 Cid    | Bolt
(3 rows)
```

### D. `IF NOT EXISTS` and namespace collisions

<!-- example: postgresql -->
```sql
CREATE PROPERTY GRAPH IF NOT EXISTS staff VERTEX TABLES (companies);
CREATE PROPERTY GRAPH staff VERTEX TABLES (companies);
CREATE PROPERTY GRAPH people VERTEX TABLES (companies);
```

```text
CREATE PROPERTY GRAPH
ERROR:  relation "staff" already exists
ERROR:  relation "people" already exists
```

### E. One label on two vertex tables

<!-- example: postgresql -->
```sql
CREATE PROPERTY GRAPH named
  VERTEX TABLES (
    people LABEL entity PROPERTIES (id, name),
    companies LABEL entity PROPERTIES (id, name)
  );
SELECT * FROM GRAPH_TABLE (named MATCH (x IS entity) COLUMNS (x.id, x.name)) ORDER BY id;
CREATE PROPERTY GRAPH bad
  VERTEX TABLES (people LABEL entity PROPERTIES (id), companies LABEL entity PROPERTIES (id, name));
CREATE PROPERTY GRAPH bad
  VERTEX TABLES (people LABEL entity PROPERTIES (id AS v), companies LABEL entity PROPERTIES (name AS v));
```

```text
CREATE PROPERTY GRAPH
 id | name
----+------
  1 | Ann
  2 | Bob
  3 | Cid
  4 | Dee
 10 | Acme
 11 | Bolt
(6 rows)

ERROR:  label entity already defined
ERROR:  cannot use mixed type for property v of label entity
```

## See also

[GRAPH_TABLE](graph-table.md) · [DROP PROPERTY GRAPH](drop-property-graph.md) · [SELECT](select.md) ·
[CREATE VIEW](create-view.md)
