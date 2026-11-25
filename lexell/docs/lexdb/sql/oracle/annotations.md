# Annotations

Keeps names, with or without a value, on a table, a view, an index or one of their columns, for tools and programs
to read from the data dictionary. lexdb itself does nothing with them.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
annotations_clause:
    ANNOTATIONS ( annotation [, annotation ]... )

annotation:
    [ ADD [ IF NOT EXISTS ] | DROP [ IF EXISTS ] | REPLACE ] name [ 'value' ]
```

Where the clause goes:

```
CREATE [ GLOBAL TEMPORARY ] TABLE table
    ( column datatype [ DEFAULT expr ] [ column_constraint ]... [ annotations_clause ], ... )
    [ ON COMMIT { DELETE | PRESERVE } ROWS ] [ annotations_clause ]
CREATE TABLE table [ ( column [, column ]... ) ] [ annotations_clause ] AS subquery

CREATE [ OR REPLACE ] VIEW view [ ( alias [ annotations_clause ] [, ...] ) ] [ annotations_clause ] AS subquery

CREATE [ UNIQUE ] INDEX index ON table ( key [, key ]... ) [ annotations_clause ]

ALTER TABLE table annotations_clause
ALTER TABLE table MODIFY ( column [ datatype ] [ NOT NULL | NULL ] annotations_clause [, ...] )
ALTER TABLE table ADD ( column datatype ... [ annotations_clause ] [, ...] )
ALTER VIEW view annotations_clause
ALTER VIEW view MODIFY ( column annotations_clause [, ...] )
ALTER INDEX index annotations_clause
```

## Arguments

*name*
: An identifier, up to 1,024 characters (ORA-00972 beyond). Unquoted it is folded to upper case (`Display` is
  `DISPLAY`); quoted it is kept as written (`"Display"`). A keyword that is not one of Oracle's reserved words is a
  name (`KEY`, `VALUE`, `TYPE`, `IF`); a reserved word (`SELECT`, `TABLE`, `NUMBER`, `LONG`) is ORA-11548. `""` is
  ORA-01741.

*value*
: A text literal of up to 4,000 characters (ORA-11545 beyond). Without one the annotation is a flag (`Hidden`), and
  its `ANNOTATION_VALUE` is NULL. An empty value (`''`), `NULL` or a number is ORA-11549.

`ADD`
: Adds the name with that value. A bare *name* in a list means `ADD`. A name may have several values: `ADD Tag 'c'`
  to a table that has `Tag 'a'` gives it both. Adding a name and value that the object has already is ORA-11552
  (ORA-11560 for a column).

`ADD IF NOT EXISTS`
: As `ADD`, but a name and value that are there already are skipped.

`DROP`
: `DROP name` drops every value of the name, `DROP name 'value'` that one. A name, or a name and value, that is not
  there is ORA-11553 (ORA-11561 for a column).

`DROP IF EXISTS`
: As `DROP`, but nothing happens when it is not there.

`REPLACE`
: Makes the name's values the one given (or the flag). A name that is not there is ORA-11553 (ORA-11561 for a
  column).

## Remarks

- In `CREATE` statements only `ADD` is allowed (with or without the word): `DROP` is ORA-11555, `REPLACE`
  ORA-11556.
- Annotations are told apart by name **and value**: `Tag 'a', Tag 'b'` is two annotations, while `Tag 'a', Tag 'a'`
  (and `Hidden, Hidden`) in one list is ORA-11562. In `ALTER`, a name that a list drops or replaces may not appear
  again in that list (ORA-11602). The list is checked first, then each item in order against the annotations the
  object had before the statement; when one fails the statement changes nothing.
- A column's `ANNOTATIONS` clause is the last part of its definition: a `NOT NULL`, `DEFAULT` or constraint after it
  is ORA-03099 (ORA-03076 when a constraint comes before it), anything else ORA-03062.
- `ALTER TABLE ... MODIFY` of a column that does not exist is ORA-00904; `ALTER TABLE` of a table that does not
  exist ORA-00942.
- The annotations go with the object: `DROP TABLE` drops a table's, its columns' and its indexes', `DROP COLUMN` and
  `DROP INDEX` theirs, and `RENAME`, `RENAME COLUMN` and `ALTER INDEX ... RENAME TO` keep them under the new name.
  `CREATE OR REPLACE VIEW` gives the view the annotations of the new statement only. A primary key's index takes
  annotations through `ALTER INDEX`, by the key's index name.
- As every DDL statement, an annotation statement commits the open transaction, also when it fails.
- The data dictionary shows them in `USER_ANNOTATIONS_USAGE` (each object or column and its annotations:
  `OBJECT_NAME`, `OBJECT_TYPE` `TABLE`, `VIEW` or `INDEX`, `COLUMN_NAME` NULL for the object's own,
  `ANNOTATION_NAME`, `ANNOTATION_VALUE`), `USER_ANNOTATIONS` (the names in use) and `USER_ANNOTATION_VALUES` (the
  names and values in use), and their `ALL_` and `DBA_` forms, which add `ANNOTATION_OWNER`. See [the data
  dictionary](data-dictionary-tables.md).
- The PostgreSQL and SQL Server doors have no annotations: `ANNOTATIONS` there is a syntax error.

## Differences from Oracle

- **A column's annotations in `CREATE TABLE ... AS`** (`CREATE TABLE c (id ANNOTATIONS (...), name) AS ...`) are
  ORA-00900; Oracle gives ORA-11559 (`Column level annotations not allowed in CREATE TABLE AS SELECT statements`).
  The table's own clause works there.
- **One column twice in `MODIFY`** (`MODIFY (price ANNOTATIONS (...), price ANNOTATIONS (...))`) applies both; Oracle
  refuses it with ORA-00957.
- **`ALTER INDEX` of an index that does not exist** is ORA-00942; Oracle gives ORA-01418.
- **`ALTER TABLE` of a view, or `ALTER VIEW` of a table,** is ORA-20000; Oracle gives ORA-00942.
- **No domains:** `ALL_` and `DBA_ANNOTATIONS_USAGE` have no rows for the built-in domains of `SYS` (Oracle Free lists
  about a hundred, `OBJECT_TYPE` `DOMAIN`), and `DOMAIN_NAME` and `DOMAIN_OWNER` are always NULL.
- **A global temporary table's annotations** are kept but not listed in the views.

## Examples

### A. A table with table and column annotations

`Searchable` and `Audited` are flags: they have no value.

<!-- example: oracle -->
```sql
CREATE TABLE product (
  id NUMBER PRIMARY KEY ANNOTATIONS (Display 'Product id'),
  name VARCHAR2(40) NOT NULL ANNOTATIONS (Display 'Name', Searchable),
  price NUMBER(8,2) ANNOTATIONS (Display 'Price', Unit 'EUR')
) ANNOTATIONS (Owner 'sales', Audited);
SELECT object_type, object_name, column_name, annotation_name, annotation_value
FROM user_annotations_usage WHERE object_name = 'PRODUCT'
ORDER BY column_name NULLS FIRST, annotation_name;
```

```text
Table created.

OBJECT_TYPE OBJECT_NAME COLUMN_NAME ANNOTATION_NAME ANNOTATION_VALUE
----------- ----------- ----------- --------------- ----------------
TABLE       PRODUCT                 AUDITED
TABLE       PRODUCT                 OWNER           sales
TABLE       PRODUCT     ID          DISPLAY         Product id
TABLE       PRODUCT     NAME        DISPLAY         Name
TABLE       PRODUCT     NAME        SEARCHABLE
TABLE       PRODUCT     PRICE       DISPLAY         Price
TABLE       PRODUCT     PRICE       UNIT            EUR

7 rows selected.
```

### B. A view and an index

<!-- example: oracle -->
```sql
CREATE VIEW cheap (id, name ANNOTATIONS (Display 'Cheap product')) ANNOTATIONS (Purpose 'price list')
AS SELECT id, name FROM product WHERE price < 10;
CREATE INDEX product_name_ix ON product (name) ANNOTATIONS (Note 'for search');
SELECT object_type, object_name, column_name, annotation_name, annotation_value
FROM user_annotations_usage WHERE object_type IN ('VIEW', 'INDEX')
ORDER BY object_type, object_name, column_name NULLS FIRST, annotation_name;
```

```text
View created.

Index created.

OBJECT_TYPE OBJECT_NAME     COLUMN_NAME ANNOTATION_NAME ANNOTATION_VALUE
----------- --------------- ----------- --------------- ----------------
INDEX       PRODUCT_NAME_IX             NOTE            for search
VIEW        CHEAP                       PURPOSE         price list
VIEW        CHEAP           NAME        DISPLAY         Cheap product

3 rows selected.
```

### C. ADD, REPLACE and DROP

<!-- example: oracle -->
```sql
ALTER TABLE product ANNOTATIONS (ADD Reviewed '2026-11', REPLACE Owner 'marketing', DROP Audited);
ALTER TABLE product MODIFY (price ANNOTATIONS (REPLACE Unit 'USD', ADD Hidden));
ALTER TABLE product ANNOTATIONS (ADD IF NOT EXISTS Owner 'marketing', DROP IF EXISTS Nothing);
ALTER INDEX product_name_ix ANNOTATIONS (DROP Note);
ALTER VIEW cheap ANNOTATIONS (ADD Hidden);
ALTER VIEW cheap MODIFY (name ANNOTATIONS (REPLACE Display 'Name'));
SELECT object_type, object_name, column_name, annotation_name, annotation_value
FROM user_annotations_usage
ORDER BY object_type, object_name, column_name NULLS FIRST, annotation_name;
```

```text
Table altered.

Table altered.

Table altered.

Index altered.

View altered.

View altered.

OBJECT_TYPE OBJECT_NAME COLUMN_NAME ANNOTATION_NAME ANNOTATION_VALUE
----------- ----------- ----------- --------------- ----------------
TABLE       PRODUCT                 OWNER           marketing
TABLE       PRODUCT                 REVIEWED        2026-11
TABLE       PRODUCT     ID          DISPLAY         Product id
TABLE       PRODUCT     NAME        DISPLAY         Name
TABLE       PRODUCT     NAME        SEARCHABLE
TABLE       PRODUCT     PRICE       DISPLAY         Price
TABLE       PRODUCT     PRICE       HIDDEN
TABLE       PRODUCT     PRICE       UNIT            USD
VIEW        CHEAP                   HIDDEN
VIEW        CHEAP                   PURPOSE         price list
VIEW        CHEAP       NAME        DISPLAY         Name

11 rows selected.
```

### D. Several values of one name, and a rename

<!-- example: oracle -->
```sql
CREATE TABLE tag_demo (id NUMBER) ANNOTATIONS (Tag 'a', Tag 'b');
ALTER TABLE tag_demo ANNOTATIONS (ADD Tag 'c', ADD Tag);
ALTER TABLE tag_demo ANNOTATIONS (DROP Tag 'a');
SELECT annotation_name, annotation_value FROM user_annotations_usage
WHERE object_name = 'TAG_DEMO' ORDER BY annotation_value NULLS FIRST;
ALTER TABLE tag_demo ANNOTATIONS (REPLACE Tag 'z');
ALTER TABLE tag_demo ADD (note VARCHAR2(10) ANNOTATIONS (Display 'Note'));
ALTER TABLE tag_demo RENAME COLUMN note TO remark;
ALTER TABLE tag_demo RENAME TO tags;
SELECT object_name, column_name, annotation_name, annotation_value FROM user_annotations_usage
WHERE object_name IN ('TAG_DEMO', 'TAGS') ORDER BY column_name NULLS FIRST;
```

```text
Table created.

Table altered.

Table altered.

ANNOTATION_NAME ANNOTATION_VALUE
--------------- ----------------
TAG
TAG             b
TAG             c

3 rows selected.

Table altered.

Table altered.

Table altered.

Table altered.

OBJECT_NAME COLUMN_NAME ANNOTATION_NAME ANNOTATION_VALUE
----------- ----------- --------------- ----------------
TAGS                    TAG             z
TAGS        REMARK      DISPLAY         Note

2 rows selected.
```

### E. The names and values in use

<!-- example: oracle -->
```sql
SELECT * FROM user_annotations ORDER BY 1;
SELECT * FROM user_annotation_values WHERE annotation_name IN ('DISPLAY', 'TAG') ORDER BY 1, 2;
SELECT annotation_owner, COUNT(*) AS n FROM all_annotations_usage WHERE annotation_owner = USER
GROUP BY annotation_owner;
```

```text
ANNOTATION_NAME
---------------
DISPLAY
HIDDEN
OWNER
PURPOSE
REVIEWED
SEARCHABLE
TAG
UNIT

8 rows selected.

ANNOTATION_NAME ANNOTATION_VALUE
--------------- ----------------
DISPLAY         Name
DISPLAY         Note
DISPLAY         Price
DISPLAY         Product id
TAG             z

5 rows selected.

ANNOTATION_OWNER  N
---------------- --
SA               13

1 row selected.
```

### F. Errors

<!-- example: oracle -->
```sql
ALTER TABLE product ANNOTATIONS (ADD Owner 'marketing');
ALTER TABLE product ANNOTATIONS (DROP Nothing);
ALTER TABLE product MODIFY (price ANNOTATIONS (DROP Nothing));
ALTER TABLE product MODIFY (price ANNOTATIONS (ADD Unit 'USD'));
ALTER TABLE product ANNOTATIONS (ADD Tag 'x', DROP Tag);
ALTER TABLE product MODIFY (nothere ANNOTATIONS (ADD x));
CREATE TABLE bad1 (a NUMBER) ANNOTATIONS (DROP Owner);
CREATE TABLE bad2 (a NUMBER ANNOTATIONS (Unit 'x') NOT NULL);
CREATE TABLE bad3 (a NUMBER ANNOTATIONS (Unit ''));
CREATE TABLE bad4 (a NUMBER ANNOTATIONS (Unit 'x', Unit 'x'));
CREATE TABLE bad5 (a NUMBER ANNOTATIONS (Select 'x'));
```

```text
ERROR:
ORA-11552: Provided annotation 'OWNER' already exists for the object 'PRODUCT'.

ERROR:
ORA-11553: Provided annotation 'NOTHING' does not exist for the object 'PRODUCT'.

ERROR:
ORA-11561: Provided annotation 'NOTHING' does not exist for the column 'PRICE'.

ERROR:
ORA-11560: Provided annotation 'UNIT' already exists for the column 'PRICE'.

ERROR:
ORA-11602: Cannot combine ADD, DROP, REPLACE operations for the same annotation 'TAG'.

ERROR:
ORA-00904: "NOTHERE": invalid identifier

ERROR:
ORA-11555: DROP annotation is not allowed in a CREATE statement.

ERROR:
ORA-03099: unexpected item NOT in a column definition

ERROR:
ORA-11549: invalid annotation value '' in the ANNOTATIONS sequence

ERROR:
ORA-11562: Duplicate annotation 'UNIT' in the ANNOTATIONS clause.

ERROR:
ORA-11548: missing or invalid annotation name 'SELECT' in the ANNOTATIONS sequence
```

### G. Where lexdb differs

Oracle gives ORA-11559, ORA-00957 (and no annotation is added), ORA-01418, ORA-00942 and ORA-00942 for the
statements below, and counts 1 annotation on the global temporary table.

<!-- example: oracle -->
```sql
CREATE TABLE copy1 (id ANNOTATIONS (Display 'x'), name) AS SELECT id, name FROM product;
ALTER TABLE product MODIFY (price ANNOTATIONS (ADD A1), price ANNOTATIONS (ADD A2));
SELECT annotation_name FROM user_annotations_usage WHERE annotation_name IN ('A1', 'A2') ORDER BY 1;
ALTER INDEX nothere_ix ANNOTATIONS (ADD x);
ALTER TABLE cheap ANNOTATIONS (ADD x);
ALTER VIEW product ANNOTATIONS (ADD x);
CREATE GLOBAL TEMPORARY TABLE scratch (a NUMBER) ANNOTATIONS (Scratch);
SELECT COUNT(*) AS n FROM user_annotations_usage WHERE object_name = 'SCRATCH';
```

```text
ERROR:
ORA-00900: invalid SQL statement

Table altered.

ANNOTATION_NAME
---------------
A1
A2

2 rows selected.

ERROR:
ORA-00942: table or view "SA"."NOTHERE_IX" does not exist

ERROR:
ORA-20000: "cheap" is a view (use ALTER VIEW)

ERROR:
ORA-20000: "product" is not a view

Table created.

N
-
0

1 row selected.
```

## See also

[CREATE TABLE](create-table.md), [ALTER TABLE](alter-table.md), [CREATE VIEW](create-view.md),
[CREATE INDEX](create-index.md), [Data dictionary: tables, columns, indexes and
constraints](data-dictionary-tables.md)
