#!/bin/bash
# vsrep.sh LEXDB_BINARY VSPG_WORKDIR OUTDIR (design/lexdb-benchmarks.md; VSPG_WORKDIR: one bench/sock/vspg.sh made): lexdb with 3 read replicas (--replicas 3, Unix socket) on a copy of
# vspg.sh's lexdb data (acct 1M rows): pgbench point selects on the replicas' shared socket at 1, 8, 32 clients (10 s),
# then 8 clients updating on the master with 24 selecting on the replicas (10 s), then the lag probe (probe2.py) idle
# (5 s) and under that mixed load (20 s). Server CPU is every lexdb process's (utime + stime).
# CPUs (vspg.sh's): lexdb and its replicas on SERVER_CPUS (0-3, their SMT siblings idle), pgbench and the probe on
# CLIENT_CPUS (4-7,12-15).
set -u
BIN=$1; V=$2; S=$3; L=$(dirname "$(realpath "$0")")
SERVER_CPUS=${SERVER_CPUS:-0-3}; CLIENT_CPUS=${CLIENT_CPUS:-4-7,12-15}
pin() { taskset -c "$CLIENT_CPUS" "$@"; }
rm -rf "$S"; mkdir -p "$S/sock"; cp -r "$V/lexdb" "$S/data"; cp "$V/sel.sql" "$V/upd.sql" "$S/"
taskset -c "$SERVER_CPUS" "$BIN" "$S/data" 127.0.0.1:5580 "$S/sock" --replicas 3 > "$S/srv.log" 2>&1 &
SUP=$!
for i in $(seq 100); do psql -h "$S/sock" -p 5581 -U test -d test -XAtc 'select 1' >/dev/null 2>&1 && break; sleep 0.2; done
psql -h "$S/sock" -p 5580 -U test -d test -XAtqc "create table if not exists lagm (id int primary key, n bigint); insert into lagm values (1, 0) on conflict (id) do nothing"
sleep 1
cpu() { local t=0 p; for p in $(pgrep -f "$S/data"); do t=$((t + $(awk '{print $14+$15}' /proc/$p/stat 2>/dev/null || echo 0))); done; echo $t; }
pin pgbench -n -f "$S/sel.sql" -M prepared -c 32 -j 8 -T 8 -h "$S/sock" -p 5581 -U test test >/dev/null 2>&1
for c in 1 8 32; do
  j=$c; [ $j -gt 8 ] && j=8
  c0=$(cpu); tps=$(timeout 30 taskset -c "$CLIENT_CPUS" pgbench -n -f "$S/sel.sql" -M prepared -c $c -j $j -T 10 -h "$S/sock" -p 5581 -U test test 2>&1 | awk '/^tps/{print int($3)}'); c1=$(cpu)
  echo "sel replicas=3 clients $c: $tps/s, server cpu/op $(awk -v d=$((c1-c0)) -v t=$tps 'BEGIN{printf "%.2f", d*10000/(t*10)}') us"
done
(timeout 30 taskset -c "$CLIENT_CPUS" pgbench -n -f "$S/upd.sql" -M prepared -c 8 -j 4 -T 10 -h "$S/sock" -p 5580 -U test test 2>&1 | awk '/^tps/{print "mixed: updates on the master (8 clients): " int($3) "/s"}' > "$S/u.out") & P1=$!
timeout 30 taskset -c "$CLIENT_CPUS" pgbench -n -f "$S/sel.sql" -M prepared -c 24 -j 6 -T 10 -h "$S/sock" -p 5581 -U test test 2>&1 | awk '/^tps/{print "mixed: selects on the replicas (24 clients): " int($3) "/s"}'
wait $P1; cat "$S/u.out"
echo "lag idle: $(pin python3 "$L/probe2.py" "$S/sock" 5580 5581 5 6 20 | head -2 | tr '\n' ' ')"
(timeout 40 taskset -c "$CLIENT_CPUS" pgbench -n -f "$S/upd.sql" -M prepared -c 8 -j 4 -T 22 -h "$S/sock" -p 5580 -U test test >/dev/null 2>&1) & P1=$!
(timeout 40 taskset -c "$CLIENT_CPUS" pgbench -n -f "$S/sel.sql" -M prepared -c 24 -j 6 -T 22 -h "$S/sock" -p 5581 -U test test >/dev/null 2>&1) & P2=$!
sleep 1; echo "lag under the mixed load: $(pin python3 "$L/probe2.py" "$S/sock" 5580 5581 20 6 20 | head -2 | tr '\n' ' ')"
wait $P1 $P2
kill -TERM $SUP; wait $SUP 2>/dev/null
