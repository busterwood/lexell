# DROP USER

Removes a user, and with `CASCADE` the objects of the user's schema.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
DROP USER user [ CASCADE ]
```

## Arguments

`CASCADE`
: Drops the user's tables, views and other objects with the user. Without it, a user who owns objects is
  ORA-01922.

## Remarks

- A user that does not exist is ORA-01918.

## Differences from Oracle

- None known.

## Examples

### A. Drop a user, with and without objects

<!-- example: oracle -->
```sql
CREATE USER ann IDENTIFIED BY pw;
CREATE USER dd IDENTIFIED BY pw;
CREATE TABLE dd.t (a NUMBER);
DROP USER ann;
DROP USER dd;
DROP USER dd CASCADE;
SELECT username FROM all_users WHERE username IN ('ANN', 'DD');
```

```text
User created.

User created.

Table created.

User dropped.

ERROR:
ORA-01922: CASCADE must be specified to drop 'DD'

User dropped.

no rows selected
```

### B. A user that does not exist

<!-- example: oracle -->
```sql
DROP USER nobody;
```

```text
ERROR:
ORA-01918: user 'NOBODY' does not exist
```

## See also

[CREATE USER](create-user.md), [ALTER USER](alter-user.md)
