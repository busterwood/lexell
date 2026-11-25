# sysbench OLTP Benchmark

Standard [sysbench](https://github.com/akopytov/sysbench) 1.0.20 OLTP benchmark suite comparing **LexDB** (1 process and 3 read replicas) against **PostgreSQL 18** (4 cores) on one machine.

## Setup

- **Schema & dataset:** `4` tables × `250,000` rows (`1,000,000` rows total, matching `bench/sock/vspg.sh`): `sbtest1..4 (id SERIAL PRIMARY KEY, k INTEGER, c CHAR(120), pad CHAR(60))` with secondary index `k_i(k)`.
- **Workloads:**
  - `oltp_point_select` — single primary-key lookup per event (autocommit)
  - `oltp_read_only` — 10 point lookups + 4 range queries (simple, `SUM`, `ORDER BY`, `DISTINCT ORDER BY`) inside `BEGIN..COMMIT`
  - `oltp_read_write` — `oltp_read_only` + index `UPDATE` + non-index `UPDATE` + `DELETE` + `INSERT` inside `BEGIN..COMMIT`
  - `oltp_write_only` — index `UPDATE` + non-index `UPDATE` + `DELETE` + `INSERT` inside `BEGIN..COMMIT`
  - `oltp_update_index` — single indexed `UPDATE k = k + 1` per event (autocommit)
  - `oltp_update_non_index` — single non-indexed `UPDATE c = ...` per event (autocommit)
- **Concurrency:** `1`, `8`, `32` threads (`--db-ps-mode=auto`, prepared statements over Unix domain sockets).
- **Isolation:** Both databases run durable (`fsync` and `synchronous_commit` on). Every LexDB transaction block runs at `SERIALIZABLE` isolation; PostgreSQL runs at its default `READ COMMITTED`. Serialization retries (`40001`) are reported under `errors`.
- **Hardware pinning:** Servers confined to `SERVER_CPUS` (`0-3`, SMT siblings idle) via transient `systemd-run --user` units; `sysbench` client pinned to `CLIENT_CPUS` (`4-7,12-15`); CPU boost disabled (`SB_BOOST=off`) for fixed-clock repeatability.

## Usage

```bash
bench/sysbench/run.sh /path/to/lexdb /path/to/workdir [TABLES] [TABLE_SIZE] [SECONDS]
```

Environment overrides:
- `SB_MODES="lexdb lexdb3 pg"` — subset of server modes to run
- `SB_TESTS="..."` — subset of sysbench OLTP scripts
- `SB_THREADS="1 8 32"` — thread counts
- `SB_BOOST=off|keep` — fixed clock (`off`, default) or current governor (`keep`)
- `SYSBENCH=/path/to/sysbench` — path to `sysbench` binary with `pgsql` driver
