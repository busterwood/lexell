# SET statements (Transact-SQL)

Set options of the session. Some change what lexdb does; the others, which drivers and tools send when they
connect, are taken and change nothing.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
SET option [ , option ... ] { ON | OFF }
SET option value
```

## Options

### Options with an effect

| Option | What it does |
|---|---|
| `NOCOUNT { ON \| OFF }` | `ON`: no `(n rows affected)` messages. `@@ROWCOUNT` is still set. |
| `ROWCOUNT n` | A `SELECT` returns at most *n* rows; 0 is no limit. |
| `XACT_ABORT { ON \| OFF }` | See [SET XACT_ABORT](set-xact-abort.md). |
| `IMPLICIT_TRANSACTIONS { ON \| OFF }` | See [SET IMPLICIT_TRANSACTIONS](set-implicit-transactions.md). |
| `IDENTITY_INSERT table { ON \| OFF }` | See [SET IDENTITY_INSERT](set-identity-insert.md). |
| `TRANSACTION ISOLATION LEVEL ...` | Taken; see [SET TRANSACTION ISOLATION LEVEL](set-transaction-isolation-level.md). |
| `QUOTED_IDENTIFIER { ON \| OFF }` | `OFF`: double quotes enclose strings, not names. It applies from the next batch. |
| `FMTONLY { ON \| OFF }` | `ON`: a `SELECT` returns its columns and no rows, and nothing else runs. |
| `LEXDB_DIALECT { POSTGRES \| TSQL }` | lexdb's own: see [SET LEXDB_DIALECT](set-lexdb-dialect.md). |
| `MAX_MATCH_STEPS [=] n` | lexdb's own: per-row step limit for [`MATCH_RECOGNIZE`](match-recognize.md) (default 10,000,000; 0 is no limit). |

### Options taken without an effect

`ANSI_NULLS`, `ANSI_PADDING`, `ANSI_WARNINGS`, `ANSI_NULL_DFLT_ON`, `ANSI_NULL_DFLT_OFF`, `ANSI_DEFAULTS`,
`ARITHABORT`, `ARITHIGNORE`, `CONCAT_NULL_YIELDS_NULL`, `NUMERIC_ROUNDABORT`, `CURSOR_CLOSE_ON_COMMIT`,
`TEXTSIZE n`, `LOCK_TIMEOUT n`, `DEADLOCK_PRIORITY ...`, `LANGUAGE ...`, `DATEFORMAT ...`, `DATEFIRST n`,
`NO_BROWSETABLE`, `QUERY_GOVERNOR_COST_LIMIT n`, `FORCEPLAN`, `SHOWPLAN_TEXT`, `SHOWPLAN_ALL`, `SHOWPLAN_XML`,
`PARSEONLY`, `NOEXEC`, `CONTEXT_INFO`.

lexdb behaves as SQL Server does with its usual settings (`ANSI_NULLS ON`, `CONCAT_NULL_YIELDS_NULL ON`,
`DATEFIRST 7`, `LANGUAGE us_english`), whatever these say.

## Remarks

- Several on/off options may be set in one statement: `SET ANSI_NULLS, ANSI_WARNINGS ON`.
- The options last for the session (until set again), not for the batch.

## Differences from SQL Server

- `ANSI_NULLS OFF` does not make `NULL = NULL` true, and `CONCAT_NULL_YIELDS_NULL OFF` does not make `'a' + NULL`
  give `'a'`.
- `DATEFIRST`, `DATEFORMAT`, `LANGUAGE` and `LOCK_TIMEOUT` change nothing: `@@DATEFIRST` stays 7 and `@@LOCK_TIMEOUT`
  -1.
- `NOEXEC ON`, `PARSEONLY ON` and the `SHOWPLAN` options do not stop statements from running, and return no plan.
- `SET STATISTICS IO ON`, `TIME`, `XML` and `PROFILE` are error 156.
- `ROWCOUNT n` limits `SELECT` only; in SQL Server it limits `UPDATE`, `DELETE` and `INSERT` too.
- `QUOTED_IDENTIFIER` takes effect at the next batch, not at the next statement of the same batch.
- A word that is not an option (`SET BOGUS ON`) is taken without an error.
- `@@OPTIONS` is not available (error 195).

## Examples

<!--setup: tsql
CREATE TABLE dbo.emp (id int PRIMARY KEY, name nvarchar(30), dept int);
INSERT dbo.emp VALUES (1, N'Ann', 1), (2, N'Bob', 1), (3, N'Cid', 2);
-->

The examples use one table:

```sql
CREATE TABLE dbo.emp (id int PRIMARY KEY, name nvarchar(30), dept int);
INSERT dbo.emp VALUES (1, N'Ann', 1), (2, N'Bob', 1), (3, N'Cid', 2);
```

### A. NOCOUNT

<!-- example: tsql -->
```sql
SET NOCOUNT ON;
UPDATE dbo.emp SET dept = dept WHERE id = 1;
SELECT @@ROWCOUNT AS still_counted;
SET NOCOUNT OFF;
UPDATE dbo.emp SET dept = dept WHERE id = 1;
```

```text
still_counted
-------------
1

(1 row affected)

(1 row affected)
```

### B. ROWCOUNT

<!-- example: tsql -->
```sql
SET ROWCOUNT 2;
SELECT id FROM dbo.emp ORDER BY id;
SET ROWCOUNT 0;
SELECT COUNT(*) AS n FROM dbo.emp;
```

```text
id
--
1
2

(2 rows affected)

n
-
3

(1 row affected)
```

### C. QUOTED_IDENTIFIER

<!-- example: tsql -->
```sql
SET QUOTED_IDENTIFIER OFF;
GO
SELECT "a string" AS s;
GO
SET QUOTED_IDENTIFIER ON;
GO
SELECT "name" FROM dbo.emp WHERE id = 1;
```

```text
s
--------
a string

(1 row affected)

name
----
Ann

(1 row affected)
```

### D. FMTONLY

<!-- example: tsql -->
```sql
SET FMTONLY ON;
SELECT id, name FROM dbo.emp;
SET FMTONLY OFF;
SELECT COUNT(*) AS n FROM dbo.emp;
```

```text
id name
-- ----

(0 rows affected)

n
-
3

(1 row affected)
```

### E. The options drivers send

<!-- example: tsql -->
```sql
SET ANSI_NULLS, ANSI_PADDING, ANSI_WARNINGS, ARITHABORT, CONCAT_NULL_YIELDS_NULL ON;
SET NUMERIC_ROUNDABORT OFF;
SET TEXTSIZE 2147483647;
SET LOCK_TIMEOUT 5000;
SET DATEFIRST 1;
SELECT @@DATEFIRST AS datefirst, @@LOCK_TIMEOUT AS lock_timeout, @@TEXTSIZE AS text_size, @@LANGUAGE AS language;
```

```text
datefirst lock_timeout text_size  language
--------- ------------ ---------- ----------
7         -1           2147483647 us_english

(1 row affected)
```

### F. Errors

<!-- example: tsql -->
```sql
SET STATISTICS IO ON;
```

```text
Msg 156, Level 15, State 1, Line 1
Incorrect syntax near the keyword 'ON'.
```

## See also

[SET XACT_ABORT](set-xact-abort.md) · [SET IMPLICIT_TRANSACTIONS](set-implicit-transactions.md) ·
[SET IDENTITY_INSERT](set-identity-insert.md) · [SET TRANSACTION ISOLATION LEVEL](set-transaction-isolation-level.md) ·
[SET LEXDB_DIALECT](set-lexdb-dialect.md) · [SET @local_variable](set-local-variable.md)
