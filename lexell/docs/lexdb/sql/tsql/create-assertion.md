# CREATE ASSERTION (Transact-SQL)

Creates an assertion: a condition over one or more tables that every write to them must leave true.

**Door:** SQL Server (TDS). **Follows:** the SQL standard (ISO/IEC 9075-2, 11.47), not SQL Server: **SQL Server has no
assertions.** `CREATE ASSERTION` is lexdb's own statement here, in the standard's form, with SQL Server's conventions
for constraints (error 547, its numbers for names that exist or do not). A script that has it does not run on SQL
Server.

An assertion is a constraint across tables. A `CHECK` constraint sees one row; an assertion sees whole tables, so it can
say that no order is without its customer. lexdb checks it after each statement that writes a table the assertion
reads, whichever door the write comes through (see [Assertions in the three doors](../../assertions.md)).

## Syntax

```
CREATE ASSERTION [ schema_name . ] assertion_name
    CHECK ( condition )
    [ [ NOT ] DEFERRABLE ] [ INITIALLY { IMMEDIATE | DEFERRED } ]
[ ; ]

condition:
    NOT EXISTS ( query )
  | EXISTS ( query )
  | ALL ( query ) SATISFY ( search_condition )
```

The characteristics each come once, in any order. The statement ends after `CHECK (...)` and the characteristics, so
no `;` is needed. There is no `IF NOT EXISTS` (T-SQL has none for `CREATE`: it is 156 at `IF`), no `ALTER ASSERTION`
and no `CASCADE`.

## Arguments

`NOT EXISTS ( query )`
: No row may satisfy the query. The usual form.

`EXISTS ( query )`
: The query must find at least one row. A `DELETE`, a `TRUNCATE TABLE` or an `UPDATE` may break it.

`ALL ( query ) SATISFY ( search_condition )`
: Every row of a one-column query satisfies the condition, written over the query's column name. A `NULL` satisfies
  nothing.

`DEFERRABLE`, `NOT DEFERRABLE`, `INITIALLY IMMEDIATE`, `INITIALLY DEFERRED`
: The standard's words, as in the PostgreSQL door (SQL Server has no deferral). Not deferrable is the default.
  A deferred assertion is checked at the outermost `COMMIT TRAN`; [`SET CONSTRAINTS`](set-constraints.md) moves the
  check. `NOT DEFERRABLE INITIALLY DEFERRED`, or a word twice, is 102.

## What a query may hold

The query must be one lexdb can restrict to the rows a statement wrote. One that is not is error **50000** (the
number lexdb gives its own errors; a real SQL Server number would tell a client something else):
`Cannot create assertion 'a': its query is not supported: ` and the reason:

| Reason | In the query |
|---|---|
| aggregates, GROUP BY or HAVING | `COUNT(*)`, `GROUP BY`, `HAVING` |
| a subquery under OR | `WHERE a OR EXISTS (...)` |
| a condition other than one NOT EXISTS (query), EXISTS (query) or ALL (query) SATISFY (condition) of one SELECT | two conditions joined by `AND`, a set operation, `CHECK (1 = 1)`, a scalar subquery compared with a value |
| FETCH FIRST, LIMIT, OFFSET or TOP | `TOP n`, `OFFSET ... FETCH` |
| a function whose value the rows do not decide | `GETDATE()`, `NEWID()`, `RAND()`, `USER_NAME()`, `NEXT VALUE FOR` and the like |
| a window function | `ROW_NUMBER() OVER (...)` |
| a query without a table | no `FROM`, or `VALUES` |
| a view, a function in FROM or a WITH query | a view, a table-valued function, a CTE |
| JOIN | `JOIN ... ON`: write the join's condition in `WHERE` |
| a subquery other than [NOT] EXISTS (query) or [NOT] IN (a query of one column) | a scalar subquery |
| an equijoin of columns that may be NULL | `a.g = b.g` where a column is not `NOT NULL`, not a key's and not kept from NULL by a condition of its own block |
| a session's temporary table | a `#temp` table goes with its session |

`ORDER BY` in the query is allowed. An unknown table is 208, an unknown column 207.

## When it is checked

- After each `INSERT`, `UPDATE`, `DELETE`, `MERGE`, `INSERT ... EXEC`, `OUTPUT ... INTO` an asserted table, `TRUNCATE
  TABLE`, bulk load and each statement of a procedure. A violation is error **547**:

  ```
  The INSERT statement conflicted with the assertion "a". The conflict occurred in database "lexdb", table "dbo.t".
  ```

  (the statement's word and the table written), severity 16. The statement ends and the transaction stays, as for a
  `CHECK` constraint's 547; with `SET XACT_ABORT ON` the transaction is rolled back and the batch ends, and
  `TRY ... CATCH` catches it.
- `CREATE ASSERTION` itself checks the rows there: 547 naming `CREATE ASSERTION`.
- A deferred assertion is checked at the outermost `COMMIT TRAN`. A violation is 547 naming `COMMIT TRANSACTION`; the
  transaction is rolled back and `@@TRANCOUNT` is 0 afterwards. With `XACT_ABORT ON` the batch ends too. A nested
  `COMMIT TRAN` only lowers `@@TRANCOUNT` and checks nothing. A `ROLLBACK TRAN` to a `SAVE TRAN` point undoes the
  writes since it, and the check at the commit sees what is left.
  [`SET CONSTRAINTS name IMMEDIATE`](set-constraints.md) checks at once: 547 naming `SET CONSTRAINTS`, the
  transaction kept.
- A write that is a bulk load (`INSERT BULK`: `bcp`, `SqlBulkCopy`) is checked whether or not `CHECK_CONSTRAINTS` is
  given: SQL Server skips `CHECK` constraints without it, and an assertion has no untrusted state.
- Each write path has its own page: see [the write paths](../../assertions.md#the-write-paths).

## What DDL does to its tables

| Statement | Result |
|---|---|
| `DROP TABLE` of a table it reads | 3729 `Cannot DROP TABLE 'dbo.t' because it is being referenced by object 'a'.` |
| `ALTER TABLE ... DROP COLUMN` of a column it reads | 5074 `The object 'a' is dependent on column 'c'.` |
| `sp_rename` of the table or of a column it reads | 15336 `... cannot be renamed because the object participates in enforced dependencies.` |
| `ALTER TABLE ... ALTER COLUMN` of a column it reads | The values are converted, and the whole query then runs: 547 if it fails. (SQL Server refuses `ALTER COLUMN` of a column a `CHECK` reads, 5074.) |
| `ADD` column, another column | Allowed. |

An assertion that is a `DROP ASSERTION` away: [DROP ASSERTION](drop-assertion.md). A name already used by an assertion
or a table, view or sequence is 2714; `DROP` of none is 3701; a schema that is not there is 2760.

## Catalog

`INFORMATION_SCHEMA.ASSERTIONS` lists it, `INFORMATION_SCHEMA.CHECK_CONSTRAINTS` has its row (`CHECK_CLAUSE`, as
written) and `INFORMATION_SCHEMA.CONSTRAINT_COLUMN_USAGE` has a row per column it reads. `CONSTRAINT_SCHEMA` shows
`public` where `dbo` is meant.

There is **no `sys.objects` row**: SQL Server has no object type for an assertion, and a made-up one would be listed
by SSMS's Object Explorer and by `sp_help` under nothing. So SSMS, `sqlcmd`'s `sp_help` and mssql-jdbc's
`DatabaseMetaData` do not see it, `OBJECT_ID('a')` is NULL, and `INFORMATION_SCHEMA` is where it is found. Oracle's
dictionary views list it too (see [Assertions in the three doors](../../assertions.md)).

## Differences from the standard

- No `CASCADE` or `RESTRICT` in `DROP ASSERTION`, and no `ALTER`.
- The query takes the shapes above, not every `<search condition>`.
- In a table of the same name, see 2714: assertions and tables share a namespace.

## Examples

### A. A violating INSERT

<!-- example: tsql -->
```sql
CREATE TABLE dbo.emp (id int PRIMARY KEY, name varchar(20), sal int);
INSERT dbo.emp VALUES (1, 'Ann', 50), (2, 'Bob', 30);
GO
CREATE ASSERTION sal_pos CHECK (NOT EXISTS (SELECT 1 FROM dbo.emp WHERE sal < 0))
GO
INSERT dbo.emp VALUES (3, 'Cy', -1);
INSERT dbo.emp VALUES (3, 'Cy', 10);
SELECT COUNT(*) AS n FROM dbo.emp;
```

```text
(2 rows affected)

Msg 547, Level 16, State 1, Line 1
The INSERT statement conflicted with the assertion "sal_pos". The conflict occurred in database "lexdb", table "dbo.emp".
(1 row affected)

n
-
3

(1 row affected)
```

### B. A deferred assertion that fails at COMMIT TRAN

<!-- example: tsql -->
```sql
CREATE TABLE dbo.customers (id int PRIMARY KEY, name varchar(20) NOT NULL);
CREATE TABLE dbo.orders (id int PRIMARY KEY, customer_id int NOT NULL, total int);
INSERT dbo.customers VALUES (1, 'Ann');
GO
CREATE ASSERTION order_has_customer CHECK (NOT EXISTS (
    SELECT 1 FROM dbo.orders o
    WHERE NOT EXISTS (SELECT 1 FROM dbo.customers c WHERE c.id = o.customer_id)))
    DEFERRABLE INITIALLY DEFERRED
GO
BEGIN TRAN;
INSERT dbo.orders VALUES (10, 2, 5);
SELECT COUNT(*) AS n FROM dbo.orders;
COMMIT TRAN;
SELECT @@TRANCOUNT AS trancount, COUNT(*) AS n FROM dbo.orders;
GO
BEGIN TRAN;
INSERT dbo.orders VALUES (10, 2, 5);
INSERT dbo.customers VALUES (2, 'Bob');
COMMIT TRAN;
SELECT COUNT(*) AS n FROM dbo.orders;
```

```text
(1 row affected)

(1 row affected)

n
-
1

(1 row affected)

Msg 547, Level 16, State 1, Line 4
The COMMIT TRANSACTION statement conflicted with the assertion "order_has_customer". The conflict occurred in database "lexdb", table "dbo.orders".
trancount n
--------- -
0         0

(1 row affected)

(1 row affected)

(1 row affected)

n
-
1

(1 row affected)
```

### C. SET CONSTRAINTS and TRY ... CATCH

<!-- example: tsql -->
```sql
CREATE TABLE dbo.stock (item int PRIMARY KEY, qty int);
GO
CREATE ASSERTION qty_ok CHECK (NOT EXISTS (SELECT 1 FROM dbo.stock WHERE qty < 0)) DEFERRABLE
GO
BEGIN TRAN;
SET CONSTRAINTS qty_ok DEFERRED;
INSERT dbo.stock VALUES (1, -3);
SET CONSTRAINTS qty_ok IMMEDIATE;
SELECT @@TRANCOUNT AS trancount;
ROLLBACK TRAN;
GO
BEGIN TRY
    INSERT dbo.stock VALUES (1, -3);
END TRY
BEGIN CATCH
    SELECT ERROR_NUMBER() AS errno;
END CATCH;
```

```text
(1 row affected)

Msg 547, Level 16, State 1, Line 4
The SET CONSTRAINTS statement conflicted with the assertion "qty_ok". The conflict occurred in database "lexdb", table "dbo.stock".
trancount
---------
1

(1 row affected)

(0 rows affected)

errno
-----
547

(1 row affected)
```

### D. A refused shape

<!-- example: tsql -->
```sql
CREATE ASSERTION too_many CHECK (NOT EXISTS (SELECT 1 FROM dbo.emp GROUP BY id HAVING COUNT(*) > 1))
GO
CREATE ASSERTION recent CHECK (NOT EXISTS (SELECT 1 FROM dbo.emp WHERE sal > DATEDIFF(s, '1970-01-01', GETDATE())))
GO
CREATE ASSERTION IF NOT EXISTS sal_pos CHECK (NOT EXISTS (SELECT 1 FROM dbo.emp WHERE sal < 0))
```

```text
Msg 50000, Level 16, State 1, Line 1
Cannot create assertion 'too_many': its query is not supported: aggregates, GROUP BY or HAVING.
Msg 50000, Level 16, State 1, Line 1
Cannot create assertion 'recent': its query is not supported: a function whose value the rows do not decide (the time, the user, random values, a sequence).
Msg 156, Level 15, State 1, Line 1
Incorrect syntax near the keyword 'not'.
```

### E. The INFORMATION_SCHEMA rows

<!-- example: tsql -->
```sql
SELECT CONSTRAINT_SCHEMA, CONSTRAINT_NAME, IS_DEFERRABLE, INITIALLY_DEFERRED
FROM INFORMATION_SCHEMA.ASSERTIONS ORDER BY CONSTRAINT_NAME;
SELECT CONSTRAINT_NAME, CHECK_CLAUSE
FROM INFORMATION_SCHEMA.CHECK_CONSTRAINTS WHERE CONSTRAINT_NAME = 'sal_pos';
SELECT TABLE_NAME, COLUMN_NAME, CONSTRAINT_NAME
FROM INFORMATION_SCHEMA.CONSTRAINT_COLUMN_USAGE WHERE CONSTRAINT_NAME = 'order_has_customer'
ORDER BY TABLE_NAME, COLUMN_NAME;
SELECT COUNT(*) AS objects FROM sys.objects WHERE name = 'sal_pos';
SELECT OBJECT_ID('sal_pos') AS id;
```

```text
CONSTRAINT_SCHEMA CONSTRAINT_NAME    IS_DEFERRABLE INITIALLY_DEFERRED
----------------- ------------------ ------------- ------------------
public            order_has_customer YES           YES
public            qty_ok             YES           NO
public            sal_pos            NO            NO

(3 rows affected)

CONSTRAINT_NAME CHECK_CLAUSE
--------------- --------------------------------------------------
sal_pos         (NOT EXISTS (SELECT 1 FROM dbo.emp WHERE sal < 0))

(1 row affected)

TABLE_NAME COLUMN_NAME CONSTRAINT_NAME
---------- ----------- ------------------
customers  id          order_has_customer
orders     customer_id order_has_customer

(2 rows affected)

objects
-------
0

(1 row affected)

id
----
NULL

(1 row affected)
```

### F. DROP TABLE and the assertion that reads it

<!-- example: tsql -->
```sql
DROP TABLE dbo.emp;
GO
ALTER TABLE dbo.emp DROP COLUMN sal;
GO
EXEC sp_rename 'dbo.emp.sal', 'pay', 'COLUMN';
```

```text
Msg 3729, Level 16, State 1, Line 1
Cannot DROP TABLE 'dbo.emp' because it is being referenced by object 'sal_pos'.
Msg 5074, Level 16, State 1, Line 1
The object 'sal_pos' is dependent on column 'sal'.
Msg 15336, Level 16, State 1, Line 1
Object 'dbo.emp.sal' cannot be renamed because the object participates in enforced dependencies.
```

## See also

[DROP ASSERTION](drop-assertion.md) · [SET CONSTRAINTS](set-constraints.md) · [BEGIN TRANSACTION](begin-transaction.md) ·
[COMMIT TRANSACTION](commit-transaction.md) · [Assertions in the three doors](../../assertions.md) ·
[Errors](errors.md)
