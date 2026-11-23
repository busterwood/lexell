# Checking the documentation's examples

Every SQL example in these pages is run against a lexdb, through the door it documents, and its output is the
output lexdb gave. `check_examples.py` runs them again and compares, so the pages can be checked after lexdb
changes.

## Marking an example

An example is an HTML comment naming the door, a `sql` block, and a `text` block with the output:

````markdown
<!-- example: tsql -->
```sql
SELECT 1 AS one;
```

```text
one
---
1

(1 row affected)
```
````

The door is `postgresql`, `tsql` or `oracle`. The comment does not show when the page is rendered. Only blank lines
may come between the `sql` block and its `text` block.

Setup that a page needs but does not show goes in a comment of its own, run in page order with the examples and
not compared:

```markdown
<!--setup: oracle
CREATE TABLE emp (id NUMBER PRIMARY KEY, name VARCHAR2(30));
-->
```

Blocks without a marker (shell commands, program output, syntax blocks) are not run.

## How a page is run

- Each page gets a new lexdb: a scratch data directory and free ports on 127.0.0.1 for the three doors
  (`--unsafe-no-sync`, as for tests). It is stopped and its directory removed after the page.
- Each door has one session per page, opened at the door's first example, so a page's examples build on each other
  (a table made in one example is there in the next). Examples run in page order across doors: an example may make
  a table in the PostgreSQL door and the next read it in the SQL Server door.
- Logins: `postgres` in the PostgreSQL door, `sa` with any password in the SQL Server door, `sa`/`SA` in the Oracle
  door (lexdb's `trust` logins). The time zone is UTC.

### The output of each door

- **postgresql**: the block is given to **psql** (`psql -X`, no pager) as it is, and the output is psql's, with
  errors and notices in place (`ERROR:  ...`). `COPY ... FROM STDIN` with its data lines and `\.` works as in a psql
  script.
- **tsql**: the block is T-SQL **batches separated by `GO` lines**, as sqlcmd takes them, sent through Microsoft's
  JDBC driver by `DocRun.java`. The output is as sqlcmd and SSMS's text mode show it: each result set as columns
  padded to their widest value with a line of dashes under the names, `NULL` for NULL, `(No column name)` for a
  column without a name; `(N rows affected)` after each result set and each statement that changes rows; `PRINT`
  and other messages as their text; errors as `Msg N, Level L, State S, Line K` and the message.
- **oracle**: the block is statements **as SQL\*Plus takes them**: SQL ends with `;` at the end of a line; PL/SQL
  (`BEGIN`, `DECLARE`, `CREATE [OR REPLACE] PROCEDURE`, `FUNCTION`, `PACKAGE`, `TRIGGER`, `TYPE`) ends with a line
  holding `/`. They are sent through Oracle's JDBC thin driver by `DocRun.java`. The output is as SQL\*Plus shows it
  with `SET FEEDBACK 1` and `SET SERVEROUTPUT ON`: result columns padded, numbers to the right, NULL as nothing;
  `N rows selected.` or `no rows selected`; `1 row created.`, `Table created.`, `PL/SQL procedure successfully
  completed.` and the like; `DBMS_OUTPUT` lines before the feedback; errors as `ERROR:` and the `ORA-` line.
  The connection is not in autocommit mode, as in SQL\*Plus: a transaction lasts until `COMMIT` or `ROLLBACK`.
  Values are as the JDBC driver's `getString` gives them (a DATE as `2026-11-23 00:00:00`): use `TO_CHAR` where the
  format matters.

## Running the checker

It needs Python 3, psql, a JDK (javac and java 17 or later), and a directory with the two JDBC drivers:

- `mssql-jdbc-*.jar` (Maven Central `com.microsoft.sqlserver:mssql-jdbc`, 13.6.2 was used);
- `ojdbc11-*.jar` (Maven Central `com.oracle.database.jdbc:ojdbc11`, 23.26.4 was used).

```sh
lexell/compiler/out/lxlc lexell/cmd/lexdb.lxl -O -o /tmp/lexdb
python3 lexell/docs/lexdb/tools/check_examples.py --lexdb /tmp/lexdb --jars ~/jars lexell/docs/lexdb
```

It prints each example that differs, as a diff of the page's output against lexdb's, and `N examples, M differ`; the
exit code is 1 when any differ. `-v` names every example that matches. `--update` writes lexdb's output into the
pages instead of comparing: use it for a new example, then read the diff before committing.

`LEXDB` and `LEXDB_DOC_JARS` may stand for `--lexdb` and `--jars`. `DocRun.java` is compiled into the temporary
directory on first use.

## Java and Lexell programs

The programs under `connect/examples/` are not run by the checker. Their output in the connect pages was taken from a
run against a lexdb built from the same tree; each page gives the commands.
