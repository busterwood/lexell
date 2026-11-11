#!/bin/bash
# vspg.sh: lexdb against PostgreSQL on the same machine, data, disk and transport
# (design/lexdb.md 9.67). Both servers run as transient systemd user services, so
# a server's CPU is its cgroup's (every process and thread, PostgreSQL's exited
# backends included), read before and after each run.
#
#   bench/sock/vspg.sh LEXDB_BINARY WORKDIR [ROUNDS] [SECONDS] [CLIENTS...]
#
# WORKDIR gets both data directories (made once, with copy-on-write off as
# lexdb sets it for itself on btrfs) and their socket directories. Measured:
#   load   a 1M-row INSERT ... generate_series of acct (aid, abalance), and of
#          t (id, g, n, v, t) for the aggregates; the time through psql
#   sel    pgbench point selects on acct, prepared, warm, over Unix sockets
#   upd    pgbench updates of acct, a commit each (both durable: PostgreSQL
#          with fsync and synchronous_commit on, as by default)
#   agg    five aggregate queries on t through psql, best of five; PostgreSQL
#          with its default parallel workers and with none
#          (max_parallel_workers_per_gather = 0); the results compared
# PostgreSQL: shared_buffers 4GB (both servers hold all the data in memory),
# otherwise its defaults. lexdb: its defaults (io_uring and adaptive polling).
set -e
BIN=$(realpath "$1"); W=$2; ROUNDS=${3:-2}; SECS=${4:-10}; shift 4 2>/dev/null || shift $#
CLIENTS=${*:-1 8 32}
LPORT=5497; PPORT=5496
mkdir -p "$W"; W=$(realpath "$W")
LSOCK=$W/lsock; PSOCK=$W/psock
mkdir -p "$LSOCK" "$PSOCK"
printf '%s\n' '\set aid random(1, 1000000)' 'SELECT abalance FROM acct WHERE aid = :aid;' > "$W/sel.sql"
printf '%s\n' '\set aid random(1, 1000000)' 'UPDATE acct SET abalance = abalance + 1 WHERE aid = :aid;' > "$W/upd.sql"

unit() { echo "vspg-$1"; }
stop() { systemctl --user stop "$(unit "$1")" 2>/dev/null || true; }
cpu_ns() { systemctl --user show -p CPUUsageNSec --value "$(unit "$1")"; }
host() { [ "$1" = lexdb ] && echo "$LSOCK" || echo "$PSOCK"; }
port() { [ "$1" = lexdb ] && echo $LPORT || echo $PPORT; }
q() { local s=$1; shift; psql -h "$(host "$s")" -p "$(port "$s")" -U test -d test -X -q "$@"; }
ready() {
    local db=test; [ "$1" = pg ] && db=postgres                    # test may not exist yet
    for _ in $(seq 100); do psql -h "$(host "$1")" -p "$(port "$1")" -U test -d $db -X -Atc 'select 1' >/dev/null 2>&1 && return; sleep 0.1; done
    echo "$1 did not start"; journalctl --user -u "$(unit "$1")" -n 20 --no-pager; exit 1
}
start() {
    stop "$1"
    if [ "$1" = lexdb ]; then
        systemd-run --user --quiet --collect -u "$(unit lexdb)" "$BIN" "$W/lexdb" 127.0.0.1:$LPORT "$LSOCK"
    else
        systemd-run --user --quiet --collect -u "$(unit pg)" /usr/bin/postgres -D "$W/pg" -k "$PSOCK" -p $PPORT \
            -c listen_addresses= -c shared_buffers=4GB
    fi
    ready "$1"
}
trap 'stop lexdb; stop pg' EXIT

if [ ! -d "$W/pg" ]; then
    mkdir -p "$W/pg"; chattr +C "$W/pg" 2>/dev/null || true
    initdb -D "$W/pg" -U test --auth=trust -E UTF8 --no-locale >/dev/null
fi
LOADS=$W/load.txt
if [ ! -d "$W/lexdb" ] || [ ! -f "$LOADS" ]; then
    rm -rf "$W/lexdb"; : > "$LOADS"
    for s in lexdb pg; do
        start $s
        [ $s = pg ] && psql -h "$PSOCK" -p $PPORT -U test -d postgres -X -q -c 'CREATE DATABASE test'
        pre=""; [ $s = lexdb ] && pre="SET max_statement_mem = 0;"
        t0=$(date +%s.%N)
        q $s -c "$pre CREATE TABLE acct (aid int PRIMARY KEY, abalance int NOT NULL); INSERT INTO acct SELECT g, 0 FROM generate_series(1, 1000000) g"
        t1=$(date +%s.%N)
        q $s -c "$pre CREATE TABLE t (id int PRIMARY KEY, g int NOT NULL, n int NOT NULL, v int NOT NULL, t text NOT NULL); INSERT INTO t SELECT i, i % 10, i % 97, (i * 37) % 1000, 'row ' || i FROM generate_series(1, 1000000) i"
        t2=$(date +%s.%N)
        [ $s = pg ] && q $s -c 'VACUUM ANALYZE'
        awk -v s=$s -v a=$t0 -v b=$t1 -v c=$t2 'BEGIN { printf "load  %-6s acct 1M rows %5.2f s   t 1M rows %5.2f s\n", s, b - a, c - b }' >> "$LOADS"
        stop $s
    done
fi
cat "$LOADS"

QUERIES=(
    "SELECT count(*) FROM t"
    "SELECT count(*), sum(v), min(v), max(v) FROM t WHERE n > 10"
    "SELECT sum(v) FROM t WHERE n > 5 AND v < 900 AND g <> 3"
    "SELECT g, count(*), sum(v), max(n) FROM t GROUP BY g ORDER BY g"
    "SELECT n, count(*) FROM t WHERE v % 2 = 0 GROUP BY n ORDER BY n"
)
agg() {  # server label [setting]: each query five times, the best, and the results' checksum
    local s=$1 label=$2 set=$3 i
    for i in "${!QUERIES[@]}"; do
        local f=$W/agg.sql
        { echo "$set"; echo '\timing on'; for _ in 1 2 3 4 5; do echo "${QUERIES[$i]};"; done; } > "$f"
        local out; out=$(q $s -At -f "$f")
        local best; best=$(echo "$out" | awk '/^Time:/ { if (b == "" || $2 < b) b = $2 } END { print b }')
        local sum; sum=$(echo "$out" | grep -v '^Time:' | grep -v '^SET$' | md5sum | cut -c1-8)
        printf "agg   %-14s q%d  %8.1f ms  results %s\n" "$label" $((i + 1)) "$best" "$sum"
    done
}

for r in $(seq "$ROUNDS"); do
    for s in lexdb pg; do
        start $s
        q $s -Atc 'SELECT sum(abalance) FROM acct' >/dev/null       # warm
        q $s -Atc 'SELECT sum(v) FROM t' >/dev/null
        pgbench -n -f "$W/sel.sql" -M prepared -c 32 -j 8 -T 5 -h "$(host $s)" -p "$(port $s)" -U test test >/dev/null 2>&1
        for kind in sel upd; do
            for c in $CLIENTS; do
                j=$c; [ $j -gt 8 ] && j=8
                c0=$(cpu_ns $s)
                tps=$(pgbench -n -f "$W/$kind.sql" -M prepared -c $c -j $j -T "$SECS" -h "$(host $s)" -p "$(port $s)" -U test test 2>&1 |
                      awk '/^tps/ { print int($3) }')
                c1=$(cpu_ns $s)
                awk -v r=$r -v s=$s -v k=$kind -v c=$c -v t=$tps -v d=$((c1 - c0)) -v n=$SECS \
                    'BEGIN { printf "%-5s round %d  %-6s clients %2d  tps %7d  server cpu/op %7.2f us\n", k, r, s, c, t, d / 1000 / (t * n) }'
            done
        done
        if [ $s = lexdb ]; then agg lexdb "lexdb"; else
            agg pg "pg parallel" ""
            agg pg "pg one core" "SET max_parallel_workers_per_gather = 0;"
        fi
        stop $s
    done
done
