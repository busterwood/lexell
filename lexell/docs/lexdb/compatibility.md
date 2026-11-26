# Driver & ORM compatibility

LexDB speaks three native wire protocols — PostgreSQL (`pgwire`), SQL Server (`TDS 7.4`), and Oracle (`TNS`/`TTC` thin) — over one shared database. Beyond unit and protocol tests, LexDB ships a live, reproducible multi-language verification suite under [tests/lexdb/compat/](../../tests/lexdb/compat/README.md) that exercises mainstream drivers, ORMs, and migration tools against all three doors.

---

## Verified compatibility matrix

Checked against LexDB on Linux x86-64 (2026-11-26):

### PostgreSQL door (`pgwire`)

| Driver / Framework | Tested version | Verified capabilities | Notes |
|---|---|---|---|
| **`psycopg` 3** | 3.3 | All scalar & array types in text **and** `binary=True` mode, prepared statements, `COPY FROM STDIN`, `executemany`, savepoints, `ON CONFLICT ... RETURNING` | Named server-side SQL cursors (`DECLARE` / `FETCH`) are not yet supported. |
| **`asyncpg`** | 0.32 | Full binary protocol, all scalar types (`int2/4/8`, `float4/8`, `numeric`, `bool`, `text`, `bytea`, `uuid`, `date`, `time`, `timestamp`, `timestamptz`, `json`, `jsonb`), `int[]`/`text[]` arrays, binary parameters, `pg_type`/`pg_range` introspection | Works out of the box with default settings. |
| **`SQLAlchemy` + `Alembic`** | 2.1 / 1.20 | `create_all`, ORM CRUD, `selectinload`/`joinedload`, full `Inspector` reflection (tables, columns, PK, FK, indexes, unique & check constraints), **`Alembic` `autogenerate` clean diff** | Uses `postgresql+psycopg://`. |
| **`Django`** | 6.1 | `manage.py migrate` (`auth`, `contenttypes`, `sessions`), `User`/`Group` ORM CRUD, `Q`, `annotate`, `Lower`, `Count`, `bulk_update`, nested `transaction.atomic()` savepoints, schema introspection | Standard `django.db.backends.postgresql`. |
| **`Npgsql` + `Entity Framework Core`** | 9.x | `EnsureCreated`, `SaveChanges` (parent + children), LINQ `Include`, `OrderBy`/`Skip`/`Take`, `Sum`, `ExecuteUpdate`, `ExecuteDelete`, transaction rollback | Works with default connection string. |
| **`pg` (`node-postgres`) + `Knex`** | 8.x / 3.1 | `createTable`, `hasTable`, `columnInfo`, batch `insert().returning()`, `where`/`orderBy`, transaction rollback | — |
| **`pgjdbc`** / **`psql`** / **`pg_restore`** | 42.7 / 18.6 | Binary parameters & results, `COPY`, `\d` / `\dt` / `\copy`, `pg_dump` / `pg_restore` (`-Fp`, `-Fc`, `-Ft`, `-Fd`) | See [PostgreSQL door](connect/postgresql.md) and [Restoring PostgreSQL backups](pg-restore.md). |

### SQL Server door (`TDS 7.4`)

| Driver / Framework | Tested version | Verified capabilities | Notes |
|---|---|---|---|
| **`Microsoft.Data.SqlClient` + `Entity Framework Core`** | 9.x | `EnsureCreated`, `SaveChanges` (including `MERGE ... OUTPUT INSERTED`), LINQ `Include`, `OrderBy`, `OFFSET`/`FETCH`, `Sum`, `ExecuteUpdate`, `ExecuteDelete`, transaction rollback | Use `Encrypt=False` unless `--tls-cert` is configured. |
| **`pymssql`** | 2.4 | Parameterized queries, all core types (`INT`, `BIGINT`, `DECIMAL`, `BIT`, `NVARCHAR`, `VARBINARY`, `DATE`, `DATETIME2`), `IDENTITY` + `SCOPE_IDENTITY()`, `#temp` tables, `OUTPUT INSERTED`, commit/rollback | — |
| **`SQLAlchemy` + `Alembic`** | 2.1 / 1.20 | `create_all`, ORM CRUD, `OFFSET ... FETCH`, `Inspector` reflection (tables, columns, PK, FK, indexes including unique indexes), **`Alembic` `autogenerate` clean diff** | Uses `mssql+pymssql://`. (SQLAlchemy's `mssql` dialect itself leaves `get_unique_constraints` and `get_check_constraints` unimplemented.) |
| **`mssql` (`tedious`) + `Knex`** | 11.x / 3.1 | `createTable`, `hasTable`, `columnInfo`, `insert().returning()`, queries, transaction rollback | — |
| **`mssql-jdbc`** | 13.6 | Prepared batches, `SQLServerBulkCopy`, `DateTimeOffset`, transaction rollback | See [SQL Server door](connect/sqlserver.md). |

### Oracle door (`TNS` / `TTC` thin)

| Driver / Framework | Tested version | Verified capabilities | Notes |
|---|---|---|---|
| **`python-oracledb` (thin)** | 26.2 | All core types (`NUMBER`, `BINARY_DOUBLE`, `VARCHAR2`, `CLOB`, `BLOB`, `DATE`, `TIMESTAMP`, `TIMESTAMPTZ`), `IDENTITY`, `RETURNING INTO`, `executemany`, PL/SQL `OUT` binds, `REF CURSOR` | Pure thin mode (no Instant Client required). |
| **`SQLAlchemy` + `Alembic`** | 2.1 / 1.20 | `create_all`, `Identity()`, ORM CRUD, `OFFSET`/`FETCH`, full `Inspector` reflection (including `ALL_CONS_COLUMNS` check constraints), **`Alembic` `autogenerate` clean diff** | Uses `oracle+oracledb://`. |
| **`Django`** | 6.1 | `manage.py migrate` (`auth`, `contenttypes`, `sessions`), `User`/`Group` ORM CRUD (including `NUMBER(1)` boolean binds & `LIKEC` string searches), `bulk_update`, nested `transaction.atomic()` savepoints, full introspection (`USER_JSON_COLUMNS`, `= ANY(...)`) | Standard `django.db.backends.oracle`. |
| **`Oracle.ManagedDataAccess.Core` (.NET thin)** | 23.x | TNS/TTC thin handshake, auth, DDL, parameterized `INSERT`/`SELECT`, aggregates, transaction commit/rollback | EF Core Oracle's `SaveChanges()` batch wrapper emits PL/SQL collection types (`TYPE ... IS TABLE OF`), which are not yet supported; direct ADO.NET / Dapper and EF Core reads/DDL work. |
| **`node-oracledb` (thin)** | 6.x | Thin connect, `IDENTITY`, named/positional binds, `RETURNING INTO`, transaction rollback | Knex's Oracle `increments()` emits `CREATE TRIGGER`, which is not yet supported. |
| **`ojdbc11`** / **`SQLcl`** | 23.26 | Array DML, PL/SQL `OUT` binds, TCPS, `INFO`/`DDL` commands | See [Oracle door](connect/oracle.md). |

---

## Running the verification suite

### 1. Live multi-language suite (Python, .NET, Node.js)

The suite in [tests/lexdb/compat/](../../tests/lexdb/compat/README.md) compiles `lexdb`, starts fresh isolated instances for each door, and runs every driver and ORM test above:

```sh
# Run all available runtimes (Python, .NET, Node.js):
./lexell/tests/lexdb/compat/run.sh

# Or target a single ecosystem:
./lexell/tests/lexdb/compat/run.sh --python
./lexell/tests/lexdb/compat/run.sh --dotnet
./lexell/tests/lexdb/compat/run.sh --node
```

### 2. Fast in-process regression suite

All catalog views, GUCs, collation rules, dialect syntax (`LIKEC`, `= ANY (...)`, T-SQL `UNION ORDER BY`), and type coercions required by these ORMs are also locked down in the zero-dependency Lexell regression test [exec_compat.lxl](../../tests/lexdb/run/exec_compat.lxl):

```sh
cd lexell && python3 tests/lexdb.py --compiler compiler/out/lxlc exec_compat
```

---

## Known remaining ecosystem gaps

- **PostgreSQL door:** SQL server-side cursors (`DECLARE ... CURSOR FOR` / `FETCH` / `CLOSE`), `LANGUAGE plpgsql` / `DO` blocks, and `CREATE TRIGGER` (see [KNOWN-ISSUES.md](KNOWN-ISSUES.md)).
- **Oracle door:** PL/SQL collection types (`TYPE ... IS TABLE OF`, used by EF Core Oracle `SaveChanges()` batching) and `CREATE TRIGGER` (used by Knex Oracle `increments()`).
- **SQL Server door:** `Encrypt=strict` (TDS 8.0) and Windows/Kerberos/Entra authentication (use SQL auth with `Encrypt=False` or `--tls-cert`).

## See also

- [Connecting through the PostgreSQL door](connect/postgresql.md)
- [Connecting through the SQL Server door](connect/sqlserver.md)
- [Connecting through the Oracle door](connect/oracle.md)
- [Known issues](KNOWN-ISSUES.md)
