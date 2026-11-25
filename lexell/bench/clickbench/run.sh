#!/bin/bash
# run.sh: ClickBench (hits table, 43 queries), lexdb against PostgreSQL on one machine.
#
#   bench/clickbench/run.sh LEXDB_BINARY WORKDIR [ROWS] [RUNS]
#
# ROWS defaults to 1000000 (1M rows, ~700 MB TSV, fast ~2-3 min full run);
# pass 10000000 (10M) or 'all' (full ~100M-row ClickBench dataset) for larger
# runs. Use one WORKDIR per row count.
#
# Env:
#   CB_ONLY=lexdb,pg1,pg4     modes to run (default all three)
#   CB_QUERIES=0,1,28         subset of query numbers to run
#   CB_CPUS=0-3               CPUs both servers are confined to
#   CB_BOOST=off              CPU boost: off (fixed clock, default) or keep
#   PG_SHARED_BUFFERS=4GB
#   QUERY_TIMEOUT=120         seconds per query
#   LEXDB_CACHE_MB=N          passed to lexdb when set
set -euo pipefail
export LC_ALL=C

HERE=$(cd "$(dirname "$0")" && pwd)
if [ $# -lt 2 ]; then
    sed -n '2,9p' "$0" >&2
    exit 2
fi

BIN=$(realpath "$1")
W=$2
ROWS=${3:-1000000}
RUNS=${4:-3}
mkdir -p "$W"
W=$(realpath "$W")

DBUSER=cb
DBNAME=cb
LPORT=${LEXDB_PORT:-5594}
PPORT=${PG_PORT:-5595}
OUT=$W/out
UNIT_L=cb-lexdb
UNIT_P=cb-pg
PG_SHARED_BUFFERS=${PG_SHARED_BUFFERS:-4GB}
QUERY_TIMEOUT=${QUERY_TIMEOUT:-120}
CB_CPUS=${CB_CPUS:-0-3}
MODES=${CB_ONLY:-lexdb,pg1,pg4}
MODES=${MODES//,/ }

want() {
    case " $MODES " in
        *" $1 "*) return 0 ;;
        *) return 1 ;;
    esac
}

for m in $MODES; do
    case $m in
        lexdb|pg1|pg4) ;;
        *) echo "run.sh: unknown mode '$m' in CB_ONLY" >&2; exit 2 ;;
    esac
done

[ -x "$BIN" ] || { echo "run.sh: $BIN is not an executable" >&2; exit 2; }
command -v psql >/dev/null || { echo "run.sh: psql is not on PATH" >&2; exit 2; }
command -v systemd-run >/dev/null || { echo "run.sh: systemd-run is not on PATH" >&2; exit 2; }
command -v python3 >/dev/null || { echo "run.sh: python3 is not on PATH" >&2; exit 2; }

POSTGRES=${POSTGRES:-$(command -v postgres || true)}
[ -n "$POSTGRES" ] || { echo "run.sh: postgres is not on PATH (set POSTGRES)" >&2; exit 2; }
PG_BIN=$(dirname "$POSTGRES")
INITDB=$PG_BIN/initdb
[ -x "$INITDB" ] || { echo "run.sh: $INITDB is missing" >&2; exit 2; }

psql_at() {
    local port=$1; shift
    psql -X -q -v ON_ERROR_STOP=1 -h 127.0.0.1 -p "$port" -U "$DBUSER" -d "$DBNAME" "$@"
}

psql_admin() {
    local port=$1; shift
    psql -X -q -v ON_ERROR_STOP=1 -h 127.0.0.1 -p "$port" -U "$DBUSER" -d postgres "$@"
}

stop() {
    systemctl --user stop "cb-$1" 2>/dev/null || true
    systemctl --user reset-failed "cb-$1" 2>/dev/null || true
}

BOOST_FILE=/sys/devices/system/cpu/cpufreq/boost
BOOST_WAS=$(cat "$BOOST_FILE" 2>/dev/null || echo unknown)
BOOST_SET=
restore_boost() {
    if [ -n "$BOOST_SET" ]; then
        sudo -n /usr/local/sbin/cpu-boost on || echo "run.sh: could not turn CPU boost back on" >&2
        BOOST_SET=
    fi
}
trap 'stop lexdb; stop pg; restore_boost' EXIT
trap 'exit 130' INT TERM

start_lexdb() {
    stop lexdb
    local envargs=() cap=() v
    for v in LEXDB_CACHE_MB LEXDB_CKPT_POOL LXL_PAR; do
        if [ -n "${!v:-}" ]; then envargs+=(--setenv="$v=${!v}"); fi
    done
    if [ -n "$CB_CPUS" ]; then cap+=(-p "CPUAffinity=$CB_CPUS"); fi
    mkdir -p "$W/lexdb"
    local args=("$W/lexdb" "127.0.0.1:$LPORT")
    if [ -n "${LEXDB_CACHE_MB:-}" ]; then args+=(--cache-mb "$LEXDB_CACHE_MB"); fi
    systemd-run --user --quiet --collect -u "$UNIT_L" -p TimeoutStopSec=5 "${cap[@]}" "${envargs[@]}" \
        "$BIN" "${args[@]}"
    for _ in $(seq 100); do
        psql_at "$LPORT" -Atc 'select 1' >/dev/null 2>&1 && return 0
        sleep 0.1
    done
    echo "run.sh: lexdb did not start" >&2
    journalctl --user -u "$UNIT_L" -n 20 --no-pager || true
    exit 1
}

start_pg() {
    stop pg
    local cap=()
    if [ -n "$CB_CPUS" ]; then cap+=(-p "CPUAffinity=$CB_CPUS"); fi
    mkdir -p "$W/psock"
    systemd-run --user --quiet --collect -u "$UNIT_P" -p TimeoutStopSec=10 "${cap[@]}" \
        "$POSTGRES" -D "$W/pg" -k "$W/psock" -p "$PPORT" \
        -c listen_addresses=127.0.0.1 -c shared_buffers="$PG_SHARED_BUFFERS" \
        -c effective_cache_size=34GB -c work_mem=256MB -c maintenance_work_mem=2GB \
        -c random_page_cost=1.1 -c effective_io_concurrency=200 -c max_wal_size=16GB
    for _ in $(seq 100); do
        psql_admin "$PPORT" -Atc 'select 1' >/dev/null 2>&1 && return 0
        sleep 0.1
    done
    echo "run.sh: PostgreSQL did not start" >&2
    journalctl --user -u "$UNIT_P" -n 20 --no-pager || true
    exit 1
}

load_hits() {
    local port=$1 label=$2 tsv=$3
    local file=$OUT/load-$label.tsv
    : > "$file"
    psql_at "$port" -f "$HERE/schema.sql"
    local t0 t1 n ms a0 a1
    t0=$(date +%s%N)
    if [ "$label" = pg ]; then
        psql_at "$port" <<EOF
BEGIN;
TRUNCATE TABLE hits;
\copy hits FROM '$tsv' WITH (FREEZE);
COMMIT;
EOF
    else
        # LexDB caps a single transaction's WAL at 4 GB; stream in 2M-row COPY transactions
        # so both 10M and 100M datasets load cleanly with zero extra disk copies.
        python3 - "$tsv" "$port" "$DBUSER" "$DBNAME" <<'PY'
import subprocess, sys
tsv, port, user, db = sys.argv[1:5]
CHUNK = 2_000_000
cmd = ["psql", "-X", "-q", "-v", "ON_ERROR_STOP=1",
       "-h", "127.0.0.1", "-p", port, "-U", user, "-d", db,
       "-c", "\\copy hits FROM stdin"]
proc = None
n = 0
with open(tsv, "rb") as f:
    for line in f:
        if proc is None:
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        proc.stdin.write(line)
        n += 1
        if n % CHUNK == 0:
            proc.stdin.close()
            rc = proc.wait()
            if rc != 0:
                sys.exit(rc)
            proc = None
if proc is not None:
    proc.stdin.close()
    rc = proc.wait()
    if rc != 0:
        sys.exit(rc)
PY
    fi
    t1=$(date +%s%N)
    n=$(psql_at "$port" -Atc "SELECT COUNT(*) FROM hits")
    ms=$(( (t1 - t0) / 1000000 ))
    printf 'hits\t%s\t%s\n' "$n" "$ms" >> "$file"
    printf 'load  %-6s hits %10s rows  %7d ms\n' "$label" "$n" "$ms"
    a0=$(date +%s%N)
    if [ "$label" = pg ]; then
        psql_at "$port" -c 'VACUUM (ANALYZE) hits'
    else
        psql_at "$port" -c 'ANALYZE'
    fi
    a1=$(date +%s%N)
    echo $(( (a1 - a0) / 1000000 )) > "$OUT/analyze-$label.ms"
    printf 'load  %-6s analyze %d ms\n' "$label" "$(( (a1 - a0) / 1000000 ))"
}

run_bench() {
    local label=$1 unit=$2 port=$3 pgoptions=$4
    local client_timeout=$((QUERY_TIMEOUT + 30))
    local cmd=(python3 "$HERE/bench.py" --label "$label" --unit "$unit"
        --port "$port" --user "$DBUSER" --db "$DBNAME"
        --queries "$HERE/queries" --out "$OUT/$label.tsv"
        --runs "$RUNS" --timeout "$client_timeout")
    if [ -n "${CB_QUERIES:-}" ]; then cmd+=(--only "$CB_QUERIES"); fi
    if [ "$label" = lexdb ]; then
        cmd+=(--pre "SET max_statement_mem = 0; SET statement_timeout = '${QUERY_TIMEOUT}s';")
    elif [ -n "$pgoptions" ]; then
        pgoptions="$pgoptions -c statement_timeout=${QUERY_TIMEOUT}s"
    fi
    set +e
    if [ -n "$pgoptions" ]; then
        PGOPTIONS="$pgoptions" "${cmd[@]}" 2>&1 | tee "$OUT/$label.log"
    else
        "${cmd[@]}" 2>&1 | tee "$OUT/$label.log"
    fi
    local r=${PIPESTATUS[0]}
    set -e
    return "$r"
}

mkdir -p "$OUT"
TSV=$("$HERE/fetch.sh" "$W" "$ROWS")

case "${CB_BOOST:-off}" in
    keep) ;;
    off)
        if [ "$BOOST_WAS" = 1 ]; then
            if sudo -n /usr/local/sbin/cpu-boost off; then
                BOOST_SET=1
            else
                echo "run.sh: cannot turn CPU boost off; set CB_BOOST=keep" >&2
                exit 1
            fi
        fi ;;
    *) echo "run.sh: CB_BOOST is off or keep" >&2; exit 2 ;;
esac

rc=0

if want lexdb; then
    if [ ! -f "$W/lexdb_${ROWS}.loaded" ] || [ ! -d "$W/lexdb" ]; then
        rm -rf "$W/lexdb" "$W/lexdb_"*.loaded
        mkdir -p "$W/lexdb"
        chattr +C "$W/lexdb" 2>/dev/null || true
        start_lexdb
        load_hits "$LPORT" lexdb "$TSV"
        : > "$W/lexdb_${ROWS}.loaded"
    else
        start_lexdb
    fi
    run_bench lexdb "$UNIT_L" "$LPORT" "" || rc=1
    stop lexdb
fi

if want pg1 || want pg4; then
    if [ ! -f "$W/pg_${ROWS}.loaded" ] || [ ! -d "$W/pg" ]; then
        rm -rf "$W/pg" "$W/pg_"*.loaded
        mkdir -p "$W/pg"
        chattr +C "$W/pg" 2>/dev/null || true
        "$INITDB" -D "$W/pg" -U "$DBUSER" --auth=trust -E UTF8 --no-locale >/dev/null
        start_pg
        psql_admin "$PPORT" -c "CREATE DATABASE $DBNAME"
        load_hits "$PPORT" pg "$TSV"
        : > "$W/pg_${ROWS}.loaded"
    else
        start_pg
    fi
    if want pg1; then
        run_bench pg1 "$UNIT_P" "$PPORT" "-c max_parallel_workers_per_gather=0" || rc=1
    fi
    if want pg4; then
        run_bench pg4 "$UNIT_P" "$PPORT" "-c max_parallel_workers_per_gather=3 -c max_parallel_workers=3" || rc=1
    fi
    stop pg
fi

if [ -f "$OUT/lexdb.tsv" ] || [ -f "$OUT/pg1.tsv" ] || [ -f "$OUT/pg4.tsv" ]; then
    python3 "$HERE/compare.py" "$OUT" | tee "$OUT/summary.txt"
    echo "clickbench: results in $OUT/summary.md"
else
    rc=1
fi
exit "$rc"
