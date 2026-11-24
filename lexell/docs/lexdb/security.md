# Security: logins, roles and privileges

Who may connect, and what each login may do, in each door.

## Logins

- **`--auth trust`** (the default): any user name logs in over TCP, without a password check. Keep TCP listeners on
  loopback until you have set passwords.
- **`--auth scram-sha-256`**: the password is checked against the stored password of the role. `--auth-local` sets
  the method for Unix socket logins separately.
- **TLS:** `--tls-cert` and `--tls-key` make every door offer TLS; `--require-tls` refuses TCP logins without it.
  See [server options](server-options.md#authentication-and-tls).

The three doors share one set of roles. A role's password, set in any door, works in all three.

| Door | Make a login | Notes |
|---|---|---|
| PostgreSQL | `CREATE ROLE app LOGIN PASSWORD 'secret'` | Under `trust`, a name that is not a role has superuser rights. Under `scram-sha-256` the role needs `LOGIN` and a password (SCRAM-SHA-256; `md5` is not offered). |
| SQL Server | `CREATE ROLE app LOGIN PASSWORD 'secret'` (PostgreSQL's form, taken in this door) or `CREATE USER` | There is no `CREATE LOGIN`. SQL authentication only: Windows and Entra logins are refused. |
| Oracle | `CREATE USER app IDENTIFIED BY secret` then `GRANT CREATE SESSION TO app` | A user is a schema, made at its first login. Under `trust`, a user with no password logs in with its own name as the password. `SYS` and `AS SYSDBA` are refused. |

Reference pages: [CREATE ROLE](sql/postgresql/create-role.md) (PostgreSQL), [CREATE USER](sql/tsql/create-user.md) and
[CREATE ROLE](sql/tsql/create-role.md) (T-SQL), [CREATE USER](sql/oracle/create-user.md) and
[CREATE ROLE](sql/oracle/create-role.md) (Oracle).

## Privileges

Privileges are on objects and are given with `GRANT` and taken back with `REVOKE`:

| Door | Pages | What is taken |
|---|---|---|
| PostgreSQL | [GRANT](sql/postgresql/grant.md), [REVOKE](sql/postgresql/revoke.md) | `SELECT`, `INSERT`, `UPDATE`, `DELETE` and the other table privileges, `USAGE` on schemas and sequences, and role membership. |
| SQL Server | [GRANT](sql/tsql/grant.md), [REVOKE](sql/tsql/revoke.md) | Object permissions (`ON [OBJECT::]name`) and role membership. There is no `DENY`. |
| Oracle | [GRANT](sql/oracle/grant.md), [REVOKE](sql/oracle/revoke.md) | Object privileges (`SELECT`, `INSERT`, `UPDATE`, `DELETE`, `REFERENCES`; `ALL`), a few system privileges (`CREATE SESSION`, `CONNECT`, `DBA`), roles. A column list is not supported. |

- A role can be a member of other roles; the member has their privileges.
- What the catalog shows: PostgreSQL's `pg_roles` and the `information_schema` privilege views; SQL Server's
  `sys.database_principals`, `sys.server_principals` and `sys.database_permissions`
  ([catalog](sql/tsql/catalog-security.md)); Oracle's `USER_TAB_PRIVS` and `ALL_USERS`
  ([data dictionary](sql/oracle/data-dictionary-system.md)).

## What is not there

- `DENY` and `CREATE LOGIN` in the SQL Server door, and a column list in the Oracle door's `GRANT`.
- The differences in what each catalog lists are in the "Differences" sections of the pages above and in
  [known issues](KNOWN-ISSUES.md).
