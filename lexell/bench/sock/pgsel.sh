#!/bin/bash
# pgbench point selects against lexdb, epoll against io_uring (LXL_URING=1),
# over TCP and a Unix socket, with the server's CPU per select from /proc.
# MODES (default "epoll uring"): each epoll or uring, optionally +spinN for
# LXL_SPIN_US=N (poll N us before sleeping), e.g. MODES="epoll uring+spin50".
# QUERY=upd: updates (a commit each) instead of selects. VIAS: "tcp unix".
# LEXDB_CACHE_MB, when set, passes to the server (64: most selects miss).
# Design note lexdb.md 9.57.
#
#   bench/sock/pgsel.sh LEXDB_BINARY WORKDIR [ROUNDS] [SECONDS] [CLIENTS...]
#
# WORKDIR gets the data directory (made once: 1M rows in acct), the socket
# directory and the pgbench script. Each round starts the server once per
# mode, warms its cache, then runs every transport and client count.
set -e
BIN=$1; W=$2; ROUNDS=${3:-2}; SECS=${4:-10}; shift 4 2>/dev/null || shift $#
CLIENTS=${*:-1 8 32}
PORT=5497
PGB=$(command -v pgbench || echo /usr/lib/postgresql/16/bin/pgbench)
SOCK=${SOCK:-$W/sock}   # a Unix socket path must fit in 108 bytes
mkdir -p "$W" "$SOCK"
printf '%s\n' '\set aid random(1, 1000000)' 'SELECT abalance FROM acct WHERE aid = :aid;' > "$W/sel.sql"
printf '%s\n' '\set aid random(1, 1000000)' 'UPDATE acct SET abalance = abalance + 1 WHERE aid = :aid;' > "$W/upd.sql"
Q=${QUERY:-sel}
VIAS=${VIAS:-tcp unix}

stop() {   # SIGTERM, then wait: its shutdown checkpoint may take seconds
    if [ -n "$SPID" ]; then kill "$SPID" 2>/dev/null || true; wait "$SPID" 2>/dev/null || true; SPID=; fi
}
start() {  # mode
    stop
    case $1 in *uring*) export LXL_URING=1 ;; *) unset LXL_URING ;; esac
    case $1 in *spin*) export LXL_SPIN_US=${1##*spin} ;; *) unset LXL_SPIN_US ;; esac
    "$BIN" "$W/data" 127.0.0.1:$PORT "$SOCK" > "$W/server.log" 2>&1 &
    SPID=$!
    for _ in $(seq 50); do psql -h 127.0.0.1 -p $PORT -U test -d test -Atc 'select 1' >/dev/null 2>&1 && return; sleep 0.1; done
    echo "server did not start"; cat "$W/server.log"; exit 1
}
cpu() { awk '{print $14 + $15}' /proc/$SPID/stat; }

if [ ! -d "$W/data" ]; then
    mkdir -p "$W/data"
    start epoll
    psql -h 127.0.0.1 -p $PORT -U test -d test -q -c 'CREATE TABLE acct (aid int PRIMARY KEY, abalance int NOT NULL)' \
        -c 'INSERT INTO acct SELECT g, 0 FROM generate_series(1, 1000000) g'
fi

TCK=$(getconf CLK_TCK)
for r in $(seq "$ROUNDS"); do
    for mode in ${MODES:-epoll uring}; do
        start $mode
        psql -h 127.0.0.1 -p $PORT -U test -d test -Atc 'SELECT sum(abalance) FROM acct' >/dev/null
        "$PGB" -n -f "$W/$Q.sql" -M prepared -c 32 -j 8 -T 5 -h 127.0.0.1 -p $PORT -U test test >/dev/null 2>&1
        for via in $VIAS; do
            H=127.0.0.1; [ $via = unix ] && H=$SOCK
            for c in $CLIENTS; do
                j=$c; [ $j -gt 8 ] && j=8
                c0=$(cpu)
                tps=$("$PGB" -n -f "$W/$Q.sql" -M prepared -c $c -j $j -T "$SECS" -h $H -p $PORT -U test test 2>&1 |
                      awk '/^tps/ {print int($3)}')
                c1=$(cpu)
                awk -v r=$r -v m=$mode -v v=$via -v c=$c -v t=$tps -v d=$((c1 - c0)) -v k=$TCK -v s=$SECS \
                    'BEGIN { printf "round %d  %-12s %-4s clients %2d  tps %7d  server cpu/op %6.2f us\n", r, m, v, c, t, d / k * 1e6 / (t * s) }'
            done
        done
    done
done
stop
