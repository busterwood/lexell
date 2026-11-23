# ALTER ROLE, ALTER USER

Changes a role's options or its name.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
ALTER ROLE name [ WITH ] option [ ... ]
ALTER ROLE name RENAME TO new_name
ALTER USER name [ WITH ] option [ ... ]
ALTER USER name RENAME TO new_name
```

*option* is one of [CREATE ROLE](create-role.md)'s.

## Arguments

*name*
: The role. `ALTER USER` is the same statement as `ALTER ROLE`.

*option*
: `SUPERUSER`, `NOSUPERUSER`, `LOGIN`, `NOLOGIN` and `PASSWORD` change the role; the other options are accepted and
  not kept.

*new_name*
: The role's new name.

## Remarks

- `PASSWORD NULL` takes the password away: the role cannot log in with a password.
- A renamed role keeps its privileges, memberships and objects.
- `ALTER ROLE` is transactional.

## Differences from PostgreSQL

- A role's own settings (`ALTER ROLE ... SET name = value`, `RESET`) are refused (0A000, `lexdb: a role's own
  settings (ALTER ROLE ... SET) are not supported`).
- The options that `CREATE ROLE` does not keep are not kept here either.

## Examples

<!--setup: postgresql
CREATE ROLE ann;
CREATE USER bob PASSWORD 'old';
-->

The examples use two roles:

```sql
CREATE ROLE ann;
CREATE USER bob PASSWORD 'old';
```

### A. Options

<!-- example: postgresql -->
```sql
ALTER ROLE ann WITH LOGIN PASSWORD 'secret';
ALTER USER bob NOLOGIN;
SELECT rolname, rolcanlogin FROM pg_roles WHERE rolname IN ('ann', 'bob') ORDER BY 1;
```

```text
ALTER ROLE
ALTER ROLE
 rolname | rolcanlogin
---------+-------------
 ann     | t
 bob     | f
(2 rows)
```

### B. Rename

<!-- example: postgresql -->
```sql
ALTER ROLE ann RENAME TO anna;
SELECT rolname FROM pg_roles WHERE rolname LIKE 'ann%';
```

```text
ALTER ROLE
 rolname
---------
 anna
(1 row)
```

### C. Errors

<!-- example: postgresql -->
```sql
ALTER ROLE nosuch LOGIN;
ALTER ROLE anna SET search_path = app;
```

```text
ERROR:  role "nosuch" does not exist
ERROR:  lexdb: a role's own settings (ALTER ROLE ... SET) are not supported
```

## See also

[CREATE ROLE](create-role.md) · [DROP ROLE](drop-role.md)
