# DROP FUNCTION, DROP PROCEDURE, DROP ROUTINE

Removes functions or procedures.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
DROP FUNCTION [ IF EXISTS ] name [ ( [ [ argmode ] [ argname ] argtype [, ...] ] ) ] [, ...] [ CASCADE | RESTRICT ]
DROP PROCEDURE [ IF EXISTS ] name [ ( [ [ argmode ] [ argname ] argtype [, ...] ] ) ] [, ...] [ CASCADE | RESTRICT ]
DROP ROUTINE [ IF EXISTS ] name [ ( [ [ argmode ] [ argname ] argtype [, ...] ] ) ] [, ...] [ CASCADE | RESTRICT ]
```

## Arguments

`IF EXISTS`
: A routine that does not exist is skipped with a notice.

*name*
: The routine, optionally schema-qualified. Without an argument list, the name must belong to one routine only
  (42725 otherwise).

*argtype*
: The argument types that pick one of several overloads. `OUT` parameters are left out of them.

`DROP ROUTINE`
: Drops a function or a procedure.

`CASCADE`, `RESTRICT`
: Accepted.

## Remarks

- `DROP FUNCTION` of a procedure, or `DROP PROCEDURE` of a function, finds nothing (42883).
- Only the owner or a superuser may drop a routine.
- `DROP` is transactional.

## Differences from PostgreSQL

None known.

## Examples

<!--setup: postgresql
CREATE FUNCTION add(a int, b int) RETURNS int RETURN a + b;
CREATE FUNCTION add(a numeric, b numeric) RETURNS numeric RETURN a + b;
CREATE FUNCTION twice(x int) RETURNS int RETURN x * 2;
CREATE PROCEDURE noop() LANGUAGE sql AS 'SELECT 1';
-->

The examples use these routines:

```sql
CREATE FUNCTION add(a int, b int) RETURNS int RETURN a + b;
CREATE FUNCTION add(a numeric, b numeric) RETURNS numeric RETURN a + b;
CREATE FUNCTION twice(x int) RETURNS int RETURN x * 2;
CREATE PROCEDURE noop() LANGUAGE sql AS 'SELECT 1';
```

### A. Overloads

<!-- example: postgresql -->
```sql
DROP FUNCTION add;
DROP FUNCTION add(int, int);
DROP FUNCTION add, twice;
```

```text
ERROR:  function name "add" is not unique
DROP FUNCTION
DROP FUNCTION
```

### B. Procedures and DROP ROUTINE

<!-- example: postgresql -->
```sql
DROP FUNCTION noop;
DROP ROUTINE noop;
DROP PROCEDURE IF EXISTS noop;
```

```text
ERROR:  could not find a function named "noop"
DROP ROUTINE
NOTICE:  procedure noop() does not exist, skipping
DROP PROCEDURE
```

## See also

[CREATE FUNCTION](create-function.md) · [CREATE PROCEDURE](create-procedure.md)
