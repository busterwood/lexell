#!/bin/bash
# commitlat.sh LEXDB_BINARY VSPG_WORKDIR OUTDIR [CLIENTS] [SECONDS] (design/lexdb-benchmarks.md 1.2): lexdb alone on a copy
# of vspg.sh's lexdb data (acct 1M rows) on SERVER_CPUS (0-3), pgbench updates from CLIENT_CPUS (4-7,12-15), 8 clients
# for 20 s by default, every transaction's latency logged (pgbench -l): the commit latency's p50, p99, p99.9 and max.
set -u
BIN=$1; V=$2; S=$3; C=${4:-8}; T=${5:-20}
SERVER_CPUS=${SERVER_CPUS:-0-3}; CLIENT_CPUS=${CLIENT_CPUS:-4-7,12-15}
rm -rf "$S"; mkdir -p "$S/sock" "$S/log"; cp -r "$V/lexdb" "$S/data"
taskset -c "$SERVER_CPUS" "$BIN" "$S/data" 127.0.0.1:5591 "$S/sock" > "$S/srv.log" 2>&1 &
P=$!
for i in $(seq 100); do psql -h "$S/sock" -p 5591 -U test -d test -XAtc 'select 1' >/dev/null 2>&1 && break; sleep 0.2; done
taskset -c "$CLIENT_CPUS" pgbench -n -f "$V/upd.sql" -M prepared -c "$C" -j 4 -T 5 -h "$S/sock" -p 5591 -U test test >/dev/null 2>&1
(cd "$S/log" && taskset -c "$CLIENT_CPUS" pgbench -n -l -f "$V/upd.sql" -M prepared -c "$C" -j 4 -T "$T" -h "$S/sock" -p 5591 -U test test >/dev/null 2>&1)
cat "$S"/log/pgbench_log.* | awk '{print $3}' | sort -n | awk -v c="$C" '{a[NR]=$1} END {
    printf "updates, %d clients: %d commits, latency ms p50 %.2f p99 %.2f p99.9 %.2f max %.2f\n", c, NR, a[int(NR*0.5)]/1000, a[int(NR*0.99)]/1000, a[int(NR*0.999)]/1000, a[NR]/1000}'
kill -TERM $P; wait $P 2>/dev/null
