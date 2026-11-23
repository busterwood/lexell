# SET IDENTITY_INSERT (Transact-SQL)

Lets explicit values be inserted into a table's identity column.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
SET IDENTITY_INSERT [ [ database_name . ] schema_name . ] table_name { ON | OFF }
```

## Arguments

*table_name*
: A table with an `IDENTITY` column, or a `#temp` table.

`ON`
: An `INSERT` into the table may give the identity column a value.

`OFF`
: The default: the identity column takes only the values the table makes, and an explicit value is error 544.

## Remarks

- The setting lasts until it is set `OFF` or the session ends.
- After an explicit value larger than the current one (for a positive increment), the next value made follows it:
  with `IDENTITY(10, 5)` and an inserted 100, the next row gets 105. A smaller value does not move the identity.
- An explicit value is not checked for being unique; a primary key or unique constraint is (error 2627).
- `SET IDENTITY_INSERT` runs when the batch reaches it, as SQL Server's does.

## Differences from SQL Server

- lexdb does not check the statement's table. SQL Server's errors are not given: a table that does not exist (208)
  or has no identity column (8106), or a second table set `ON` while another is (8107). The statement is taken and
  changes nothing.
- With `IDENTITY_INSERT ON`, an `INSERT` that leaves out the identity column gets the next value; SQL Server refuses
  it (545). An `INSERT` with no column list is taken; SQL Server refuses it (8101).

## Examples

<!--setup: tsql
CREATE TABLE dbo.ticket (id int IDENTITY(10, 5) PRIMARY KEY, title nvarchar(30));
INSERT dbo.ticket (title) VALUES (N'first'), (N'second');
-->

The examples use one table:

```sql
CREATE TABLE dbo.ticket (id int IDENTITY(10, 5) PRIMARY KEY, title nvarchar(30));
INSERT dbo.ticket (title) VALUES (N'first'), (N'second');
```

### A. Insert an explicit identity value

<!-- example: tsql -->
```sql
SET IDENTITY_INSERT dbo.ticket ON;
INSERT INTO dbo.ticket (id, title) VALUES (100, N'imported');
SET IDENTITY_INSERT dbo.ticket OFF;
INSERT INTO dbo.ticket (title) VALUES (N'next');
SELECT * FROM dbo.ticket ORDER BY id;
```

```text
(1 row affected)

(1 row affected)

id  title
--- --------
10  first
15  second
100 imported
105 next

(4 rows affected)
```

### B. Fill a gap: a smaller value does not move the identity

<!-- example: tsql -->
```sql
SET IDENTITY_INSERT dbo.ticket ON;
INSERT INTO dbo.ticket (id, title) VALUES (12, N'between');
SET IDENTITY_INSERT dbo.ticket OFF;
INSERT INTO dbo.ticket (title) VALUES (N'after');
SELECT * FROM dbo.ticket ORDER BY id;
```

```text
(1 row affected)

(1 row affected)

id  title
--- --------
10  first
12  between
15  second
100 imported
105 next
110 after

(6 rows affected)
```

### C. A temporary table

<!-- example: tsql -->
```sql
CREATE TABLE #t (id int IDENTITY, v nvarchar(10));
SET IDENTITY_INSERT #t ON;
INSERT #t (id, v) VALUES (7, N'seven');
SET IDENTITY_INSERT #t OFF;
INSERT #t (v) VALUES (N'eight');
SELECT * FROM #t;
```

```text
(1 row affected)

(1 row affected)

id v
-- -----
7  seven
8  eight

(2 rows affected)
```

### D. Errors

<!-- example: tsql -->
```sql
INSERT INTO dbo.ticket (id, title) VALUES (200, N'not allowed');
SET IDENTITY_INSERT dbo.ticket ON;
INSERT INTO dbo.ticket (id, title) VALUES (100, N'again');
SET IDENTITY_INSERT dbo.ticket OFF;
```

```text
Msg 544, Level 16, State 1, Line 1
cannot insert a non-DEFAULT value into column "id"
Msg 2627, Level 14, State 1, Line 3
Violation of PRIMARY KEY constraint 'ticket_pkey'. Cannot insert duplicate key in object 'dbo.ticket'. The duplicate key value is (100).
```

## See also

[INSERT](insert.md) · CREATE TABLE · [SET statements](set-statements.md)
