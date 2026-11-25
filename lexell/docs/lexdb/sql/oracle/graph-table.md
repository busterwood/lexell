# GRAPH_TABLE

Finds the vertices and edges of a property graph that match a pattern, in the `FROM` clause of a
[SELECT](select.md), and returns a row for each match (SQL/PGQ).

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai (SQL/PGQ, ISO/IEC 9075-16).

## Syntax

```
GRAPH_TABLE ( [ schema. ] graph
    MATCH path_pattern [, path_pattern ]...
    [ WHERE condition ]
    [ ONE ROW PER MATCH ]
    COLUMNS ( { expression [ AS name ] | variable.* } [, ...] )
) [ alias ]

path_pattern:
    vertex_pattern [ { edge_pattern [ quantifier ] | ( edge_pattern vertex_pattern [ ... ] ) quantifier } vertex_pattern ]...

vertex_pattern:
    ( [ variable ] [ IS label_expression ] [ WHERE condition ] )

edge_pattern:
    -[ [ variable ] [ IS label_expression ] [ WHERE condition ] ]->      source to destination
    <-[ [ variable ] [ IS label_expression ] [ WHERE condition ] ]-      destination to source
    -[ [ variable ] [ IS label_expression ] [ WHERE condition ] ]-       either way
    ->  |  <-  |  -                                                      any edge, without a variable

label_expression:
    label [ { '|' | '&' } label ]...

quantifier:
    { n } | { m, n } | { , n }
```

## Arguments

*graph*
: A property graph made by [CREATE PROPERTY GRAPH](create-property-graph.md), with its owner in front for another
  schema's (`app.social`). One that does not exist is ORA-42421.

`MATCH` *path_pattern*
: Vertices and the edges between them. A vertex pattern in brackets binds its variable to one vertex: a row of a
  vertex table of the graph. An edge pattern binds its variable to one edge, a row of an edge table, whose two ends are
  the vertices on its left and right. Several path patterns, separated by commas, are matched together: a variable
  they share is the same element in each, and patterns that share none give every combination of their matches.

*variable*
: The name the pattern's columns and conditions use for the element (`a.name`). A pattern may leave it out. The same
  variable twice in a pattern is one element: `(a) -> (b) -> (a)` is a cycle back to `a`. A vertex and an edge of the
  same name are ORA-49000.

`IS` *label_expression*
: The labels the element must have. `person|company` is either, `person&manager` both. Without `IS` the element may be
  of any table. A label the graph does not have is ORA-40954; `!` (not) is ORA-40951.

`WHERE` *condition*
: Inside a vertex or edge pattern, a condition on that element (`(a IS person WHERE a.city = 'Oslo')`); after the path
  patterns, a condition on all of them. Besides properties, it may test:
  - *variable* `IS [ NOT ] LABELED` *label*: whether the element has the label;
  - *vertex* `IS [ NOT ] SOURCE OF` *edge* and `IS [ NOT ] DESTINATION OF` *edge*: which end of the edge the vertex is,
    useful with an edge matched either way;
  - `VERTEX_ID(v) = VERTEX_ID(w)`: whether two variables are the same element.

`->`, `<-`, `-`, and the arrows around `[ ... ]`
: `-[e]->` goes from the edge's source to its destination, `<-[e]-` the other way, and `-[e]-` either way: each edge
  is matched once in each direction, so a pattern `(a) -[e]- (b)` gives both `(x, y)` and `(y, x)`. An edge from a
  vertex to itself is matched once. `->`, `<-` and `-` are the same without a variable or label: any edge.

*quantifier*
: The number of edges of a path: `{n}` exactly n, `{m,n}` from m to n, `{,n}` from 0 to n. It follows an edge pattern
  (`-[k IS knows]->{1,3}`) or a bracketed path of edges and vertices (`(-[k]-> (m)){1,2}`). Zero edges is a path from a
  vertex to itself. A path may use an edge more than once. Only bounded quantifiers exist: `+` and `*` are
  ORA-40985, `?` is ORA-49003, `{m,}`, `{0}` and `{3,1}` are ORA-40984, and a quantifier after a vertex pattern is
  ORA-40997.

`ONE ROW PER MATCH`
: The default, and the only form lexdb has: one row for each match.

`COLUMNS (` ... `)`
: The columns of the result:
  - *variable*`.`*property*, alone (the column is named after the property) or in any expression with `AS`:
    functions, `CASE`, arithmetic. An expression without `AS` is ORA-02000, and two columns of one name are ORA-00918.
  - *variable*`.*`: every property of the variable's labels, in the order the labels have them.
  - `VERTEX_ID(v)` and `EDGE_ID(e)`: the element's identity (graph, element table, key value) as JSON text.
  - `MATCHNUM()`: a number for each match, the same in all of its rows.
  - aggregates of a quantified variable: `COUNT`, `SUM`, `MIN`, `MAX`, `AVG` and `LISTAGG(x [, separator])` over
    the elements of the path, in its order (`COUNT(k.since)` is the path's length, `LISTAGG(m.name, ',')` the
    vertices it passes).

*alias*
: A name for the result, as for an inline view (`... ) g`). `AS` before it is ORA-03048, as for a table alias.

## Remarks

- A variable reads the properties of its labels. Without `IS`, or with `|`, it may be bound to elements of several
  tables: it reads the properties of all their labels, and a property the bound element's labels do not have is NULL
  (`e.since` of a `works_at` edge, example D). A property no label of the graph has is ORA-40983, one that the
  variable's labels do not have ORA-49044, and a label expression no element satisfies ORA-49013.
- A quantified edge's variable stands for several edges: it may be used only inside an aggregate in `COLUMNS`
  (ORA-40990 elsewhere in `COLUMNS`, ORA-40998 in the pattern's `WHERE`), and an aggregate must have one (ORA-49011,
  `COUNT(*)` too). `COUNT(e)` without a property is ORA-40956.
- No subquery inside `GRAPH_TABLE` (ORA-40988), and no column of the query around it (ORA-40996): join the result
  instead (example J).
- Bind variables work in the conditions and `COLUMNS`, as in any query: `WHERE a.name = :who`. A PL/SQL variable
  inside `GRAPH_TABLE` is refused when the block compiles, ORA-49028, as in Oracle; pass its value as a bind with
  `EXECUTE IMMEDIATE ... USING` (example M).
- `GRAPH_TABLE` is a table reference. It may be joined with tables, used in a subquery, an `IN` list, a `WITH` query
  and a view, and its rows grouped, ordered and filtered as any others. The rows come in no particular order: use
  `ORDER BY`.
- lexdb writes `GRAPH_TABLE` as SQL before it is planned: the joins of the element tables on the graph's keys, one
  for each way the pattern's variables can be bound to tables and each length of its quantifiers, and the `UNION ALL`
  of them, planned as any other query. A query of `GRAPH_TABLE` alone costs what the hand-written join does.
- The tables are read with the session's privileges.
- A graph whose table, or a column it names, has been dropped or renamed is ORA-04045 until a table and columns of
  those names are there again (see [CREATE PROPERTY GRAPH](create-property-graph.md)).
- Names without quotes are folded to upper case. A quoted graph name and a quoted label are exact, as in Oracle:
  `GRAPH_TABLE (mixg ...)` is ORA-42421 for a graph `"MixG"`, and `IS "person"` is not
  `PERSON` (ORA-40954).

## Differences from Oracle

- `ONE ROW PER VERTEX` and `ONE ROW PER STEP`, and so `ELEMENT_NUMBER`, are not supported (ORA-03001). Without them
  `ELEMENT_NUMBER` is ORA-49033, as in Oracle.
- `LISTAGG ... WITHIN GROUP (ORDER BY ...)` and `DISTINCT` in an aggregate of a quantified variable are ORA-03001.
- A pattern that would need more than 4,096 joins (the lengths of its quantifiers multiplied by the tables its
  variables may be bound to) is refused (ORA-03001). Oracle runs out of memory on such a pattern (ORA-04036 at
  `{1,5000}`).
- `VERTEX_ID` and `EDGE_ID` give the JSON text as a character value, not as the `JSON` type: a table made from them with
  `CREATE TABLE ... AS SELECT` has a `CLOB` column (Oracle: `JSON`). `JSON_VALUE`, `JSON_SERIALIZE` and the other
  [JSON functions](functions-json.md) read them (`JSON_VALUE(vp, '$.KEY_VALUE.ID')`).
- `MATCHNUM()` numbers the matches one each, as Oracle does, but the numbers are lexdb's own: a match does not have
  Oracle's number.
- The [PostgreSQL](../postgresql/graph-table.md) and [SQL Server](../tsql/graph-table.md) doors also support `GRAPH_TABLE`.

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
-->

The examples use four tables and a graph over them: people who know each other, and the companies they work at.

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
INSERT INTO knows VALUES (100, 1, 2, 2010);    -- Ann knows Bob
INSERT INTO knows VALUES (101, 2, 3, 2012);    -- Bob knows Cid
INSERT INTO knows VALUES (102, 3, 4, 2015);    -- Cid knows Dee
INSERT INTO knows VALUES (103, 1, 3, 2018);    -- Ann knows Cid
INSERT INTO works_at VALUES (1, 10, 'dev');
INSERT INTO works_at VALUES (2, 10, 'ops');
INSERT INTO works_at VALUES (3, 11, 'dev');
COMMIT;
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
```

### A. One hop

Who knows whom, and since when:

<!-- example: oracle -->
```sql
SELECT * FROM GRAPH_TABLE (social
  MATCH (a IS person) -[k IS knows]-> (b IS person)
  COLUMNS (a.name AS who, b.name AS knows_whom, k.since AS since)
) ORDER BY 1, 2;
```

```text
WHO KNOWS_WHOM SINCE
--- ---------- -----
Ann Bob         2010
Ann Cid         2018
Bob Cid         2012
Cid Dee         2015

4 rows selected.
```

### B. Two hops

The people Ann knows through someone she knows. The middle edge patterns have no variable:

<!-- example: oracle -->
```sql
SELECT * FROM GRAPH_TABLE (social
  MATCH (a IS person WHERE a.name = 'Ann') -[IS knows]-> (b IS person) -[IS knows]-> (c IS person)
  COLUMNS (b.name AS via, c.name AS reached)
) ORDER BY 1, 2;
```

```text
VIA REACHED
--- -------
Bob Cid
Cid Dee

2 rows selected.
```

### C. An edge either way

`-[k]-` matches an edge in both directions: the people Cid knows and the people who know Cid. `IS SOURCE OF` tells
which way the edge goes:

<!-- example: oracle -->
```sql
SELECT * FROM GRAPH_TABLE (social
  MATCH (a IS person WHERE a.name = 'Cid') -[k IS knows]- (b IS person)
  COLUMNS (b.name AS friend, k.since AS since,
           CASE WHEN a IS SOURCE OF k THEN 'out' ELSE 'in' END AS dir)
) ORDER BY 1;
SELECT * FROM GRAPH_TABLE (social
  MATCH (a IS person WHERE a.name = 'Cid') <- (b)
  COLUMNS (b.name AS known_by)
) ORDER BY 1;
```

```text
FRIEND SINCE DIR
------ ----- ---
Ann     2018 in
Bob     2012 in
Dee     2015 out

3 rows selected.

KNOWN_BY
--------
Ann
Bob

2 rows selected.
```

### D. Any edge, and a label disjunction on an edge

`->` is any edge. With `IS knows|works_at` the variable reads both labels' properties; a property the edge's label
does not have is NULL:

<!-- example: oracle -->
```sql
SELECT * FROM GRAPH_TABLE (social
  MATCH (a WHERE a.name = 'Ann') -> (b)
  COLUMNS (b.name AS reached)
) ORDER BY 1;
SELECT * FROM GRAPH_TABLE (social
  MATCH (a IS person WHERE a.name = 'Ann') -[e IS knows|works_at]-> (b)
  COLUMNS (b.name AS reached, e.since AS since, e.role AS role)
) ORDER BY 1;
```

```text
REACHED
-------
Acme
Bob
Cid

3 rows selected.

REACHED SINCE ROLE
------- ----- ----
Acme          dev
Bob      2010
Cid      2018

3 rows selected.
```

### E. A label disjunction on a vertex

Everything in Oslo, person or company:

<!-- example: oracle -->
```sql
SELECT * FROM GRAPH_TABLE (social
  MATCH (x IS person|company)
  WHERE x.city = 'Oslo'
  COLUMNS (x.name AS name, CASE WHEN x IS LABELED company THEN 'company' ELSE 'person' END AS kind)
) ORDER BY 1;
```

```text
NAME KIND
---- -------
Acme company
Ann  person
Cid  person

3 rows selected.
```

### F. A path of one to three edges

`{1,3}` matches paths of one, two and three `knows` edges. `k` stands for the path's edges, so it is read through
aggregates: `COUNT` is the number of edges and `LISTAGG` the years, in the path's order:

<!-- example: oracle -->
```sql
SELECT * FROM GRAPH_TABLE (social
  MATCH (a IS person WHERE a.name = 'Ann') -[k IS knows]->{1,3} (b IS person)
  COLUMNS (b.name AS reached, COUNT(k.since) AS hops, LISTAGG(k.since, ',') AS years, MIN(k.since) AS first)
) ORDER BY 2, 1;
```

```text
REACHED HOPS YEARS          FIRST
------- ---- -------------- -----
Bob        1 2010            2010
Cid        1 2018            2018
Cid        2 2010,2012       2010
Dee        2 2018,2015       2015
Dee        3 2010,2012,2015  2010

5 rows selected.
```

### G. A quantified path of edges and vertices

A bracketed path repeats an edge and a vertex. The companies within two acquaintances of Ann, and the people on the
way:

<!-- example: oracle -->
```sql
SELECT * FROM GRAPH_TABLE (social
  MATCH (a IS person WHERE a.name = 'Ann') (-[k IS knows]-> (m IS person)){1,2} -[IS works_at]-> (c IS company)
  COLUMNS (c.name AS company, COUNT(k.since) AS hops, LISTAGG(m.name, ',') AS via)
) ORDER BY 2, 1;
SELECT * FROM GRAPH_TABLE (social
  MATCH (a IS person WHERE a.name = 'Dee') -[k IS knows]->{,1} (b IS person)
  COLUMNS (a.name AS a, b.name AS b, COUNT(k.since) AS hops)
);
```

```text
COMPANY HOPS VIA
------- ---- -------
Acme       1 Bob
Bolt       1 Cid
Bolt       2 Bob,Cid

3 rows selected.

A   B   HOPS
--- --- ----
Dee Dee    0

1 row selected.
```

Dee knows nobody, so the only path is the one of no edges, from Dee to Dee.

### H. Two path patterns that share a vertex

`b` is the same person in both patterns: who knows someone who works at a company, and where:

<!-- example: oracle -->
```sql
SELECT * FROM GRAPH_TABLE (social
  MATCH (a IS person) -[IS knows]-> (b IS person),
        (b) -[w IS works_at]-> (c IS company)
  COLUMNS (a.name AS who, b.name AS knows_whom, c.name AS works_at, w.role AS role)
) ORDER BY 1, 2;
```

```text
WHO KNOWS_WHOM WORKS_AT ROLE
--- ---------- -------- ----
Ann Bob        Acme     ops
Ann Cid        Bolt     dev
Bob Cid        Bolt     dev

3 rows selected.
```

### I. All properties, VERTEX_ID, EDGE_ID and MATCHNUM

<!-- example: oracle -->
```sql
SELECT * FROM GRAPH_TABLE (social MATCH (c IS company) COLUMNS (c.*)) ORDER BY 1;
SELECT * FROM GRAPH_TABLE (social
  MATCH (a IS person WHERE a.id = 1) -[w IS works_at]-> (c)
  COLUMNS (VERTEX_ID(c) AS vertex, EDGE_ID(w) AS edge)
);
SELECT COUNT(*) AS rows_, COUNT(DISTINCT m) AS matches FROM GRAPH_TABLE (social
  MATCH (a) -[e]- (b)
  COLUMNS (MATCHNUM() AS m)
);
```

```text
ID NAME CITY
-- ---- ----
10 Acme Oslo
11 Bolt Rome

2 rows selected.

VERTEX                                                                                    EDGE
----------------------------------------------------------------------------------------- -------------------------------------------------------------------------------------------------
{"GRAPH_OWNER":"SA","GRAPH_NAME":"SOCIAL","ELEM_TABLE":"COMPANIES","KEY_VALUE":{"ID":10}} {"GRAPH_OWNER":"SA","GRAPH_NAME":"SOCIAL","ELEM_TABLE":"WORKS_AT","KEY_VALUE":{"PID":1,"CID":10}}

1 row selected.

ROWS_ MATCHES
----- -------
   14      14

1 row selected.
```

### J. GRAPH_TABLE with tables, in a WITH query and in a view

A graph's rows join a table as an inline view's do. A column of a table outside cannot be used inside the
`GRAPH_TABLE`: join the result on it.

<!-- example: oracle -->
```sql
SELECT g.who, g.company, c.city
FROM GRAPH_TABLE (social
       MATCH (p IS person) -[IS works_at]-> (x IS company)
       COLUMNS (p.name AS who, x.id AS cid, x.name AS company)) g
JOIN companies c ON c.id = g.cid
WHERE c.city <> 'Rome'
ORDER BY 1;
WITH f AS (
  SELECT * FROM GRAPH_TABLE (social MATCH (a IS person) -[IS knows]- (b IS person)
                             COLUMNS (a.name AS name, b.name AS friend))
)
SELECT name, COUNT(*) AS friends FROM f GROUP BY name ORDER BY 1;
CREATE VIEW friends AS
  SELECT * FROM GRAPH_TABLE (social MATCH (a IS person) -[IS knows]- (b IS person)
                             COLUMNS (a.name AS name, b.name AS friend));
SELECT friend FROM friends WHERE name = 'Bob' ORDER BY 1;
SELECT name FROM people
WHERE id IN (SELECT bid FROM GRAPH_TABLE (social MATCH (a IS person WHERE a.name = 'Ann') -> (b IS person)
                                          COLUMNS (b.id AS bid)))
ORDER BY 1;
```

```text
WHO COMPANY CITY
--- ------- ----
Ann Acme    Oslo
Bob Acme    Oslo

2 rows selected.

NAME FRIENDS
---- -------
Ann        2
Bob        2
Cid        3
Dee        1

4 rows selected.

View created.

FRIEND
------
Ann
Cid

2 rows selected.

NAME
----
Bob
Cid

2 rows selected.
```

### K. Errors

<!-- example: oracle -->
```sql
SELECT * FROM GRAPH_TABLE (nosuch MATCH (a) COLUMNS (a.name AS n));
SELECT * FROM GRAPH_TABLE (social MATCH (a IS employee) COLUMNS (a.name AS n));
SELECT * FROM GRAPH_TABLE (social MATCH (a IS person) -[k IS knows]->* (b) COLUMNS (a.name AS n));
SELECT * FROM GRAPH_TABLE (social MATCH (a IS person) -[k IS knows]->{3,1} (b) COLUMNS (a.name AS n));
SELECT * FROM GRAPH_TABLE (social MATCH (a IS person) -[k IS knows]->{1,} (b) COLUMNS (a.name AS n));
SELECT * FROM GRAPH_TABLE (social MATCH (a IS person) -[k IS knows]->{1,2} (b) COLUMNS (a.name AS n, k.since AS s));
SELECT * FROM GRAPH_TABLE (social MATCH (a IS person) -[k IS knows]->{1,2} (b) WHERE k.since > 2010 COLUMNS (a.name AS n));
SELECT * FROM GRAPH_TABLE (social MATCH (a IS person) -[k IS knows]-> (b) COLUMNS (a.name AS n, SUM(k.since) AS s));
SELECT * FROM GRAPH_TABLE (social MATCH (a IS company) COLUMNS (a.nosuch AS s));
SELECT * FROM GRAPH_TABLE (social MATCH (a IS person) -[w IS works_at]-> (b) COLUMNS (w.since AS s));
SELECT * FROM GRAPH_TABLE (social MATCH (a IS person) -[w IS works_at]-> (c) COLUMNS (w.city AS c));
SELECT * FROM GRAPH_TABLE (social MATCH (a IS person) COLUMNS (a.name || '!'));
SELECT * FROM GRAPH_TABLE (social MATCH (a IS person) COLUMNS (a.name AS n, (SELECT COUNT(*) FROM companies) AS c));
SELECT COUNT(*) FROM people p, GRAPH_TABLE (social MATCH (a IS person) WHERE a.id = p.id COLUMNS (a.name AS n));
```

```text
ERROR:
ORA-42421: property graph does not exist

ERROR:
ORA-40954: unknown label

ERROR:
ORA-40985: unsupported quantifier for variable path pattern in a GRAPH_TABLE operator

ERROR:
ORA-40984: invalid value specified for bounded quantifier in a GRAPH_TABLE operator

ERROR:
ORA-40984: invalid value specified for bounded quantifier in a GRAPH_TABLE operator

ERROR:
ORA-40990: invalid reference of group variable K in the COLUMNS clause of a GRAPH_TABLE operator

ERROR:
ORA-40998: invalid reference of group variable K in the WHERE clause of a GRAPH_TABLE operator

ERROR:
ORA-49011: A group function inside GRAPH_TABLE() must have a group reference.

ERROR:
ORA-40983: property "NOSUCH" is never defined

ERROR:
ORA-49044: Property "SINCE" is never defined when evaluating the label expression for element variable "W".

ERROR:
ORA-40983: property "CITY" is never defined

ERROR:
ORA-02000: missing AS keyword

ERROR:
ORA-40988: Subquery is not allowed in a GRAPH_TABLE operator.

ERROR:
ORA-40996: Variable P is not declared in the MATCH clause of a GRAPH_TABLE operator.
```

### L. Where lexdb differs

<!-- example: oracle -->
```sql
SELECT * FROM GRAPH_TABLE (social MATCH (a) -[e]-> (b) ONE ROW PER VERTEX (v) COLUMNS (v.name AS n));
SELECT * FROM GRAPH_TABLE (social
  MATCH (a IS person WHERE a.name = 'Ann') -[k IS knows]->{1,2} (b)
  COLUMNS (LISTAGG(k.since, ',') WITHIN GROUP (ORDER BY k.since) AS years));
```

```text
ERROR:
ORA-03001: unimplemented feature: lexdb: GRAPH_TABLE's ONE ROW PER VERTEX and ONE ROW PER STEP are not supported (ONE ROW PER MATCH is)

ERROR:
ORA-03001: unimplemented feature: lexdb: WITHIN GROUP and OVER after an aggregate of GRAPH_TABLE are not supported
```

Oracle gives ORA-03001 for neither: it returns the rows.

### M. A PL/SQL variable

A PL/SQL variable inside `GRAPH_TABLE` is ORA-49028 when the block compiles. A bind passes the value: dynamic SQL with
`USING`.

<!-- example: oracle -->
```sql
DECLARE
  v_name VARCHAR2(20) := 'Bob';
  n NUMBER;
BEGIN
  SELECT COUNT(*) INTO n FROM GRAPH_TABLE (social
    MATCH (a IS person) -[IS knows]- (b IS person) WHERE a.name = v_name COLUMNS (b.id AS id));
  DBMS_OUTPUT.PUT_LINE(v_name || ' knows ' || n);
END;
/
DECLARE
  v_name VARCHAR2(20) := 'Bob';
  n NUMBER;
BEGIN
  EXECUTE IMMEDIATE 'SELECT COUNT(*) FROM GRAPH_TABLE (social
    MATCH (a IS person) -[IS knows]- (b IS person) WHERE a.name = :who COLUMNS (b.id AS id))' INTO n USING v_name;
  DBMS_OUTPUT.PUT_LINE(v_name || ' knows ' || n);
END;
/
```

```text
ERROR:
ORA-06550: line 6, column 67:
PL/SQL: ORA-49028: The PL/SQL variable "V_NAME" is referenced inside a GRAPH_TABLE operator.
ORA-06550: line 5, column 3:
PL/SQL: SQL Statement ignored

Bob knows 2

PL/SQL procedure successfully completed.
```

## See also

[CREATE PROPERTY GRAPH](create-property-graph.md) · [DROP PROPERTY GRAPH](drop-property-graph.md) ·
[SELECT](select.md) · [Joins](select-join.md) · [MATCH_RECOGNIZE](match-recognize.md) ·
[Data dictionary](data-dictionary-tables.md)
