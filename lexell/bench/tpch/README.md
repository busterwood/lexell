# TPC-H, derived, for lexdb against PostgreSQL

The 22 TPC-H queries at the specification's substitution values, over dbgen
data at one scale factor, run against lexdb and PostgreSQL on the same
machine. This is **derived from TPC-H, not an audited TPC result**: there
are no refresh functions (RF1/RF2), no full-disclosure report and no audit.
Do not publish a number from here as a "TPC-H result"; say "TPC-H-derived,
dbgen SFn, unaudited".

The point is external comparability and optimizer coverage: the 22 queries
have the joins, correlated subqueries, `CASE`, date arithmetic and decimal
aggregates that `bench/sock`'s five aggregates and the 35-query analytic
suite in `~/Work/lexdb-bench/hp` do not.

## Files

| file | what |
|---|---|
| `schema.sql` | the TPC-H tables, primary keys, no foreign keys |
| `queries/q1.sql` … `q22.sql` | the 22 queries, fixed substitution values |
| `fetch.sh` | clone and build dbgen (tpch-kit, pinned commit) |
| `run.sh` | generate, load, warm, time, compare; one server at a time |
| `bench.py` | times one server's queries, writes a TSV |
| `compare.py` | the lexdb/PostgreSQL table and geometric means |

## Run it

```sh
lexell/compiler/build.sh
lexell/compiler/out/lxlc lexell/cmd/lexdb.lxl -o /tmp/lexdb

W=~/tpch
lexell/bench/tpch/fetch.sh "$W/tpch-kit"
lexell/bench/tpch/run.sh /tmp/lexdb "$W" 1 3
cat "$W/out/summary.md"
```

`run.sh LEXDB_BINARY WORKDIR [SCALE] [RUNS]` loads and times lexdb, then
PostgreSQL on one core (`pg1`), then PostgreSQL at four processes (`pg4`),
stopping each server before the next. SCALE 1 is about 1 GB of data and
6M `lineitem` rows; 10 is about 10 GB and 60M. RUNS is the number of timed
runs after one warm run (default 3). The first run builds both data
directories; later runs reuse `WORKDIR/lexdb` and `WORKDIR/pg` and only
time.

Before running, check the machine is quiet (the project's rule: load under
1, one benchmark at a time). The suite uses the fixed unit names
`tpch-lexdb` and `tpch-pg` and ports 5598/5599, so only one `run.sh` at a
time.

`TPCH_CHECK_ONLY=1` resolves dbgen, PostgreSQL and the queries, prints the
plan and exits without generating, starting or measuring anything.

## What is measured

- **Wall:** psql's `\timing` around the query, not around psql's start-up.
  For q15 (which creates and drops a view around its select), the largest
  statement time; the view DDL is not in the figure.
- **CPU:** the server's cgroup (`CPUUsageNSec` of its transient systemd
  unit) across the same psql call, so it includes any checkpoint or
  background work that lands in the query.
- **Load:** `\copy` of each `dbgen` table through psql, per table, then
  `ANALYZE` (PostgreSQL: `VACUUM (ANALYZE)`), timed separately.
- **Runs:** one unrecorded warm run per query, then RUNS timed runs; the
  TSV keeps median/min/max. Every run's row count and MD5 are checked
  against the warm run; a failure or a changed result is a finding, not a
  stopped run. Each run is a fresh psql session, so no session state or
  plan cache carries over.

Both servers are confined to `TPCH_CPUS` (default `0-7`), half of this
16-thread machine, leaving the other half for everything else. They run one
at a time, so each sees the same set. Neither is CPU-capped by default;
`LEXDB_CPU_QUOTA` and `PG_CPU_QUOTA` add a quota on top. lexdb is
deliberately **not** capped to one core: its SQL execution is one thread,
but checkpoint encode runs on the `par.map` pool (`LEXDB_CKPT_POOL=1` on
the checkpoint branch) and its I/O helpers use other cores. A 100% quota
would make the pool's threads contend for one core and measure an
artificial server, not lexdb. PostgreSQL gets `shared_buffers=12GB`;
`LEXDB_CPU_QUOTA=400%` plus `LXL_PAR=3` gives lexdb the same four-way
budget as PostgreSQL's leader + 3 workers, for a separately reported run.
lexdb's cache defaults to a quarter of RAM; `LEXDB_CACHE_MB` passes
through, as do `LEXDB_CKPT_POOL` and `LXL_PAR` (systemd-run does not
inherit them). Both are warm.

TPC-H is read-only: after the load there is no new log, so checkpoints are
driven by the load rather than the queries (unless the checkpoint change
adds time-driven ones). The parallel checkpoint work therefore shows in the
load table. Add RF1/RF2 or concurrent writes and it enters the query phase
too. The `pg1` column sets
`max_parallel_workers_per_gather=0`; `pg4` sets it to 3 with
`max_parallel_workers=3`.

Output: `WORKDIR/out/lexdb.tsv`, `pg1.tsv`, `pg4.tsv` (one row per query:
name, rows, median/min/max wall ms, median/min/max CPU ms, MD5, status),
`load-*.tsv` and `analyze-*.ms`, `config.txt` (the quotas, buffers and
versions actually used), and `summary.md` / `summary.txt`.

## Options

| env | default | what |
|---|---|---|
| `TPCH_ONLY` | `lexdb,pg1,pg4` | modes to run, comma or space separated |
| `TPCH_DBGEN` | `WORKDIR/tpch-kit/dbgen/dbgen` | dbgen binary (or its kit directory) |
| `TPCH_QUERIES` | all | query numbers, e.g. `3,5,15` |
| `PG_SHARED_BUFFERS` | `12GB` | PostgreSQL `shared_buffers` |
| `QUERY_TIMEOUT` | `900` | seconds per query; lexdb cancels on the server, psql gets 30 s more |
| `TPCH_CPUS` | `0-7` | CPUs both servers are confined to; empty for none |
| `LEXDB_CACHE_MB` | lexdb's default | passed to lexdb |
| `LEXDB_CPU_QUOTA` | unset | lexdb's cgroup quota; `400%` budget-matches PG |
| `PG_CPU_QUOTA` | unset | PostgreSQL's cgroup quota; unset for none |
| `LEXDB_CKPT_POOL` | lexdb's default | `1` enables the parallel checkpoint encode on the checkpoint branch |
| `LXL_PAR` | lexdb's default | par.map threads (`0` runs the caller's thread only) |
| `POSTGRES` | `command -v postgres` | PostgreSQL server binary |
| `LEXDB_PORT`, `PG_PORT` | `5598`, `5599` | ports |

Use one `WORKDIR` per scale factor; `run.sh` refuses a workdir that already
has a different `sf*`. To reload a database, remove its directory and
`.loaded` marker:

```sh
rm -rf "$W/lexdb" "$W/lexdb.loaded"
```

## Caveats

- One textual adaptation: the specification's queries write `interval '3'
  month`; lexdb's parser takes the unit inside the string, so the query
  files say `interval '3 months'`. The semantics are identical. The
  alternative is extending lexdb's parser to PostgreSQL's trailing-unit
  form.
- lexdb query sessions set `max_statement_mem = 0`. The server's default
  of 256 MB is too small for q13 and q18 at SF1; the existing load tests do
  the same. PostgreSQL has no such setting.
- q19 is a known optimizer stressor: at `04fa4b80` lexdb plans its
  OR-of-three-ANDs as a full scan of `lineitem` followed by a cross join
  against `part`, so it does not finish. `QUERY_TIMEOUT` cancels it and
  records a failure; a first pass with 120 s is reasonable. Do not read a
  timeout as a hardware limit.
- Fixed parameters only. qgen varies the substitution values between runs;
  here every run is the same SQL, the usual choice for a first comparison.
- No RF1/RF2 refresh functions. This measures the query half of TPC-H.
- No foreign keys: the spec has them, but they do not affect a plan after
  the load and checking them on 60M rows would measure the load. Say so if
  the schema is described.
- Checksums can differ on decimal formatting even when the values agree;
  the summary marks those `different result` rather than asserting a bug.
  Compare the values with a separate query before treating a difference as
  a correctness finding.
- The output of every query is sent to psql; it is at most 100 rows per
  query (q2, q3, q10, q18, q21 have `limit 100`), so this is small, but it
  is part of the wall time.
- A timed-out psql is killed; whether the server stops the statement is the
  server's business. Check the target's `statement_timeout` before using a
  short `QUERY_TIMEOUT`.

## Provenance and license

The query text in `queries/` is the TPC-H specification's, copied from
Apache DataFusion's `benchmarks/queries` (which publishes the standard
queries with their usual substitution literals). TPC-H and its queries are
the Transaction Processing Performance Council's; they are included here
for benchmarking and are not covered by this repository's Apache-2.0
license. `fetch.sh` downloads the TPC's dbgen through Greg Rahn's tpch-kit
and does not vendor it. The tpch-kit change that matters here is that its
dbgen omits the trailing `|`; `run.sh` strips it anyway so an official
dbgen also loads.
