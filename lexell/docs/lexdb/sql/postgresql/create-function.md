# CREATE FUNCTION

Makes a function written in SQL.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
CREATE [ OR REPLACE ] FUNCTION name ( [ [ argmode ] [ argname ] argtype [ { DEFAULT | = } default_expr ] [, ...] ] )
    [ RETURNS rettype | RETURNS SETOF rettype | RETURNS TABLE ( column_name column_type [, ...] ) ]
    { LANGUAGE sql
      | { IMMUTABLE | STABLE | VOLATILE }
      | [ NOT ] LEAKPROOF
      | CALLED ON NULL INPUT | RETURNS NULL ON NULL INPUT | STRICT
      | [ EXTERNAL ] SECURITY { INVOKER | DEFINER }
      | PARALLEL { UNSAFE | RESTRICTED | SAFE }
      | COST execution_cost | ROWS result_rows
      | SET configuration_parameter { TO value | = value | FROM CURRENT }
      | AS 'definition'
      | sql_body
    } ...

argmode:
    IN | OUT | INOUT | VARIADIC

sql_body:
    RETURN expression
    | BEGIN ATOMIC statement; [ ... ] END
```

## Arguments

*name*
: The function's name, optionally schema-qualified. Functions of one name may overload one another by their
  argument types.

*argmode*, *argname*, *argtype*
: The parameters. `IN` is the default. `OUT` and `INOUT` parameters make the result's columns. In the body a
  parameter is named, or `$1`, `$2` ...; a column of a table the body reads wins over a parameter of its name.

`DEFAULT` *default_expr*
: A value for a parameter the call leaves out. The parameters after one with a default need defaults too.

`RETURNS` *rettype*
: The type of the result: one value. `void` for none.

`RETURNS SETOF` *rettype*, `RETURNS TABLE (...)`
: A set-returning function, which a query reads in `FROM`.

`LANGUAGE sql`
: The only language. Another is 42704 (`language "plpgsql" does not exist`).

`AS '`*definition*`'`
: The body, a string: one or more SQL statements, the last of which gives the result. A dollar-quoted string
  (`$$ ... $$`) needs no doubled quotes inside.

`RETURN` *expression*, `BEGIN ATOMIC ... END`
: The body written as SQL, as in the SQL standard.

`STRICT`, `RETURNS NULL ON NULL INPUT`
: The function gives NULL when an argument is NULL, without running.

`IMMUTABLE`, `STABLE`, `VOLATILE`, the other attributes
: Accepted; the volatility words are kept in `pg_proc`.

## Remarks

- A function is written into the query that calls it before the query is planned: a body that is one `SELECT` of an
  expression becomes that expression, and a body that reads tables becomes a subquery. So a function costs about
  what its body would cost written out.
- The body's syntax is checked at `CREATE`; the names it uses are found when it is called.
- `CREATE OR REPLACE` changes a function of the same name and argument types; its result type must stay the same
  (42P13).
- `pg_proc`, `information_schema.routines` and `pg_get_functiondef` list the functions.
- A function may be run by `PUBLIC` until `REVOKE EXECUTE ... FROM PUBLIC` (see [GRANT](grant.md)).

## Differences from PostgreSQL

- **There is no PL/pgSQL, and no `DO`.** Functions and procedures are `LANGUAGE sql` only: `LANGUAGE plpgsql` (or
  any other language) is 42704, and `DO` is a syntax error.
- Where a function can be called in a query:
  - a function whose body reads tables can be given only values as arguments, not a column or a subquery (0A000,
    `the function pay reads tables: it cannot be given a column or a subquery as an argument yet`);
  - a function whose body writes (`INSERT ...; SELECT ...`), or that returns several columns through `OUT`
    parameters, cannot be called in a query (0A000);
  - a set-returning function is read in `FROM` only, not in the select list (42883);
  - named arguments (`f(a => 1)`) are taken by `CALL` only, and `VARIADIC` is read but cannot be called.
- With overloads `add(int, int)` and `add(numeric, numeric)`, `add(2, 3)` calls the `numeric` one; PostgreSQL calls
  the `integer` one.
- The result column of a call is named after its type or expression (`int4`, `numeric`, `?column?`), not after the
  function; give it a name with `AS`.
- `SECURITY DEFINER` is accepted and ignored: a function runs as its caller.
- `ALTER FUNCTION` is not supported.

## Examples

<!--setup: postgresql
CREATE TABLE emp (id int PRIMARY KEY, name text, salary numeric(8,2));
INSERT INTO emp VALUES (1, 'ada', 5200), (2, 'ben', 3100), (3, 'cy', 2900);
-->

The examples use one table:

```sql
CREATE TABLE emp (id int PRIMARY KEY, name text, salary numeric(8,2));
INSERT INTO emp VALUES (1, 'ada', 5200), (2, 'ben', 3100), (3, 'cy', 2900);
```

### A. A function of its arguments

<!-- example: postgresql -->
```sql
CREATE FUNCTION add(a int, b int) RETURNS int LANGUAGE sql AS 'SELECT a + b';
CREATE FUNCTION twice(x int) RETURNS int RETURN x * 2;
SELECT add(2, 3) AS sum, twice(21) AS twice;
SELECT name, twice(id) AS doubled FROM emp ORDER BY id;
```

```text
CREATE FUNCTION
CREATE FUNCTION
 sum | twice
-----+-------
   5 |    42
(1 row)

 name | doubled
------+---------
 ada  |       2
 ben  |       4
 cy   |       6
(3 rows)
```

### B. Defaults, STRICT and dollar quotes

<!-- example: postgresql -->
```sql
CREATE FUNCTION greet(who text DEFAULT 'world') RETURNS text LANGUAGE sql AS $$ SELECT 'hello ' || who $$;
SELECT greet() AS a, greet('ann') AS b;
CREATE FUNCTION next_id(n int) RETURNS int STRICT LANGUAGE sql AS 'SELECT n + 1';
SELECT next_id(NULL) IS NULL AS is_null;
```

```text
CREATE FUNCTION
      a      |     b
-------------+-----------
 hello world | hello ann
(1 row)

CREATE FUNCTION
 is_null
---------
 t
(1 row)
```

### C. A function that reads a table

<!-- example: postgresql -->
```sql
CREATE FUNCTION pay(eid int) RETURNS numeric LANGUAGE sql STABLE
BEGIN ATOMIC
    SELECT salary FROM emp WHERE id = eid;
END;
SELECT pay(1) AS ada, pay(9) AS nobody;
SELECT name, pay(id) FROM emp;
```

```text
CREATE FUNCTION
   ada   | nobody
---------+--------
 5200.00 |
(1 row)

ERROR:  lexdb: the function pay reads tables: it cannot be given a column or a subquery as an argument yet
```

### D. Set-returning functions

<!-- example: postgresql -->
```sql
CREATE FUNCTION paid_over(m numeric) RETURNS SETOF text LANGUAGE sql AS $$
    SELECT name FROM emp WHERE salary > m ORDER BY name
$$;
SELECT * FROM paid_over(3000);
CREATE FUNCTION staff() RETURNS TABLE (id int, name text) LANGUAGE sql AS $$ SELECT id, name FROM emp $$;
SELECT s.name FROM staff() AS s WHERE s.id > 1 ORDER BY s.name;
```

```text
CREATE FUNCTION
 paid_over
-----------
 ada
 ben
(2 rows)

CREATE FUNCTION
 name
------
 ben
 cy
(2 rows)
```

### E. In the catalog

<!-- example: postgresql -->
```sql
SELECT proname, prokind, pronargs FROM pg_proc WHERE proname IN ('add', 'twice', 'pay') ORDER BY proname;
SELECT pg_get_functiondef('twice'::regproc);
```

```text
 proname | prokind | pronargs
---------+---------+----------
 add     | f       |        2
 pay     | f       |        1
 twice   | f       |        1
(3 rows)

                 pg_get_functiondef
----------------------------------------------------
 CREATE OR REPLACE FUNCTION public.twice(x integer)+
  RETURNS integer                                  +
  LANGUAGE sql                                     +
 RETURN x * 2                                      +

(1 row)
```

### F. Errors

<!-- example: postgresql -->
```sql
CREATE FUNCTION one() RETURNS int LANGUAGE plpgsql AS $$ BEGIN RETURN 1; END $$;
DO $$ BEGIN NULL; END $$;
CREATE OR REPLACE FUNCTION twice(x int) RETURNS text RETURN 'x';
CREATE FUNCTION empty() RETURNS int LANGUAGE sql;
```

```text
ERROR:  language "plpgsql" does not exist
ERROR:  syntax error at or near "do"
ERROR:  cannot change return type of existing function
ERROR:  no function body specified
```

### G. Overloads, and the result's name

<!-- example: postgresql -->
```sql
CREATE FUNCTION add(a numeric, b numeric) RETURNS numeric RETURN a + b + 0.5;
SELECT add(2, 3), add(2.0, 3.0);
SELECT twice(2);
```

```text
CREATE FUNCTION
 numeric | numeric
---------+---------
     5.5 |     5.5
(1 row)

 int4
------
    4
(1 row)
```

## See also

[CREATE PROCEDURE](create-procedure.md) · [DROP FUNCTION](drop-function.md) · [CALL](call.md) · [GRANT](grant.md)
