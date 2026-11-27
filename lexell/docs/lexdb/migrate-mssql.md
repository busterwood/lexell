# Migrating from SQL Server (and dumping LexDB TDS) with `lexmigrate`

`lexmigrate` is a native, zero-driver migration, dump, and restore CLI written in Lexell that speaks **SQL Server's TDS 7.4 wire protocol and T-SQL dialect** end-to-end.

Because LexDB has a native SQL Server door (`--tds`), migrating through TDS instead of converting to PostgreSQL SQL preserves everything SQL Server applications rely on:

- **SQL Server collations** (`SQL_Latin1_General_CP1_CI_AS`, `Latin1_General_CS_AS`, etc. — in LexDB, collations live in the SQL Server door)
- **Native SQL Server types** (`tinyint`, `smallint`, `int`, `bigint`, `bit`, `decimal`/`numeric`, `money`/`smallmoney`, `real`, `float`, `char`/`varchar(n|max)`, `nchar`/`nvarchar(n|max)`, `text`/`ntext`, `binary`/`varbinary(n|max)`, `image`, `date`, `time(p)`, `datetime`, `smalldatetime`, `datetime2(p)`, `datetimeoffset(p)`, `uniqueidentifier`, `xml`, and `rowversion` mapped to `varbinary(8)`)
- **`IDENTITY(seed, increment)`** columns (values preserved via TDS bulk load, sequence automatically advanced past the maximum loaded ID)
- **Defaults, `KEEP_NULLS`, and computed columns** (`PERSISTED` and virtual)
- **Constraints and indexes**: `PRIMARY KEY`, `UNIQUE`, `CHECK` (including `WITH NOCHECK` / disabled constraints), `FOREIGN KEY` (including self-references, cycles, `ON DELETE`/`ON UPDATE` actions, and disabled/untrusted FKs), `DESC`, `INCLUDE (...)`, and filtered `WHERE ...` indexes
- **Sequences, table types, views (including `WITH SCHEMABINDING` indexed views), and T-SQL functions/procedures** (replayed verbatim from `sys.sql_modules`)
- **Works against both real SQL Server (2019 / 2022 / 2025) and LexDB's own `--tds` endpoint** (so it also serves as a logical backup/export tool for LexDB)

---

## Build

```sh
lexell/compiler/out/lxlc lexell/cmd/lexmigrate.lxl -O -o lexmigrate
```

No ODBC driver, JDBC runtime, or `sqlcmd`/`bcp` installation is required.

---

## Quick start

### 1. Inspect a source SQL Server database (dry run)

```sh
./lexmigrate mssql inspect \
  --from "Server=sql.example.com,1433;Database=appdb;UID=sa;PWD=...;Encrypt=yes;TrustServerCertificate=yes"
```

Prints an object inventory (schemas, table types, sequences, tables, constraints, indexes, views, routines, triggers) and a compatibility report flagging alias-type unfoldings, CLR objects, or unsupported column types before touching anything.

### 2. Direct live migration (`SQL Server → LexDB`)

Streams rows straight from source TDS (`sqlserver.stream`) into target LexDB TDS bulk copy (`INSERT BULK ... WITH (KEEP_NULLS)`) in fixed-size batches — constant memory, binary end-to-end, no temporary disk space:

```sh
# Start LexDB with its SQL Server (TDS) door enabled
./lexdb ./data 127.0.0.1:5433 --tds 127.0.0.1:1433

# Stream schema + data + post-DDL + row-count verification
./lexmigrate mssql migrate \
  --from "Server=sql.example.com,1433;Database=appdb;UID=sa;PWD=...;Encrypt=yes;TrustServerCertificate=yes" \
  --to   "Server=127.0.0.1,1433;Database=lexdb;UID=sa;PWD=x;Encrypt=no"
```

> [!TIP]
> To keep passwords out of shell history, set `LEXMIGRATE_FROM` and `LEXMIGRATE_TO` in the environment and omit `--from` / `--to`.

### 3. Dump to a portable bundle and restore later

Use `dump` + `restore` for offline transfers, air-gapped environments, inspectable/editable T-SQL DDL, or logical backups of a LexDB server:

```sh
# Dump from SQL Server (or from LexDB's --tds endpoint)
./lexmigrate mssql dump \
  --from "Server=sql.example.com,1433;Database=appdb;UID=sa;PWD=...;Encrypt=yes;TrustServerCertificate=yes" \
  --out  ./appdb_dump

# Restore into a fresh LexDB
./lexmigrate mssql restore \
  --in ./appdb_dump \
  --to "Server=127.0.0.1,1433;Database=lexdb;UID=sa;PWD=x;Encrypt=no"
```

#### Dump bundle layout

```text
appdb_dump/
├── manifest.json                 # Source metadata, table list, row counts, warnings
├── report.txt                    # Human-readable compatibility report
├── 01_pre.sql                    # Native T-SQL: schemas, table types, sequences, tables (GO-delimited)
├── 02_post.sql                   # Native T-SQL: UNIQUE, indexes, CHECK, FK, views, indexed views, procs/funcs, sequence restarts
└── data/
    ├── 1_dbo_customers.lxrd.zst  # Streaming binary row file (zstd-compressed; --no-compress writes .lxrd)
    └── 2_dbo_orders.lxrd.zst
```

Because `01_pre.sql` and `02_post.sql` are plain `GO`-delimited T-SQL, you can inspect or hand-edit schema adjustments before running `restore`.

---

## Command-line options

| Option | Commands | Description |
|---|---|---|
| `--from DSN` | `inspect`, `migrate`, `dump` | Source SQL Server or LexDB TDS connection string (fallback: `LEXMIGRATE_FROM`). |
| `--to DSN` | `migrate`, `restore` | Target LexDB TDS connection string (fallback: `LEXMIGRATE_TO`). |
| `--out DIR` | `dump` | Output directory for the dump bundle. |
| `--in DIR` | `restore` | Input dump bundle directory. |
| `--schema NAME` | `inspect`, `migrate`, `dump` | Include only objects in this schema (repeatable). |
| `--table [S.]NAME` | `inspect`, `migrate`, `dump` | Include only this table (repeatable; bare names default to `dbo`). |
| `--exclude-table [S.]NAME` | `inspect`, `migrate`, `dump` | Exclude this table (repeatable). |
| `--schema-only` | `migrate`, `dump`, `restore` | Transfer/emit DDL only, skipping table rows. |
| `--data-only` | `migrate`, `restore` | Transfer table rows only, skipping DDL. |
| `--batch-size N` | `migrate`, `dump`, `restore` | Rows per streaming batch (default: `2000`). |
| `--no-compress` | `dump` | Write uncompressed `.lxrd` files instead of `.lxrd.zst`. |
| `--no-verify` | `migrate`, `restore` | Skip post-load `COUNT(*)` verification across every migrated table. |
| `--skip-unsupported` | `inspect`, `migrate`, `dump` | Omit unsupported column types (e.g., `hierarchyid`, `geography`, `geometry`, `sql_variant`) instead of aborting. |
| `--continue-on-error` | `migrate`, `restore` | Collect DDL/module errors and finish remaining objects rather than stopping at the first error. |
| `-v`, `--verbose` | `migrate`, `restore` | Print every executed DDL batch. |

---

## How SQL Server-specific features are handled

- **User-defined alias types (`CREATE TYPE dbo.ShortName FROM nvarchar(50)`):** Automatically unfolded to their underlying SQL Server system type and logged as an `[INFO]` note in the report.
- **`rowversion` / `timestamp` columns:** Mapped to `varbinary(8)` so the raw 8-byte values are preserved verbatim during migration (logged as `[INFO]`).
- **DML Triggers:** Migrated in post-data DDL (`02_post.sql` / `applyPostSchema`) after data loading and view/routine creation, preserving `AFTER` and `INSTEAD OF` triggers (on tables and views) and disabled state (`DISABLE TRIGGER`).
- **Synonyms, CLR objects, and XML/spatial/columnstore indexes:** Detected from `sys.objects` and `sys.indexes`, skipped cleanly, and listed in the compatibility report (`[WARN]`).
- **Unsupported column types (`hierarchyid`, `geography`, `geometry`, `sql_variant`, CLR UDTs):** Flagged as `[ERROR]` and abort before modifying the target unless `--skip-unsupported` is passed, in which case those columns are omitted with a `[WARN]`.
- **View and routine dependencies:** Post-data DDL runs constraints and table indexes first, then views (with automatic multi-pass dependency resolution), then indexed-view indexes (clustered first), then functions/procedures (multi-pass), and finally `ALTER SEQUENCE ... RESTART WITH` to restore exact sequence positions.
- **Migrating from PostgreSQL instead?** Use standard `pg_dump` / `pg_restore` directly over LexDB's PostgreSQL door — see [Restoring PostgreSQL backups](pg-restore.md).
