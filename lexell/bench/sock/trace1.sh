#!/bin/bash
# trace1.sh: a per-request timeline of one pgbench client against lexdb, from
# tracefs (design/lexdb.md 9.59): system calls of lexdb and pgbench, their
# wakeups and switches, and the io_uring events, for 0.3 s of a warm run.
#
#   bench/sock/trace1.sh LEXDB_BINARY WORKDIR MODE OUT
#
# MODE: epoll (LXL_URING=0) or uring. WORKDIR is pgsel.sh's (its data
# directory and sel.sql must exist: run pgsel.sh once first). OUT gets the
# raw trace. SOCK (default /tmp/lxs) is the Unix socket's directory.
# Needs write access to /sys/kernel/tracing, once per boot:
#   sudo chmod -R a+rwX /sys/kernel/tracing
# Filters are by process name, not pid: under WSL2 the distro's pids are not
# the kernel's.
set -e
BIN=$1; W=$2; MODE=$3; OUT=$4
T=/sys/kernel/tracing
SOCK=${SOCK:-/tmp/lxs}
PORT=5497
mkdir -p "$SOCK"
[ "$MODE" = uring ] && export LXL_URING=1 || export LXL_URING=0
NAME=$(basename "$BIN" | cut -c1-15)
"$BIN" "$W/data" 127.0.0.1:$PORT "$SOCK" > "$OUT.server.log" 2>&1 &
SP=$!
for _ in $(seq 50); do psql -h "$SOCK" -p $PORT -U test -d test -Atc 'select 1' >/dev/null 2>&1 && break; sleep 0.1; done
# warm the cache, so the capture has no reads from the disk
psql -h "$SOCK" -p $PORT -U test -d test -Atc 'select sum(abalance) from acct' >/dev/null
pgbench -n -f "$W/sel.sql" -M prepared -c 8 -j 8 -T 3 -h "$SOCK" -p $PORT -U test test >/dev/null 2>&1
pgbench -n -f "$W/sel.sql" -M prepared -c 1 -j 1 -T 4 -h "$SOCK" -p $PORT -U test test > "$OUT.pgbench" 2>&1 &
PB=$!
sleep 1.5
echo 0 > $T/tracing_on; echo > $T/trace; echo 16384 > $T/buffer_size_kb
F="comm == \"$NAME\" || comm == \"pgbench\""
echo "$F" > $T/events/raw_syscalls/sys_enter/filter
echo "$F" > $T/events/raw_syscalls/sys_exit/filter
echo "$F" > $T/events/sched/sched_wakeup/filter
echo "next_comm == \"$NAME\" || next_comm == \"pgbench\" || prev_comm == \"$NAME\" || prev_comm == \"pgbench\"" > $T/events/sched/sched_switch/filter
EV="raw_syscalls/sys_enter raw_syscalls/sys_exit sched/sched_wakeup sched/sched_switch io_uring"
for e in $EV; do echo 1 > $T/events/$e/enable; done
echo 1 > $T/tracing_on; sleep 0.3; echo 0 > $T/tracing_on
for e in $EV; do echo 0 > $T/events/$e/enable; done
for e in raw_syscalls/sys_enter raw_syscalls/sys_exit sched/sched_wakeup sched/sched_switch; do echo 0 > $T/events/$e/filter; done
cp $T/trace "$OUT"
echo 1410 > $T/buffer_size_kb; echo 1 > $T/tracing_on
wait $PB
kill $SP; wait $SP || true
grep ^tps "$OUT.pgbench"
echo "trace: $(grep -vc '^#' "$OUT") events in $OUT"
