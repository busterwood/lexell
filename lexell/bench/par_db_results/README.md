# par.map database-kernel results

The raw tables behind [design/par-db-perf.md](../../design/par-db-perf.md),
made on 2026-11-14 on an 8-core/16-thread Ryzen, Linux, `-O`.

| file | what |
|---|---|
| `par_db_kernels.tsv` | `par_db.lxl`: GROUP BY, DISTINCT, hash probes, expressions over 1M rows; 1, 2, 4, 8 threads |
| `par_copy.tsv` | `par_copy.lxl`: the wide 9.118 COPY, split/parse/encode, owned against borrowed fields; 16 chunks |
| `lex_1thread.tsv` | the same queries on lexdb at `main`, one thread: wall and server CPU ms |
| `pg_1core.tsv` | PostgreSQL 18, `max_parallel_workers_per_gather=0` |
| `pg_4proc.tsv` | PostgreSQL 18, `max_parallel_workers_per_gather=3`, `max_parallel_workers=3` |
| `copy.txt` | the wide COPY, lexdb against PostgreSQL, three runs each |
| `queries.txt` | the query list used by `measure.py` and `pgmeasure.py` |
| `pgmeasure.py` | a small wall-time harness for PostgreSQL |

The `LXL_PAR` column is the pool size: 0 is a loop on the calling thread, 1
is 2 threads, 3 is 4 and 7 is 8. `median_ms` drops the first round (lazy
pool start). `user_s` is the process's user and system CPU, from
`getrusage(RUSAGE_CHILDREN)`, for the whole program including reading the
input.
