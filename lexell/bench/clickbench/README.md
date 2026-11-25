# ClickBench (LexDB vs PostgreSQL)

Derived from [ClickHouse/ClickBench](https://github.com/ClickHouse/ClickBench) (`postgresql/create.sql` and `postgresql/queries.sql`, 105-column `hits` table and 43 analytical queries `q0`–`q42`).

## Running

```sh
# Build LexDB (native -O)
lexell/compiler/out/lxlc --native -O -o /tmp/lexdb lexell/cmd/lexdb.lxl

# 1M-row slice (default; fast ~2-3 min full comparison)
lexell/bench/clickbench/run.sh /tmp/lexdb ~/clickbench-1m 1000000 3

# 10M-row slice
lexell/bench/clickbench/run.sh /tmp/lexdb ~/clickbench-10m 10000000 3

# Full ~100M-row dataset (downloads full 16.3 GB hits.tsv.gz)
lexell/bench/clickbench/run.sh /tmp/lexdb ~/clickbench-full all 3
```

## Notes

- Both servers run one at a time on CPUs `0-3` (`CB_CPUS=0-3`), with CPU boost off (`CB_BOOST=off`) for a fixed clock, matching `bench/tpch/run.sh`.
- PostgreSQL runs single-core (`pg1`, `max_parallel_workers_per_gather=0`) and 4-process parallel (`pg4`, `max_parallel_workers_per_gather=3`).
- `compare.py` checks exact MD5 parity against `pg1` on deterministic queries, and checks row counts on top-N/unordered queries (`q18` has no `ORDER BY`; several `LIMIT` queries can tie on equal sort keys).
- Pass `CB_ONLY=lexdb` or `CB_QUERIES=0,1,28` to iterate on specific queries without reloading.
