# CREATE ROLE, CREATE USER

Makes a role: a user who logs in, or a group whose privileges its members share.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
CREATE ROLE name [ [ WITH ] option [ ... ] ]
CREATE USER name [ [ WITH ] option [ ... ] ]

option:
    SUPERUSER | NOSUPERUSER
    | LOGIN | NOLOGIN
    | [ ENCRYPTED ] PASSWORD 'password' | PASSWORD NULL
    | CREATEDB | NOCREATEDB | CREATEROLE | NOCREATEROLE | INHERIT | NOINHERIT
    | REPLICATION | NOREPLICATION | BYPASSRLS | NOBYPASSRLS
    | CONNECTION LIMIT connlimit | VALID UNTIL 'timestamp' | SYSID uid
    | IN ROLE role_name [, ...] | ROLE role_name [, ...] | ADMIN role_name [, ...]
```

## Arguments

*name*
: The role's name. Names beginning with `pg_` are reserved (42939).

`SUPERUSER`
: The role passes every privilege check. `NOSUPERUSER` is the default.

`LOGIN`
: The role may log in. `CREATE USER` is `CREATE ROLE` with `LOGIN`; `CREATE ROLE` gives `NOLOGIN` by default.

`PASSWORD`
: The password that the server checks when it runs with `--auth scram-sha-256` (see [server
  options](../../server-options.md)). It is kept as a SCRAM-SHA-256 verifier. Under `--auth trust`, the default,
  passwords are not checked.

`CREATEDB`, `CREATEROLE`, `INHERIT`, `REPLICATION`, `BYPASSRLS`, `CONNECTION LIMIT`, `VALID UNTIL`, `SYSID`
: Accepted and not kept.

`IN ROLE`, `ROLE`, `ADMIN`
: Accepted and not kept: use [GRANT](grant.md) *role* `TO` *member*.

## Remarks

- Roles belong to the server, not to a schema. `pg_roles`, `pg_user` and `pg_auth_members` list them.
- A role made by `CREATE ROLE` without `LOGIN` is a group: grant it privileges, then grant it to users.
- Every role has the privileges granted to `PUBLIC` and to the roles it is a member of.
- `CREATE ROLE` is transactional.

## Differences from PostgreSQL

- `CREATEDB`, `CREATEROLE`, `INHERIT` and the other options listed as not kept have no effect, and `pg_roles` shows
  `rolcreatedb` and `rolcreaterole` only for superusers.
- `IN ROLE`, `ROLE` and `ADMIN` make no memberships.
- A role named `public` can be made; PostgreSQL refuses the name (42939).
- The bootstrap role `postgres` is not a role that statements can name: `OWNER TO postgres` and `DROP ROLE postgres`
  give 42704 (`role "postgres" does not exist`), though `pg_roles` lists it.

## Examples

### A. A group and users

<!-- example: postgresql -->
```sql
CREATE ROLE readers;
CREATE USER ann WITH PASSWORD 'secret';
CREATE ROLE bob LOGIN;
CREATE ROLE ops SUPERUSER;
GRANT readers TO ann, bob;
SELECT rolname, rolsuper, rolcanlogin FROM pg_roles WHERE rolname IN ('readers', 'ann', 'bob', 'ops') ORDER BY 1;
```

```text
CREATE ROLE
CREATE ROLE
CREATE ROLE
CREATE ROLE
GRANT ROLE
 rolname | rolsuper | rolcanlogin
---------+----------+-------------
 ann     | f        | t
 bob     | f        | t
 ops     | t        | f
 readers | f        | f
(4 rows)
```

### B. Memberships

<!-- example: postgresql -->
```sql
SELECT g.rolname AS role, m.rolname AS member
FROM pg_auth_members a JOIN pg_roles g ON g.oid = a.roleid JOIN pg_roles m ON m.oid = a.member
ORDER BY 1, 2;
```

```text
  role   | member
---------+--------
 readers | ann
 readers | bob
(2 rows)
```

### C. Options that are not kept

<!-- example: postgresql -->
```sql
CREATE USER carol CREATEDB IN ROLE readers;
SELECT rolcreatedb FROM pg_roles WHERE rolname = 'carol';
SELECT count(*) FROM pg_auth_members a JOIN pg_roles m ON m.oid = a.member WHERE m.rolname = 'carol';
```

```text
CREATE ROLE
 rolcreatedb
-------------
 f
(1 row)

 count
-------
     0
(1 row)
```

### D. Errors

<!-- example: postgresql -->
```sql
CREATE ROLE ann;
CREATE ROLE pg_mine;
CREATE ROLE dee WITH FLY;
```

```text
ERROR:  role "ann" already exists
ERROR:  role name "pg_mine" is reserved
ERROR:  unrecognized role option "fly"
```

## See also

[ALTER ROLE](alter-role.md) · [DROP ROLE](drop-role.md) · [GRANT](grant.md) · [SET ROLE](set-role.md)
