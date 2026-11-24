# VALUES

A table of rows written out in the statement.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
VALUES ( expression [, ...] ) [, ...]
    [ ORDER BY sort_expression [ ASC | DESC ] [ NULLS { FIRST | LAST } ] [, ...] ]
    [ LIMIT { count | ALL } ]
    [ OFFSET start [ ROW | ROWS ] ]
    [ FETCH { FIRST | NEXT } [ count ] { ROW | ROWS } ONLY ]
```

## Arguments

*expression*
: A value of a row. Every row has the same number of values.

`ORDER BY`, `LIMIT`, `OFFSET`, `FETCH`
: As in [SELECT](select.md). The columns are named `column1`, `column2` and so on, and may be ordered by those
  names or by position.

## Remarks

- `VALUES` is a statement of its own, the rows of an [INSERT](insert.md), a `FROM` item in parentheses with an alias
  (`(VALUES ...) AS v(a, b)`), a `WITH` query, or one side of a `UNION`.
- Each column's type is the common type of its values. A string literal in a column of numbers is read as a number,
  so `VALUES (1), ('x')` is 22P02; a column of values with no common type is 42804.
- In `FROM`, a column alias list names the columns: `(VALUES (1, 'a')) AS v(n, letter)`.

## Differences from PostgreSQL

- `VALUES` after `WITH` (`WITH t AS (...) VALUES ...`) is a syntax error; `WITH t AS (...) SELECT * FROM (VALUES
  ...) AS v` works.

## Examples

### A. A VALUES statement

<!-- example: postgresql -->
```sql
VALUES (1, 'one'), (2, 'two');
VALUES (3), (1), (2) ORDER BY 1 LIMIT 2;
```

```text
 column1 | column2
---------+---------
       1 | one
       2 | two
(2 rows)

 column1
---------
       1
       2
(2 rows)
```

### B. In FROM, with names

<!-- example: postgresql -->
```sql
SELECT n, word, n * 10 AS tens FROM (VALUES (1, 'one'), (2, 'two'), (3, NULL)) AS v(n, word) ORDER BY n;
```

```text
 n | word | tens
---+------+------
 1 | one  |   10
 2 | two  |   20
 3 |      |   30
(3 rows)
```

### C. Joining a list of values to a table

<!-- example: postgresql -->
```sql
CREATE TABLE price (item text PRIMARY KEY, cost numeric(6,2));
INSERT INTO price VALUES ('pen', 1.20), ('ink', 3.50), ('pad', 2.00);
SELECT o.item, o.qty, o.qty * p.cost AS total
FROM (VALUES ('pen', 3), ('pad', 2)) AS o(item, qty) JOIN price p USING (item)
ORDER BY o.item;
```

```text
CREATE TABLE
INSERT 0 3
 item | qty | total
------+-----+-------
 pad  |   2 |  4.00
 pen  |   3 |  3.60
(2 rows)
```

### D. Types

The second column's common type is numeric.

<!-- example: postgresql -->
```sql
SELECT pg_typeof(column1) AS t1, pg_typeof(column2) AS t2 FROM (VALUES (1, 1), (2, 2.5)) AS v LIMIT 1;
VALUES (1), ('x');
VALUES (1), (true);
VALUES (1, 2), (3);
```

```text
   t1    |   t2
---------+---------
 integer | numeric
(1 row)

ERROR:  invalid input syntax for type integer: "x"
ERROR:  VALUES types integer and boolean cannot be matched
ERROR:  VALUES lists must all be the same length
```

## See also

[SELECT](select.md) · [INSERT](insert.md) · [WITH](with.md)
