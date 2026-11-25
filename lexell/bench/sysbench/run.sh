#!/bin/bash
# run.sh: sysbench OLTP benchmark suite, lexdb against PostgreSQL on one machine.
#
#   bench/sysbench/run.sh LEXDB_BINARY WORKDIR [TABLES] [TABLE_SIZE] [SECONDS]
#
# Defaults: 4 tables x 250,000 rows (1,000,000 rows total), 10 seconds per run,
# threads "1 8 32", Unix domain sockets, prepared statements (--db-ps-mode=auto),
# servers pinned to CPUs 0-3 (SMT siblings idle), sysbench client pinned to
# CPUs 4-7,12-15, CPU boost off (fixed clock).
#
# Modes (SB_MODES, default "lexdb lexdb3 pg"):
#   lexdb   single lexdb process (all workloads)
#   lexdb3  lexdb master + 3 read replicas (read workloads on replica socket)
#   pg      PostgreSQL 18 on 4 cores (all workloads, fsync + synchronous_commit on)
#
# Env:
#   SB_MODES="lexdb lexdb3 pg"
#   SB_TESTS="oltp_point_select oltp_read_only oltp_read_write oltp_write_only oltp_update_index oltp_update_non_index"
#   SB_THREADS="1 8 32"
#   SB_PS_MODE=auto            auto (prepared) or disable
#   SB_BOOST=off               off (fixed clock, default) or keep
#   SERVER_CPUS=0-3
#   CLIENT_CPUS=4-7,12-15
#   PG_SHARED_BUFFERS=4GB
#   SYSBENCH=/path/to/sysbench
set -euo pipefail
export LC_ALL=C

HERE=$(cd "$(dirname "$0")" && pwd)
if [ $# -lt 2 ]; then
    sed -n '2,16p' "$0" >&2
    exit 2
fi

BIN=$(realpath "$1")
W=$2
TABLES=${3:-4}
TABLE_SIZE=${4:-250000}
SECS=${5:-10}
mkdir -p "$W"
W=$(realpath "$W")

SYSBENCH=${SYSBENCH:-$(command -v sysbench || ([ -x "$HOME/.local/bin/sysbench" ] && echo "$HOME/.local/bin/sysbench") || true)}
[ -x "$SYSBENCH" ] || { echo "run.sh: sysbench not found (install sysbench or set SYSBENCH)" >&2; exit 2; }
[ -x "$BIN" ] || { echo "run.sh: $BIN is not an executable" >&2; exit 2; }
command -v psql >/dev/null || { echo "run.sh: psql is not on PATH" >&2; exit 2; }
command -v systemd-run >/dev/null || { echo "run.sh: systemd-run is not on PATH" >&2; exit 2; }
command -v python3 >/dev/null || { echo "run.sh: python3 is not on PATH" >&2; exit 2; }

POSTGRES=${POSTGRES:-$(command -v postgres || true)}
[ -n "$POSTGRES" ] || { echo "run.sh: postgres is not on PATH" >&2; exit 2; }
PG_BIN=$(dirname "$POSTGRES")
INITDB=$PG_BIN/initdb

SERVER_CPUS=${SERVER_CPUS:-0-3}
CLIENT_CPUS=${CLIENT_CPUS:-4-7,12-15}
PG_SHARED_BUFFERS=${PG_SHARED_BUFFERS:-4GB}
SB_PS_MODE=${SB_PS_MODE:-auto}
SB_BOOST=${SB_BOOST:-off}
SB_MODES=${SB_MODES:-"lexdb lexdb3 pg"}
SB_TESTS=${SB_TESTS:-"oltp_point_select oltp_read_only oltp_read_write oltp_write_only oltp_update_index oltp_update_non_index"}
SB_THREADS=${SB_THREADS:-"1 8 32"}
SB_MODES=${SB_MODES//,/ }
SB_TESTS=${SB_TESTS//,/ }
SB_THREADS=${SB_THREADS//,/ }

DBUSER=sb
DBNAME=sb
LPORT=${LEXDB_PORT:-5586}
LPORT_R=$((LPORT + 1))
PPORT=${PG_PORT:-5588}

LSOCK=$W/lsock
LRSOCK=$W/lrsock
PSOCK=$W/psock
OUT=$W/out
mkdir -p "$LSOCK" "$LRSOCK" "$PSOCK" "$OUT"

UNIT_L=sb-lexdb
UNIT_LR=sb-lexdb3
UNIT_P=sb-pg

pin() { taskset -c "$CLIENT_CPUS" "$@"; }

want_mode() {
    case " $SB_MODES " in
        *" $1 "*) return 0 ;;
        *) return 1 ;;
    esac
}

is_read_test() {
    case "$1" in
        oltp_point_select|oltp_read_only) return 0 ;;
        *) return 1 ;;
    esac
}

unit_of() {
    case "$1" in
        lexdb) echo "$UNIT_L" ;;
        lexdb3) echo "$UNIT_LR" ;;
        pg) echo "$UNIT_P" ;;
    esac
}

stop_unit() {
    local u=$1
    systemctl --user stop "$u" 2>/dev/null || true
    for _ in $(seq 50); do
        systemctl --user is-active --quiet "$u" 2>/dev/null || break
        sleep 0.1
    done
    systemctl --user reset-failed "$u" 2>/dev/null || true
}

cpu_ns() {
    systemctl --user show -p CPUUsageNSec --value "$(unit_of "$1")"
}

BOOST_CHANGED=0
cleanup() {
    stop_unit "$UNIT_L"
    stop_unit "$UNIT_LR"
    stop_unit "$UNIT_P"
    if [ "$BOOST_CHANGED" = 1 ]; then
        sudo -n /usr/local/sbin/cpu-boost on >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT

if [ "$SB_BOOST" = "off" ] && [ -x /usr/local/sbin/cpu-boost ]; then
    if sudo -n /usr/local/sbin/cpu-boost off >/dev/null 2>&1; then
        BOOST_CHANGED=1
    else
        echo "run.sh: warning: could not disable CPU boost (continuing)" >&2
    fi
fi

wait_ready() {
    local sock=$1 port=$2 db=$3 u=$4
    for _ in $(seq 150); do
        if psql -h "$sock" -p "$port" -U "$DBUSER" -d "$db" -X -Atc 'select 1' >/dev/null 2>&1; then
            return 0
        fi
        sleep 0.1
    done
    echo "run.sh: $u did not start on $sock:$port" >&2
    journalctl --user -u "$u" -n 30 --no-pager >&2 || true
    exit 1
}

start_lexdb() {
    stop_unit "$UNIT_L"
    mkdir -p "$W/lexdb"
    systemd-run --user --quiet --collect -u "$UNIT_L" -p CPUAffinity="$SERVER_CPUS" \
        "$BIN" "$W/lexdb" "127.0.0.1:$LPORT" "$LSOCK"
    wait_ready "$LSOCK" "$LPORT" "$DBNAME" "$UNIT_L"
}

start_lexdb3() {
    stop_unit "$UNIT_LR"
    rm -rf "$W/lexdb3"
    cp -r "$W/lexdb" "$W/lexdb3"
    systemd-run --user --quiet --collect -u "$UNIT_LR" -p CPUAffinity="$SERVER_CPUS" \
        "$BIN" "$W/lexdb3" "127.0.0.1:$LPORT" "$LRSOCK" --replicas 3
    wait_ready "$LRSOCK" "$LPORT_R" "$DBNAME" "$UNIT_LR"
}

start_pg() {
    stop_unit "$UNIT_P"
    if [ ! -d "$W/pg" ]; then
        mkdir -p "$W/pg"
        chattr +C "$W/pg" 2>/dev/null || true
        "$INITDB" -D "$W/pg" -U "$DBUSER" --auth=trust -E UTF8 --no-locale >/dev/null
    fi
    systemd-run --user --quiet --collect -u "$UNIT_P" -p CPUAffinity="$SERVER_CPUS" \
        "$POSTGRES" -D "$W/pg" -k "$PSOCK" -p "$PPORT" \
        -c listen_addresses= \
        -c shared_buffers="$PG_SHARED_BUFFERS" \
        -c effective_cache_size=34GB \
        -c work_mem=64MB \
        -c maintenance_work_mem=1GB \
        -c random_page_cost=1.1 \
        -c effective_io_concurrency=200 \
        -c max_wal_size=8GB \
        -c max_connections=128
    wait_ready "$PSOCK" "$PPORT" postgres "$UNIT_P"
    psql -h "$PSOCK" -p "$PPORT" -U "$DBUSER" -d postgres -X -Atc \
        "SELECT 1 FROM pg_database WHERE datname='$DBNAME'" | grep -q 1 || \
        psql -h "$PSOCK" -p "$PPORT" -U "$DBUSER" -d postgres -X -q -c "CREATE DATABASE $DBNAME"
}

sb_cmd() {
    local test=$1 sock=$2 port=$3 threads=$4 time_s=$5 action=$6
    pin "$SYSBENCH" "$test" \
        --db-driver=pgsql \
        --pgsql-host="$sock" \
        --pgsql-port="$port" \
        --pgsql-user="$DBUSER" \
        --pgsql-db="$DBNAME" \
        --tables="$TABLES" \
        --table-size="$TABLE_SIZE" \
        --threads="$threads" \
        --time="$time_s" \
        --db-ps-mode="$SB_PS_MODE" \
        "$action"
}

prepare_server() {
    local mode=$1 sock=$2 port=$3 marker=$4
    if [ -f "$marker" ]; then
        return 0
    fi
    local pt=$TABLES
    [ "$pt" -gt 8 ] && pt=8
    echo "sysbench: preparing $mode ($TABLES tables x $TABLE_SIZE rows)..." >&2
    local t0 t1
    t0=$(date +%s.%N)
    sb_cmd oltp_read_write "$sock" "$port" "$pt" 0 prepare >/dev/null
    if [ "$mode" = "pg" ]; then
        pin psql -h "$sock" -p "$port" -U "$DBUSER" -d "$DBNAME" -X -q -c "VACUUM ANALYZE"
    else
        pin psql -h "$sock" -p "$port" -U "$DBUSER" -d "$DBNAME" -X -q -c "ANALYZE"
    fi
    t1=$(date +%s.%N)
    awk -v m="$mode" -v a="$t0" -v b="$t1" 'BEGIN { printf "%s\t%.2f\n", m, b - a }' > "$marker"
    echo "sysbench: $mode prepared in $(awk -v a="$t0" -v b="$t1" 'BEGIN { printf "%.2f", b - a }') s" >&2
}

parse_sb() {
    local test=$1 threads=$2 cpu_delta_ns=$3 raw_file=$4
    python3 - "$test" "$threads" "$cpu_delta_ns" "$raw_file" <<'PY'
import re, sys
test, threads, cpu_ns, path = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
txt = open(path).read()

def grab(pat, default=0.0):
    m = re.search(pat, txt)
    return float(m.group(1)) if m else default

tx_n = grab(r"transactions:\s+(\d+)")
tps = grab(r"transactions:\s+\d+\s+\(([0-9.]+)\s+per sec")
q_n = grab(r"queries:\s+(\d+)")
qps = grab(r"queries:\s+\d+\s+\(([0-9.]+)\s+per sec")
errs = int(grab(r"ignored errors:\s+(\d+)"))
avg_ms = grab(r"avg:\s+([0-9.]+)")
p95_ms = grab(r"95th percentile:\s+([0-9.]+)")
cpu_us_tx = (cpu_ns / 1000.0 / tx_n) if tx_n > 0 else 0.0
cpu_us_q = (cpu_ns / 1000.0 / q_n) if q_n > 0 else 0.0
print(f"{test}\t{threads}\t{tps:.2f}\t{qps:.2f}\t{avg_ms:.2f}\t{p95_ms:.2f}\t{errs}\t{cpu_us_tx:.2f}\t{cpu_us_q:.2f}")
PY
}

run_suite() {
    local mode=$1 sock=$2 port=$3 out_tsv=$4
    printf "test\tthreads\ttps\tqps\tavg_ms\tp95_ms\terrors\tcpu_us_tx\tcpu_us_q\n" > "$out_tsv"

    # Warm page cache / B-tree pools
    sb_cmd oltp_point_select "$sock" "$port" 8 3 run >/dev/null 2>&1 || true

    for test in $SB_TESTS; do
        if [ "$mode" = "lexdb3" ] && ! is_read_test "$test"; then
            continue
        fi
        for th in $SB_THREADS; do
            local raw=$OUT/${mode}_${test}_t${th}.txt
            local c0 c1 line
            c0=$(cpu_ns "$mode")
            sb_cmd "$test" "$sock" "$port" "$th" "$SECS" run > "$raw"
            c1=$(cpu_ns "$mode")
            line=$(parse_sb "$test" "$th" "$((c1 - c0))" "$raw")
            echo "$line" >> "$out_tsv"
            printf "%-7s %-22s t=%-2s  tps=%9s  qps=%10s  p95=%6s ms  cpu/tx=%8s us  err=%s\n" \
                "$mode" "$test" "$th" \
                "$(echo "$line" | cut -f3)" \
                "$(echo "$line" | cut -f4)" \
                "$(echo "$line" | cut -f6)" \
                "$(echo "$line" | cut -f8)" \
                "$(echo "$line" | cut -f7)"
        done
    done
}

# Prepare data if needed (lexdb3 needs lexdb prepared first)
if want_mode lexdb || want_mode lexdb3; then
    if [ ! -f "$W/lexdb.prepared" ]; then
        start_lexdb
        prepare_server lexdb "$LSOCK" "$LPORT" "$W/lexdb.prepared"
        stop_unit "$UNIT_L"
    fi
fi

if want_mode lexdb; then
    start_lexdb
    run_suite lexdb "$LSOCK" "$LPORT" "$OUT/lexdb.tsv"
    stop_unit "$UNIT_L"
fi

if want_mode lexdb3; then
    start_lexdb3
    run_suite lexdb3 "$LRSOCK" "$LPORT_R" "$OUT/lexdb3.tsv"
    stop_unit "$UNIT_LR"
fi

if want_mode pg; then
    start_pg
    prepare_server pg "$PSOCK" "$PPORT" "$W/pg.prepared"
    run_suite pg "$PSOCK" "$PPORT" "$OUT/pg.tsv"
    stop_unit "$UNIT_P"
fi

python3 "$HERE/compare.py" "$OUT" --tables "$TABLES" --table-size "$TABLE_SIZE" --seconds "$SECS" > "$OUT/summary.md"
cat "$OUT/summary.md"
echo "sysbench: results in $OUT/summary.md"
