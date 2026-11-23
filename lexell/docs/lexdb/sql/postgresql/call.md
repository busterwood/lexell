# CALL

Runs a procedure.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
CALL name ( [ argument ] [, ...] )

argument:
    expression | argname => expression
```

## Arguments

*name*
: The procedure, optionally schema-qualified.

*argument*
: A value for each parameter, by position or by name (`amount => 10`). Parameters with defaults may be left out. An
  `OUT` parameter takes a placeholder, usually `NULL`.

## Remarks

- The arguments are computed as a `SELECT` and converted to the parameters' types.
- A procedure with `OUT` or `INOUT` parameters returns one row of them; otherwise the command tag is `CALL`.
- The procedure needs `EXECUTE` for the calling role (granted to `PUBLIC` until revoked).

## Differences from PostgreSQL

None known.

## Examples

<!--setup: postgresql
CREATE TABLE emp (id int PRIMARY KEY, name text, salary numeric(8,2));
INSERT INTO emp VALUES (1, 'ada', 5200), (2, 'ben', 3100);
CREATE PROCEDURE raise(eid int, amount numeric DEFAULT 50) LANGUAGE sql AS 'UPDATE emp SET salary = salary + amount WHERE id = eid';
CREATE FUNCTION twice(x int) RETURNS int RETURN x * 2;
-->

The examples use a table, a procedure and a function:

```sql
CREATE TABLE emp (id int PRIMARY KEY, name text, salary numeric(8,2));
INSERT INTO emp VALUES (1, 'ada', 5200), (2, 'ben', 3100);
CREATE PROCEDURE raise(eid int, amount numeric DEFAULT 50) LANGUAGE sql
    AS 'UPDATE emp SET salary = salary + amount WHERE id = eid';
CREATE FUNCTION twice(x int) RETURNS int RETURN x * 2;
```

### A. By position, by name, and a default

<!-- example: postgresql -->
```sql
CALL raise(1, 100);
CALL raise(amount => 200, eid => 2);
CALL raise(2);
SELECT * FROM emp ORDER BY id;
```

```text
CALL
CALL
CALL
 id | name | salary
----+------+---------
  1 | ada  | 5300.00
  2 | ben  | 3350.00
(2 rows)
```

### B. Rolled back with the block

<!-- example: postgresql -->
```sql
BEGIN;
CALL raise(1, 100);
ROLLBACK;
SELECT salary FROM emp WHERE id = 1;
```

```text
BEGIN
CALL
ROLLBACK
 salary
---------
 5300.00
(1 row)
```

### C. Errors

<!-- example: postgresql -->
```sql
CALL nosuch();
CALL twice(1);
CREATE ROLE clerk;
REVOKE EXECUTE ON PROCEDURE raise(int, numeric) FROM PUBLIC;
SET ROLE clerk;
CALL raise(1);
RESET ROLE;
```

```text
ERROR:  procedure nosuch() does not exist
HINT:  No procedure matches the given name and argument types. You might need to add explicit type casts.
ERROR:  twice(integer) is not a procedure
CREATE ROLE
REVOKE
SET
ERROR:  permission denied for procedure raise
RESET
```

## See also

[CREATE PROCEDURE](create-procedure.md) · [GRANT](grant.md)
