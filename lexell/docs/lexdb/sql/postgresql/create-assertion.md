# CREATE ASSERTION

Creates an assertion: a condition over one or more tables that every write to them must leave true.

**Door:** PostgreSQL. **Follows:** the SQL standard (ISO/IEC 9075-2, 11.47), not PostgreSQL: **PostgreSQL has no
assertions.** `CREATE ASSERTION` is lexdb's own statement here, in the standard's form, with PostgreSQL's conventions
for constraints (its error states and its `DEFERRABLE` words). A `pg_dump` of the database does not contain it.

An assertion is a constraint across tables. A `CHECK` constraint sees one row; an assertion sees whole tables, so it can
say that no order is without its customer, or that no two rows of a group are both `a` and `b`. lexdb checks it after
each statement that writes a table the assertion reads, whichever door the write comes through (see
[Assertions in the three doors](../../assertions.md)).

## Syntax

```
CREATE ASSERTION [ IF NOT EXISTS ] [ schema. ] name
    CHECK ( condition )
    [ [ NOT ] DEFERRABLE ] [ INITIALLY { IMMEDIATE | DEFERRED } ]

condition:
    NOT EXISTS ( query )
  | EXISTS ( query )
  | ALL ( query ) SATISFY ( search_condition )
```

The characteristics each come once, in any order. There is no `ALTER ASSERTION`, and `DROP ASSERTION` has no `CASCADE`
or `RESTRICT` (the standard's has none).

## Arguments

`NOT EXISTS ( query )`
: No row may satisfy the query. The usual form: the query finds the rows that break the rule.

`EXISTS ( query )`
: The query must find at least one row. A `DELETE`, a `TRUNCATE` or an `UPDATE` may break it.

`ALL ( query ) SATISFY ( search_condition )`
: Every row of a one-column query satisfies the condition, written over the query's column name. A `NULL` satisfies
  nothing.

`DEFERRABLE`, `NOT DEFERRABLE`, `INITIALLY IMMEDIATE`, `INITIALLY DEFERRED`
: As for a foreign key. An assertion that is not deferrable is checked after each statement. `INITIALLY DEFERRED` alone
  is `DEFERRABLE`; `NOT DEFERRABLE INITIALLY DEFERRED` is 42601 (`constraint declared INITIALLY DEFERRED must be
  DEFERRABLE`), and a word twice is 42601 too. A deferrable assertion is checked at `COMMIT` when it is `INITIALLY
  DEFERRED` or after [`SET CONSTRAINTS`](set-constraints.md).

`IF NOT EXISTS`
: No error if an assertion of the name is there (a table, view or sequence of the name is still 42P07).

## What a query may hold

lexdb checks an assertion from the rows a statement wrote, so the query must be one it can restrict to them. A query
that is not is 0A000, `assertion's query is not supported: ` and the reason:

| Reason | In the query |
|---|---|
| aggregates, GROUP BY or HAVING | `count(*)`, `GROUP BY`, `HAVING` |
| a subquery under OR | `WHERE a OR EXISTS (...)` |
| a condition other than one NOT EXISTS (query), EXISTS (query) or ALL (query) SATISFY (condition) of one SELECT | two conditions joined by `AND`, a set operation, `CHECK (1 = 1)`, a scalar subquery compared with a value |
| FETCH FIRST, LIMIT, OFFSET or TOP | a limit |
| a function whose value the rows do not decide | `now()`, `random()`, `current_user`, `nextval` and the like |
| a window function | `row_number() OVER (...)` |
| a query without a table | no `FROM`, or `VALUES` |
| a view, a function in FROM or a WITH query | a view, a set-returning function, a CTE |
| JOIN | `JOIN ... ON`: write the join's condition in `WHERE` |
| a subquery other than [NOT] EXISTS (query) or [NOT] IN (a query of one column) | a scalar subquery, `ANY`, `ALL` |
| an equijoin of columns that may be NULL | `a.g = b.g` where a column is not `NOT NULL`, not a key's and not kept from NULL by a condition of its own block |
| a session's temporary table | a `TEMP` table goes with its session; the assertion would stay |

`ORDER BY` in the query is allowed. An unknown table is 42P01, an unknown column 42703.

## When it is checked

- After each `INSERT` (also `INSERT ... SELECT` and `ON CONFLICT`), `UPDATE`, `DELETE`, `MERGE`, `COPY FROM` and
  `TRUNCATE`, and after each statement of a function or procedure. A violation is **23514**,
  `assertion "name" is violated`, and undoes the statement. The transaction is then aborted as after any error
  (25P02), unless the statement was under a `SAVEPOINT`.
- An `UPDATE` that sets none of the columns the assertion reads is not checked.
- `CREATE ASSERTION` itself checks the rows there: if they break it, 23514 `assertion "name" is violated by some row`.
- A deferred assertion is checked when the transaction commits. A violation fails the `COMMIT` with 23514 and the
  transaction is rolled back. [`SET CONSTRAINTS name IMMEDIATE`](set-constraints.md) checks at once.
- Foreign key actions are checked: `ON DELETE CASCADE`, `SET NULL`, `SET DEFAULT` and `ON UPDATE CASCADE` write the
  child table, and the assertions on it run.
- Each write path has its own page: see [the write paths](../../assertions.md#the-write-paths).

## What DDL does to its tables

| Statement | Result |
|---|---|
| `DROP TABLE` of a table it reads | 2BP01 `cannot drop table t because other objects depend on it`, DETAIL `assertion a depends on table t`. `DROP TABLE ... CASCADE` drops the assertion too. |
| `ALTER TABLE ... DROP COLUMN` of a column it reads | 2BP01; `CASCADE` drops the assertion. |
| `ALTER TABLE ... RENAME` of the table or of a column it reads | 0A000: PostgreSQL's renames follow what depends on them, lexdb's stored text cannot. |
| `ALTER TABLE ... TYPE` of a column | The values are cast, and the whole query then runs: 23514 if it fails. |
| `ADD COLUMN`, another column | Allowed. |

## Whose rights the check has

The check runs with the rights of the assertion's owner, as in the Oracle door: a user with `INSERT`, `UPDATE` or
`DELETE` on an asserted table and no `SELECT` on it is not refused (42501); the write is checked, and breaks it with
23514. The user's own `WHERE` and `RETURNING` still need the privilege.

## Catalog

`information_schema.assertions` lists it (`constraint_catalog`, `constraint_schema`, `constraint_name`,
`is_deferrable`, `initially_deferred`), `information_schema.check_constraints` has its row (`check_clause` is the
condition as written), and `information_schema.constraint_column_usage` has a row per column it reads.

There is **no `pg_constraint` row**. Every `pg_constraint` row has a `conrelid` or a `contypid` that clients join
(psql's `\d` lists constraints by `conrelid`, pgjdbc's `getPrimaryKeys` and `getImportedKeys` by `contype`), and a
row of neither would be a constraint of nothing. So psql's `\d` of an asserted table works and does not show the
assertion, `pg_dump` and pgjdbc's `DatabaseMetaData` do not see it, and the table's `pg_class.relhastriggers` is true:
the checks are its triggers, in effect (`pg_trigger` has no rows).

## Differences from the standard

- No `CASCADE` or `RESTRICT` in `DROP ASSERTION`, and no `ALTER`.
- The query takes the shapes above, not every `<search condition>`.
- The names of an assertion and a table share one namespace, as relations do in PostgreSQL.

## Examples

### A. A violating INSERT

<!-- example: postgresql -->
```sql
CREATE TABLE emp (id int PRIMARY KEY, name text, sal int);
INSERT INTO emp VALUES (1, 'Ann', 50), (2, 'Bob', 30);
CREATE ASSERTION sal_pos CHECK (NOT EXISTS (SELECT 1 FROM emp WHERE sal < 0));
INSERT INTO emp VALUES (3, 'Cy', -1);
INSERT INTO emp VALUES (3, 'Cy', 10);
SELECT count(*) FROM emp;
```

```text
CREATE TABLE
INSERT 0 2
CREATE ASSERTION
ERROR:  assertion "sal_pos" is violated
INSERT 0 1
 count
-------
     3
(1 row)
```

### B. Two tables, and a deferred assertion that fails at COMMIT

<!-- example: postgresql -->
```sql
CREATE TABLE customers (id int PRIMARY KEY, name text NOT NULL);
CREATE TABLE orders (id int PRIMARY KEY, customer_id int NOT NULL, total int);
INSERT INTO customers VALUES (1, 'Ann');
CREATE ASSERTION order_has_customer CHECK (NOT EXISTS (
    SELECT 1 FROM orders o
    WHERE NOT EXISTS (SELECT 1 FROM customers c WHERE c.id = o.customer_id)))
    DEFERRABLE INITIALLY DEFERRED;
BEGIN;
INSERT INTO orders VALUES (10, 2, 5);
SELECT count(*) FROM orders;
COMMIT;
SELECT count(*) FROM orders;
BEGIN;
INSERT INTO orders VALUES (10, 2, 5);
INSERT INTO customers VALUES (2, 'Bob');
COMMIT;
SELECT count(*) FROM orders;
```

```text
CREATE TABLE
CREATE TABLE
INSERT 0 1
CREATE ASSERTION
BEGIN
INSERT 0 1
 count
-------
     1
(1 row)

ERROR:  assertion "order_has_customer" is violated
 count
-------
     0
(1 row)

BEGIN
INSERT 0 1
INSERT 0 1
COMMIT
 count
-------
     1
(1 row)
```

### C. SET CONSTRAINTS

<!-- example: postgresql -->
```sql
CREATE TABLE stock (item int PRIMARY KEY, qty int);
CREATE ASSERTION qty_ok CHECK (NOT EXISTS (SELECT 1 FROM stock WHERE qty < 0)) DEFERRABLE;
BEGIN;
SET CONSTRAINTS qty_ok DEFERRED;
INSERT INTO stock VALUES (1, -3);
SET CONSTRAINTS qty_ok IMMEDIATE;
ROLLBACK;
BEGIN;
SET CONSTRAINTS qty_ok DEFERRED;
INSERT INTO stock VALUES (1, -3);
UPDATE stock SET qty = 3;
COMMIT;
SELECT * FROM stock;
```

```text
CREATE TABLE
CREATE ASSERTION
BEGIN
SET CONSTRAINTS
INSERT 0 1
ERROR:  assertion "qty_ok" is violated
ROLLBACK
BEGIN
SET CONSTRAINTS
INSERT 0 1
UPDATE 1
COMMIT
 item | qty
------+-----
    1 |   3
(1 row)
```

### D. A refused shape

<!-- example: postgresql -->
```sql
CREATE ASSERTION too_many CHECK (NOT EXISTS (SELECT 1 FROM emp GROUP BY id HAVING count(*) > 1));
CREATE ASSERTION recent CHECK (NOT EXISTS (SELECT 1 FROM emp WHERE sal > extract(epoch FROM now())));
CREATE ASSERTION two CHECK (NOT EXISTS (SELECT 1 FROM emp WHERE sal < 0) AND NOT EXISTS (SELECT 1 FROM emp WHERE sal > 9));
```

```text
ERROR:  assertion's query is not supported: aggregates, GROUP BY or HAVING
ERROR:  assertion's query is not supported: a function whose value the rows do not decide (the time, the user, random values, a sequence)
ERROR:  assertion's query is not supported: a condition other than one NOT EXISTS (query), EXISTS (query) or ALL (query) SATISFY (condition) of one SELECT (split it into several assertions)
```

### E. The information_schema rows

<!-- example: postgresql -->
```sql
SELECT constraint_schema, constraint_name, is_deferrable, initially_deferred
FROM information_schema.assertions ORDER BY constraint_name;
SELECT constraint_name, check_clause
FROM information_schema.check_constraints WHERE constraint_name = 'sal_pos';
SELECT table_name, column_name, constraint_name
FROM information_schema.constraint_column_usage WHERE constraint_name = 'order_has_customer'
ORDER BY table_name, column_name;
SELECT count(*) FROM pg_constraint WHERE conname = 'sal_pos';
```

```text
 constraint_schema |  constraint_name   | is_deferrable | initially_deferred
-------------------+--------------------+---------------+--------------------
 public            | order_has_customer | YES           | YES
 public            | qty_ok             | YES           | NO
 public            | sal_pos            | NO            | NO
(3 rows)

 constraint_name |                  check_clause
-----------------+------------------------------------------------
 sal_pos         | (NOT EXISTS (SELECT 1 FROM emp WHERE sal < 0))
(1 row)

 table_name | column_name |  constraint_name
------------+-------------+--------------------
 customers  | id          | order_has_customer
 orders     | customer_id | order_has_customer
(2 rows)

 count
-------
     0
(1 row)
```

### F. A COPY that breaks one

<!-- example: postgresql -->
```sql
COPY emp FROM STDIN;
4	Di	20
5	Ed	-7
\.
SELECT count(*) FROM emp;
COPY emp FROM STDIN;
4	Di	20
5	Ed	7
\.
SELECT count(*) FROM emp;
```

```text
ERROR:  assertion "sal_pos" is violated
 count
-------
     3
(1 row)

COPY 2
 count
-------
     5
(1 row)
```

### G. DROP TABLE and the assertion that reads it

<!-- example: postgresql -->
```sql
DROP TABLE emp;
DROP TABLE emp CASCADE;
SELECT count(*) FROM information_schema.assertions WHERE constraint_name = 'sal_pos';
```

```text
ERROR:  cannot drop table emp because other objects depend on it
DETAIL:  assertion sal_pos depends on table emp
HINT:  Use DROP ... CASCADE to drop the dependent objects too.
DROP TABLE
 count
-------
     0
(1 row)
```

### H. Other ways in: a savepoint, a cascade, ALTER TYPE, TRUNCATE, a rename, a temporary table

<!-- example: postgresql -->
```sql
CREATE TABLE acct (id int PRIMARY KEY, bal int);
INSERT INTO acct VALUES (1, 5);
CREATE ASSERTION bal_pos CHECK (NOT EXISTS (SELECT 1 FROM acct WHERE bal < 0));
BEGIN;
INSERT INTO acct VALUES (2, -5);
SELECT 1;
ROLLBACK;
BEGIN;
SAVEPOINT s;
INSERT INTO acct VALUES (2, -5);
ROLLBACK TO s;
INSERT INTO acct VALUES (2, 5);
COMMIT;
CREATE TEMP TABLE scratch (v int);
CREATE ASSERTION scratch_pos CHECK (NOT EXISTS (SELECT 1 FROM scratch WHERE v < 0));
CREATE TABLE parent (id int PRIMARY KEY);
CREATE TABLE child (id int PRIMARY KEY, pid int REFERENCES parent ON DELETE CASCADE);
INSERT INTO parent VALUES (1);
INSERT INTO child VALUES (1, 1);
CREATE ASSERTION has_child CHECK (EXISTS (SELECT 1 FROM child));
DELETE FROM parent WHERE id = 1;
TRUNCATE child;
CREATE TABLE label (id int, v text);
INSERT INTO label VALUES (1, '5');
CREATE ASSERTION label_small CHECK (NOT EXISTS (SELECT 1 FROM label WHERE v = '5000'));
ALTER TABLE label ALTER COLUMN v TYPE int USING v::int * 1000;
ALTER TABLE acct RENAME TO acct2;
ALTER TABLE acct RENAME COLUMN bal TO amount;
```

```text
CREATE TABLE
INSERT 0 1
CREATE ASSERTION
BEGIN
ERROR:  assertion "bal_pos" is violated
ERROR:  current transaction is aborted, commands ignored until end of transaction block
ROLLBACK
BEGIN
SAVEPOINT
ERROR:  assertion "bal_pos" is violated
ROLLBACK
INSERT 0 1
COMMIT
CREATE TABLE
ERROR:  lexdb: an assertion cannot read a temporary table ("scratch")
CREATE TABLE
CREATE TABLE
INSERT 0 1
INSERT 0 1
CREATE ASSERTION
ERROR:  assertion "has_child" is violated
ERROR:  assertion "has_child" is violated
CREATE TABLE
INSERT 0 1
CREATE ASSERTION
ERROR:  assertion "label_small" is violated
ERROR:  cannot rename table acct because assertion bal_pos reads it
ERROR:  cannot rename column bal of table acct because assertion bal_pos reads it
```

## See also

[DROP ASSERTION](drop-assertion.md) · [SET CONSTRAINTS](set-constraints.md) · [COPY](copy.md) ·
[Assertions in the three doors](../../assertions.md) · [Constraint catalog](catalog-constraints.md) ·
[Error codes](errors.md)
