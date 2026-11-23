# Catalog: roles and privileges

`pg_roles`, `pg_user`, `pg_auth_members`, and the privilege views of `information_schema`.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
SELECT ... FROM [ pg_catalog. ] pg_roles
SELECT ... FROM [ pg_catalog. ] pg_user
SELECT ... FROM [ pg_catalog. ] pg_auth_members
SELECT ... FROM information_schema.table_privileges
SELECT ... FROM information_schema.role_table_grants
SELECT ... FROM information_schema.routine_privileges
SELECT ... FROM information_schema.role_routine_grants
```

## Views

Each relation has all of PostgreSQL 18's columns. The columns below are the ones lexdb fills in; the others are
NULL, zero, false or empty.

`pg_roles`: one row per role, `postgres` included
: `oid`, `rolname`, `rolsuper`, `rolinherit`, `rolcreaterole`, `rolcreatedb`, `rolcanlogin`, `rolreplication`,
  `rolconnlimit`, `rolbypassrls`. `rolpassword` is NULL, as PostgreSQL shows it to everyone but a superuser
  (`********`).

`pg_user`: one row per role that can log in
: `usename`, `usesysid`, `usecreatedb`, `usesuper`, `userepl`, `usebypassrls`.

`pg_auth_members`: one row per membership (`GRANT role TO role`)
: `oid`, `roleid`, `member`, `grantor`, `admin_option`, `inherit_option`, `set_option`.

`information_schema.table_privileges`, `information_schema.role_table_grants`: one row per privilege on a table
or view
: `grantor`, `grantee`, `table_catalog`, `table_schema`, `table_name`, `privilege_type`, `is_grantable`,
  `with_hierarchy`. The owner holds every privilege, `WITH GRANT OPTION`.

`information_schema.routine_privileges`, `information_schema.role_routine_grants`: one row per `EXECUTE`
privilege
: `grantor`, `grantee` (`PUBLIC` for the default grant), `specific_catalog`, `specific_schema`, `specific_name`,
  `routine_catalog`, `routine_schema`, `routine_name`, `privilege_type`, `is_grantable`.

## Remarks

- `pg_class.relacl`, `pg_namespace.nspacl` and `pg_proc.proacl` hold the same privileges as `aclitem` text
  (`clerk=ar/postgres`: `a` INSERT, `r` SELECT, `w` UPDATE, `d` DELETE, `D` TRUNCATE, `x` REFERENCES, `t`
  TRIGGER, `X` EXECUTE, `U` USAGE, `C` CREATE).
- The `has_..._privilege` functions answer for one role and object (see [catalog functions](functions-catalog.md)).
- psql's `\du` and `\dp` read these relations.

## Differences from PostgreSQL

- `CREATEDB`, `CREATEROLE` and other non-login options of `CREATE ROLE` are read and not kept: `rolcreatedb` and
  `rolcreaterole` stay false.
- `pg_authid`, `pg_has_role`, `information_schema.enabled_roles`, `applicable_roles` and `column_privileges` do not
  exist.
- `table_privileges` lists every table's privileges, not only those of the current user's roles.

## Examples

<!--setup: postgresql
CREATE TABLE orders (no int PRIMARY KEY, total numeric(10,2));
CREATE FUNCTION tax(p numeric) RETURNS numeric LANGUAGE sql AS 'SELECT p * 0.2';
CREATE ROLE clerk LOGIN;
CREATE ROLE staff;
GRANT SELECT, INSERT ON orders TO clerk;
GRANT staff TO clerk;
-->

The examples use these objects:

```sql
CREATE TABLE orders (no int PRIMARY KEY, total numeric(10,2));
CREATE FUNCTION tax(p numeric) RETURNS numeric LANGUAGE sql AS 'SELECT p * 0.2';
CREATE ROLE clerk LOGIN;
CREATE ROLE staff;
GRANT SELECT, INSERT ON orders TO clerk;
GRANT staff TO clerk;
```

### A. Roles and users

<!-- example: postgresql -->
```sql
SELECT rolname, rolsuper, rolcanlogin, rolinherit, rolconnlimit FROM pg_roles ORDER BY rolname;
SELECT usename, usesuper FROM pg_user ORDER BY usename;
```

```text
 rolname  | rolsuper | rolcanlogin | rolinherit | rolconnlimit
----------+----------+-------------+------------+--------------
 clerk    | f        | t           | t          |           -1
 postgres | t        | t           | t          |           -1
 staff    | f        | f           | t          |           -1
(3 rows)

 usename  | usesuper
----------+----------
 clerk    | f
 postgres | t
(2 rows)
```

### B. Membership

<!-- example: postgresql -->
```sql
SELECT pg_get_userbyid(roleid) AS role, pg_get_userbyid(member) AS member, admin_option, inherit_option
FROM pg_auth_members;
```

```text
 role  | member | admin_option | inherit_option
-------+--------+--------------+----------------
 staff | clerk  | f            | t
(1 row)
```

### C. Table privileges

<!-- example: postgresql -->
```sql
SELECT grantee, privilege_type, is_grantable FROM information_schema.table_privileges
WHERE table_name = 'orders' AND grantee = 'clerk' ORDER BY privilege_type;
SELECT relname, relacl FROM pg_class WHERE relname = 'orders';
```

```text
 grantee | privilege_type | is_grantable
---------+----------------+--------------
 clerk   | INSERT         | NO
 clerk   | SELECT         | NO
(2 rows)

 relname |                    relacl
---------+-----------------------------------------------
 orders  | {postgres=arwdDxt/postgres,clerk=ar/postgres}
(1 row)
```

### D. Routine privileges

<!-- example: postgresql -->
```sql
GRANT EXECUTE ON FUNCTION tax(numeric) TO clerk;
SELECT routine_name, grantee, privilege_type FROM information_schema.routine_privileges ORDER BY grantee;
```

```text
GRANT
 routine_name | grantee  | privilege_type
--------------+----------+----------------
 tax          | PUBLIC   | EXECUTE
 tax          | clerk    | EXECUTE
 tax          | postgres | EXECUTE
(3 rows)
```

### E. psql's list of roles

<!-- example: postgresql -->
```sql
\du
```

```text
                       List of roles
 Role name |                  Attributes
-----------+-----------------------------------------------
 clerk     |
 postgres  | Superuser, Create role, Create DB, Bypass RLS
 staff     | Cannot login
```

## See also

[CREATE ROLE](create-role.md) · [GRANT](grant.md) · [REVOKE](revoke.md) · [Catalog functions](functions-catalog.md)
