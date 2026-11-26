# LexDB multi-door driver & ORM compatibility suite

End-to-end verification of real third-party database drivers and ORMs against a live `lexdb` server across all three doors (PostgreSQL, SQL Server / TDS, Oracle / TNS).

## What is tested

| Runtime | Suite | Doors & libraries |
|---|---|---|
| Python | [test_pg_door.py](test_pg_door.py) | `psycopg` 3 (text & `binary=True`, `COPY`, savepoints, `ON CONFLICT`), `asyncpg` (binary scalars, arrays, binary params), `SQLAlchemy` 2 + `Inspector` + `Alembic` autogenerate, `Django` (`migrate`, ORM CRUD/Q/annotate/`bulk_update`, nested `atomic()`, introspection) |
| Python | [test_tds_door.py](test_tds_door.py) | `pymssql` (types, `IDENTITY`, `SCOPE_IDENTITY()`, `#temp`, `OUTPUT INSERTED`, rollback), `SQLAlchemy` 2 (`mssql+pymssql`) + `Inspector` + `Alembic` autogenerate |
| Python | [test_ora_door.py](test_ora_door.py) | `python-oracledb` thin (types, `IDENTITY`, `RETURNING INTO`, CLOB/BLOB, `executemany`, PL/SQL `OUT`, `REF CURSOR`), `SQLAlchemy` 2 (`oracle+oracledb`) + `Inspector` + `Alembic` autogenerate, `Django` Oracle (`migrate`, ORM, savepoints, introspection) |
| .NET | [efcore/Program.cs](efcore/Program.cs) | `Npgsql.EntityFrameworkCore.PostgreSQL` (`EnsureCreated`, `SaveChanges`, `Include`, `Skip`/`Take`, `Sum`, `ExecuteUpdate`/`ExecuteDelete`, rollback), `Microsoft.EntityFrameworkCore.SqlServer` (same), `Oracle.ManagedDataAccess.Core` thin (connect, DDL, params, rollback) |
| Node.js | [node/test_node.mjs](node/test_node.mjs) | `pg` + `Knex`, `mssql` (`tedious`) + `Knex`, `node-oracledb` thin |

## Running

```sh
# Build lexdb and run Python, .NET, and Node.js suites (skips runtimes not installed):
./lexell/tests/lexdb/compat/run.sh

# Run a single runtime or point at an existing lexdb binary:
./lexell/tests/lexdb/compat/run.sh --python
./lexell/tests/lexdb/compat/run.sh --dotnet --lexdb ./lexdb
./lexell/tests/lexdb/compat/run.sh --node
```

Dependencies (Python venv, `.NET` build output, `node_modules`) are installed inside `.cache/` / gitignored subfolders and never pollute `git status`.

For the fast in-process Lexell regression test covering the same protocol/catalog/dialect behaviors without external runtimes, run:

```sh
cd lexell && python3 tests/lexdb.py --compiler compiler/out/lxlc exec_compat
```

See [docs/lexdb/compatibility.md](../../docs/lexdb/compatibility.md) for the full compatibility matrix and known limitations.
