# CREATE PROPERTY GRAPH (Transact-SQL)

Creates a property graph: names for the vertices and edges that rows of tables stand for, their labels and their
properties, for [GRAPH_TABLE](graph-table.md) to match patterns over.

**Door:** SQL Server (TDS). **Follows:** SQL:2023 property graph queries (SQL/PGQ, ISO/IEC 9075-16), not SQL Server's
proprietary `AS NODE` / `AS EDGE` table syntax. **SQL Server has no `CREATE PROPERTY GRAPH`:** lexdb adds the SQL
standard statement to this door with SQL Server's case-insensitive identifiers, `[bracket]` quoting, `dbo` default
schema, expressions, and error numbers.

## Syntax

```
CREATE [ OR REPLACE | OR ALTER ] PROPERTY GRAPH [ IF NOT EXISTS ] [ schema_name . ] graph_name
    { VERTEX | NODE } TABLES ( vertex_table [ ,...n ] )
    [ { EDGE | RELATIONSHIP } TABLES ( edge_table [ ,...n ] ) ]
[ ; ]

vertex_table ::=
    table_or_view_name [ [ AS ] element_name ] [ KEY ( column_name [ ,...n ] ) ] [ labels ]

edge_table ::=
    table_or_view_name [ [ AS ] element_name ] [ KEY ( column_name [ ,...n ] ) ]
        SOURCE [ KEY ( column_name [ ,...n ] ) REFERENCES ] vertex_element [ ( column_name [ ,...n ] ) ]
        DESTINATION [ KEY ( column_name [ ,...n ] ) REFERENCES ] vertex_element [ ( column_name [ ,...n ] ) ]
        [ labels ]

labels ::=
    { LABEL label_name | DEFAULT LABEL } [ properties ] [ { LABEL label_name | DEFAULT LABEL } [ properties ] ]...
  | properties

properties ::=
    PROPERTIES ( { column_name | expression AS property_name } [ ,...n ] )
  | PROPERTIES [ ARE ] ALL COLUMNS [ EXCEPT ( column_name [ ,...n ] ) ]
  | NO PROPERTIES
```

## Arguments

`OR REPLACE`, `OR ALTER`
: Replaces the graph of that name, if there is one. Both the SQL standard `OR REPLACE` and T-SQL's `OR ALTER` are
  accepted.

`IF NOT EXISTS`
: Does nothing when a graph of that name exists. A table, view or sequence of the same name is still error 2714.

*graph_name*
: The graph's name, optionally schema-qualified (`dbo.social`). It shares the namespace of tables, views, sequences and
  assertions: a name one of them has is error 2714, and so is `CREATE TABLE` of a graph's name. A schema that does not
  exist is error 2760. Names are resolved without regard to case.

`VERTEX TABLES` (`NODE TABLES`)
: The tables whose rows are vertices. Each is an *element* of the graph, named by its alias (`dbo.people AS p`) or the
  table's name; two elements of one name are error 2714, so a table can be two elements under two aliases. A view may be
  one, with a `KEY`. `NODE TABLES` is accepted as the SQL:2023 synonym for `VERTEX TABLES`.

`EDGE TABLES` (`RELATIONSHIP TABLES`)
: The tables whose rows are edges. Each row is an edge from the vertex its `SOURCE` columns name to the one its
  `DESTINATION` columns name. A graph may have no edge tables. `RELATIONSHIP TABLES` is accepted as the SQL:2023
  synonym for `EDGE TABLES`.

`KEY (` *column_name* ... `)`
: The columns that tell the element's rows apart. The default is the table's primary key; a table without one or a view
  without `KEY` is error 50000. A column named twice is error 50000.

`SOURCE`, `DESTINATION`
: The two ends of an edge. `KEY (src) REFERENCES people (id)`: the edge's `src` is a vertex's `id`, in the vertex
  element `people` (its element name: with an alias, the alias; an unknown vertex element is error 208). The vertex
  columns default to the vertex element's key, and need not be a key. The two lists must have as many columns (error
  50000). Without `KEY ... REFERENCES` (`SOURCE people`), the end is the edge table's foreign key to the vertex table;
  exactly one is needed (error 50000 when there is none or more than one).

`LABEL` *label_name*
: A label of the element, with its properties. An element may have several. Vertex and edge labels share one set of
  names.

`DEFAULT LABEL`
: A label named as the element.

*properties*
: The label's properties. `PROPERTIES (name, UPPER(city) AS town)` lists columns and T-SQL expressions; an expression
  needs `AS` (error 102) and may use only pure functions (`GETDATE()`, `NEWID()`, `USER_NAME()` and the like are error
  50000); a property twice in a label is error 50000. `ALL COLUMNS` is every column of the table as it is now, `EXCEPT`
  leaves some out, and `NO PROPERTIES` gives none. Without a properties clause a label has all columns.

Without any `LABEL`, an element has the default label (its own name), with the properties given or all columns.

## Remarks

- A label may be on several elements, and then it has the same property names on each (error 2714), each of one kind of
  type: an `int` on one and `nvarchar` on another is error 50000 (`int` and `decimal` agree). A pattern `(x IS entity)`
  then matches the rows of all of them (example E).
- The statement ends after `VERTEX`/`NODE TABLES (...)` and the optional `EDGE`/`RELATIONSHIP TABLES (...)`, so no `;`
  is needed between statements in a T-SQL batch.
- The graph keeps names: the tables are not changed, and [GRAPH_TABLE](graph-table.md) reads their rows as they are
  when it runs. A column added after `CREATE` is no property, even under `ALL COLUMNS`.
- A table the graph uses can be dropped or renamed, and a column it names dropped or renamed. The graph stays, and
  `GRAPH_TABLE` over it fails (error 208 for a missing table, error 207 for a missing column) until a table and columns
  of those names are there again.
- Local variables (`@x`) are not allowed in `CREATE PROPERTY GRAPH` (error 137).
- A replica refuses the statement (error 3906); it has the primary's graphs.
- A graph created here can also be queried or dropped from the PostgreSQL and Oracle doors (and vice versa).
- A graph is dropped with [DROP PROPERTY GRAPH](drop-property-graph.md).

## Differences from SQL Server and the standard

- SQL Server has its own graph table extensions (`CREATE TABLE ... AS NODE` / `AS EDGE` and `MATCH (a-(e)->b)` in
  `WHERE`); lexdb implements the SQL:2023 standard SQL/PGQ (`CREATE PROPERTY GRAPH` and `GRAPH_TABLE`) instead.
- There is no `ALTER PROPERTY GRAPH`, no `sys.objects` row for a property graph, and no separate `GRANT` on a property
  graph: `GRAPH_TABLE` reads the underlying tables with the session's own table permissions.
- The [PostgreSQL](../postgresql/create-property-graph.md) and [Oracle](../oracle/create-property-graph.md) doors have
  the same statement.

## Examples

<!--setup: tsql
CREATE TABLE dbo.people (id int PRIMARY KEY, name nvarchar(30), city nvarchar(30));
CREATE TABLE dbo.companies (id int PRIMARY KEY, name nvarchar(30), city nvarchar(30));
CREATE TABLE dbo.knows (id int PRIMARY KEY, src int REFERENCES dbo.people (id), dst int REFERENCES dbo.people (id), since int);
CREATE TABLE dbo.works_at (pid int REFERENCES dbo.people (id), cid int REFERENCES dbo.companies (id), role nvarchar(20), PRIMARY KEY (pid, cid));
INSERT dbo.people VALUES (1, N'Ann', N'Oslo'), (2, N'Bob', N'Rome'), (3, N'Cid', N'Oslo'), (4, N'Dee', N'Pisa');
INSERT dbo.companies VALUES (10, N'Acme', N'Oslo'), (11, N'Bolt', N'Rome');
INSERT dbo.knows VALUES (100, 1, 2, 2010), (101, 2, 3, 2012), (102, 3, 4, 2015), (103, 1, 3, 2018);
INSERT dbo.works_at VALUES (1, 10, N'dev'), (2, 10, N'ops'), (3, 11, N'dev');
-->

The examples use four tables: people, companies, who knows whom, and who works where.

```sql
CREATE TABLE dbo.people (id int PRIMARY KEY, name nvarchar(30), city nvarchar(30));
CREATE TABLE dbo.companies (id int PRIMARY KEY, name nvarchar(30), city nvarchar(30));
CREATE TABLE dbo.knows (id int PRIMARY KEY, src int REFERENCES dbo.people (id), dst int REFERENCES dbo.people (id), since int);
CREATE TABLE dbo.works_at (pid int REFERENCES dbo.people (id), cid int REFERENCES dbo.companies (id), role nvarchar(20), PRIMARY KEY (pid, cid));
INSERT dbo.people VALUES (1, N'Ann', N'Oslo'), (2, N'Bob', N'Rome'), (3, N'Cid', N'Oslo'), (4, N'Dee', N'Pisa');
INSERT dbo.companies VALUES (10, N'Acme', N'Oslo'), (11, N'Bolt', N'Rome');
INSERT dbo.knows VALUES (100, 1, 2, 2010), (101, 2, 3, 2012), (102, 3, 4, 2015), (103, 1, 3, 2018);
INSERT dbo.works_at VALUES (1, 10, N'dev'), (2, 10, N'ops'), (3, 11, N'dev');
```

### A. Vertices, edges, labels and computed properties

<!-- example: tsql -->
```sql
CREATE PROPERTY GRAPH dbo.social
  VERTEX TABLES (
    dbo.people KEY (id)
      LABEL person PROPERTIES (id, name, UPPER(city) AS town),
    dbo.companies KEY (id)
      LABEL company PROPERTIES (id, name, city)
  )
  EDGE TABLES (
    dbo.knows
      SOURCE KEY (src) REFERENCES people (id)
      DESTINATION KEY (dst) REFERENCES people (id)
      LABEL knows PROPERTIES (since),
    dbo.works_at
      SOURCE KEY (pid) REFERENCES people (id)
      DESTINATION KEY (cid) REFERENCES companies (id)
      LABEL works_at PROPERTIES (role)
  );
GO
SELECT * FROM GRAPH_TABLE (dbo.social
  MATCH (p IS person) -[w IS works_at]-> (c IS company)
  COLUMNS (p.name AS person, p.town, c.name AS company, w.role)
) ORDER BY person;
```

```text
person town company role
------ ---- ------- ----
Ann    OSLO Acme    dev
Bob    ROME Acme    ops
Cid    OSLO Bolt    dev

(3 rows affected)
```

### B. Defaults: primary keys, foreign keys and `NODE` / `RELATIONSHIP` synonyms

`works_at` has one foreign key to `people` and one to `companies`, so `SOURCE` and `DESTINATION` need only the vertex
element names. `NODE TABLES` and `RELATIONSHIP TABLES` are SQL:2023 synonyms for `VERTEX TABLES` and `EDGE TABLES`.

<!-- example: tsql -->
```sql
CREATE PROPERTY GRAPH dbo.staff
  NODE TABLES (dbo.people, dbo.companies)
  RELATIONSHIP TABLES (dbo.works_at SOURCE people DESTINATION companies)
SELECT * FROM GRAPH_TABLE (dbo.staff
  MATCH (p IS people) -[w IS works_at]-> (c IS companies)
  COLUMNS (p.name AS person, c.name AS company, w.role)
) ORDER BY person;
```

```text
person company role
------ ------- ----
Ann    Acme    dev
Bob    Acme    ops
Cid    Bolt    dev

(3 rows affected)
```

### C. `OR ALTER`, `ALL COLUMNS EXCEPT` and `NO PROPERTIES`

<!-- example: tsql -->
```sql
CREATE OR ALTER PROPERTY GRAPH dbo.staff
  VERTEX TABLES (
    dbo.people PROPERTIES ARE ALL COLUMNS EXCEPT (city),
    dbo.companies DEFAULT LABEL PROPERTIES (id, name)
  )
  EDGE TABLES (
    dbo.works_at SOURCE people DESTINATION companies NO PROPERTIES
  );
GO
SELECT * FROM GRAPH_TABLE (dbo.staff
  MATCH (p IS people) -[w IS works_at]-> (c IS companies)
  COLUMNS (p.name AS person, c.name AS company)
) ORDER BY person;
```

```text
person company
------ -------
Ann    Acme
Bob    Acme
Cid    Bolt

(3 rows affected)
```

### D. `IF NOT EXISTS` and namespace collisions

<!-- example: tsql -->
```sql
CREATE PROPERTY GRAPH IF NOT EXISTS dbo.staff VERTEX TABLES (dbo.companies);
GO
CREATE PROPERTY GRAPH dbo.staff VERTEX TABLES (dbo.companies);
GO
CREATE PROPERTY GRAPH dbo.people VERTEX TABLES (dbo.companies);
```

```text
Msg 2714, Level 16, State 1, Line 1
There is already an object named 'staff' in the database.
Msg 2714, Level 16, State 1, Line 1
There is already an object named 'people' in the database.
```

### E. One label on two vertex tables

<!-- example: tsql -->
```sql
CREATE PROPERTY GRAPH dbo.named
  VERTEX TABLES (
    dbo.people LABEL entity PROPERTIES (id, name),
    dbo.companies LABEL entity PROPERTIES (id, name)
  );
GO
SELECT * FROM GRAPH_TABLE (dbo.named MATCH (x IS entity) COLUMNS (x.id, x.name)) ORDER BY id;
GO
CREATE PROPERTY GRAPH dbo.bad
  VERTEX TABLES (dbo.people LABEL entity PROPERTIES (id), dbo.companies LABEL entity PROPERTIES (id, name));
GO
CREATE PROPERTY GRAPH dbo.bad
  VERTEX TABLES (dbo.people LABEL entity PROPERTIES (id AS v), dbo.companies LABEL entity PROPERTIES (name AS v));
```

```text
id name
-- ----
1  Ann
2  Bob
3  Cid
4  Dee
10 Acme
11 Bolt

(6 rows affected)

Msg 2714, Level 16, State 1, Line 1
label entity already defined
Msg 50000, Level 16, State 1, Line 1
cannot use mixed type for property v of label entity
```

## See also

[GRAPH_TABLE](graph-table.md) · [DROP PROPERTY GRAPH](drop-property-graph.md) · [SELECT](select.md) ·
[FROM, JOIN and APPLY](from.md) · [CREATE VIEW](create-view.md)
