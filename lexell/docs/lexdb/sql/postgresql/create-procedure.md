# CREATE PROCEDURE

Makes a procedure written in SQL, run with [CALL](call.md).

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
CREATE [ OR REPLACE ] PROCEDURE name ( [ [ argmode ] [ argname ] argtype [ { DEFAULT | = } default_expr ] [, ...] ] )
    { LANGUAGE sql
      | [ EXTERNAL ] SECURITY { INVOKER | DEFINER }
      | SET configuration_parameter { TO value | = value | FROM CURRENT }
      | AS 'definition'
      | BEGIN ATOMIC statement; [ ... ] END
    } ...

argmode:
    IN | OUT | INOUT | VARIADIC
```

## Arguments

*name*
: The procedure's name, optionally schema-qualified. Procedures of one name may overload one another by their
  argument types.

*argmode*, *argname*, *argtype*, `DEFAULT`
: As for [CREATE FUNCTION](create-function.md). `OUT` and `INOUT` parameters make the row `CALL` returns.

`LANGUAGE sql`
: The only language. Another is 42704.

`AS '`*definition*`'`, `BEGIN ATOMIC ... END`
: The body: SQL statements, run in order.

## Remarks

- The body's statements run in the `CALL`'s transaction: all of them, or none if one fails. In a block, they are
  kept or undone with it.
- A procedure returns no value; its `OUT` parameters give one row.
- The body's syntax is checked at `CREATE`.
- `pg_proc` lists procedures with `prokind` `p`.

## Differences from PostgreSQL

- **There is no PL/pgSQL, and no `DO`.** Procedures are `LANGUAGE sql` only: a body cannot `COMMIT` or
  `ROLLBACK`, or loop.
- In a procedure's body, `1 + p / 100` with a `numeric` parameter `p` of 10 gives 1, as if the division were of
  integers: `UPDATE emp SET salary = salary * (1 + pct / 100)` leaves the salaries as they were. The same
  expression in a function's body or in a query gives 1.1.
- `SECURITY DEFINER` is accepted and ignored.
- `ALTER PROCEDURE` is not supported.

## Examples

<!--setup: postgresql
CREATE TABLE emp (id int PRIMARY KEY, name text, salary numeric(8,2));
INSERT INTO emp VALUES (1, 'ada', 5200), (2, 'ben', 3100);
-->

The examples use one table:

```sql
CREATE TABLE emp (id int PRIMARY KEY, name text, salary numeric(8,2));
INSERT INTO emp VALUES (1, 'ada', 5200), (2, 'ben', 3100);
```

### A. A procedure that changes rows

<!-- example: postgresql -->
```sql
CREATE PROCEDURE raise(eid int, amount numeric) LANGUAGE sql AS $$
    UPDATE emp SET salary = salary + amount WHERE id = eid
$$;
CALL raise(2, 100);
SELECT salary FROM emp WHERE id = 2;
```

```text
CREATE PROCEDURE
CALL
 salary
---------
 3200.00
(1 row)
```

### B. An OUT parameter

<!-- example: postgresql -->
```sql
CREATE PROCEDURE head_count(OUT n bigint) LANGUAGE sql AS 'SELECT count(*) FROM emp';
CALL head_count(NULL);
```

```text
CREATE PROCEDURE
 n
---
 2
(1 row)
```

### C. All or nothing

<!-- example: postgresql -->
```sql
CREATE PROCEDURE hire_two() LANGUAGE sql
BEGIN ATOMIC
    INSERT INTO emp VALUES (3, 'cy', 2900);
    INSERT INTO emp VALUES (3, 'dee', 2800);
END;
CALL hire_two();
SELECT count(*) FROM emp;
```

```text
CREATE PROCEDURE
ERROR:  duplicate key value violates unique constraint "emp_pkey"
DETAIL:  Key (id)=(3) already exists.
 count
-------
     2
(1 row)
```

### D. Errors

<!-- example: postgresql -->
```sql
CREATE PROCEDURE p() LANGUAGE plpgsql AS $$ BEGIN COMMIT; END $$;
SELECT raise(1, 1);
```

```text
ERROR:  language "plpgsql" does not exist
ERROR:  raise() is a procedure
HINT:  To call a procedure, use CALL.
```

## See also

[CALL](call.md) · [CREATE FUNCTION](create-function.md) · [DROP FUNCTION, DROP PROCEDURE](drop-function.md)
