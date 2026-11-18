#!/bin/bash
# run.sh: the TPC-H derived workload, lexdb against PostgreSQL on one machine.
#
#   bench/tpch/run.sh LEXDB_BINARY WORKDIR [SCALE] [RUNS]
#
# This is derived from TPC-H, not an audited TPC result: the 22 queries at
# the specification's substitution values, dbgen data at one scale factor,
# and no refresh functions (RF1/RF2). See README.md.
#
# WORKDIR holds everything: WORKDIR/sfN (the dbgen files), WORKDIR/lexdb and
# WORKDIR/pg (the two data directories), and WORKDIR/out (the TSVs and
# summary). Use one WORKDIR per scale factor. The data directories are
# created with copy-on-write off on btrfs; both servers are stopped and
# restarted between modes, never run together.
#
# The servers run as transient systemd user units, so a server's CPU is its
# cgroup's. Both are confined to TPCH_CPUS (default 0-3: four physical
# cores, their SMT siblings 8-11 left idle, as the other suites pin servers;
# design/lexdb-benchmarks.md 2), and they run one at a time. lexdb is deliberately not CPU-capped
# to one core: its SQL execution is one thread, but checkpoints encode leaves
# on the par pool (LEXDB_CKPT_POOL=1) and its I/O helpers use other cores. A
# 100% quota would throttle all of them; par.map would still start its pool
# and the threads would contend for one core. LEXDB_CPU_QUOTA and
# PG_CPU_QUOTA add a quota when a budget-matched run is wanted.
#
# Env:
#   TPCH_ONLY=lexdb,pg1,pg4   modes to run (default all three)
#   TPCH_DBGEN=PATH           dbgen binary or kit directory;
#                             default WORKDIR/tpch-kit/dbgen/dbgen
#   PG_SHARED_BUFFERS=4GB
#   TPCH_CPUS=0-3             CPUs both servers are confined to
#   TPCH_INDEXES=conventional secondary index set, or none for PKs only
#   QUERY_TIMEOUT=900         seconds per query; lexdb cancels on the server
#                             (statement_timeout), psql gets 30 s more
#   LEXDB_CACHE_MB=N          passed to lexdb when set
#   LEXDB_CKPT_POOL=1, LXL_PAR=N   passed to lexdb when set
#   LEXDB_CPU_QUOTA=400%      lexdb cgroup quota (default: none; a 100%
#                             quota throttles its parallel checkpoint pool)
#   PG_CPU_QUOTA=400%         PostgreSQL cgroup quota (default: none, no quota)
#   TPCH_CHECK_ONLY=1         check prerequisites and the plan; run nothing
#   TPCH_REF=DIR              an earlier run's directory whose pg1.tsv checks
#                             lexdb's results when this run has no pg1
#   TPCH_BOOST=off            CPU frequency boost for the run: off (default:
#                             a fixed clock, restored after), or keep
#
# First time:
#   lexell/bench/tpch/fetch.sh WORKDIR/tpch-kit
#   bench/tpch/run.sh BINARY WORKDIR 1 3
set -euo pipefail
export LC_ALL=C

HERE=$(cd "$(dirname "$0")" && pwd)
if [ $# -lt 2 ]; then
    sed -n '2,9p' "$0" >&2
    exit 2
fi

BIN=$(realpath "$1")
W=$2
SF=${3:-1}
RUNS=${4:-3}
mkdir -p "$W"
W=$(realpath "$W")

DBUSER=tpch
DBNAME=tpch
LPORT=${LEXDB_PORT:-5598}
PPORT=${PG_PORT:-5599}
OUT=$W/out
DATA=$W/sf$SF
UNIT_L=tpch-lexdb
UNIT_P=tpch-pg
PG_SHARED_BUFFERS=${PG_SHARED_BUFFERS:-4GB}
QUERY_TIMEOUT=${QUERY_TIMEOUT:-900}
TPCH_CPUS=${TPCH_CPUS:-0-3}
TPCH_INDEXES=${TPCH_INDEXES:-conventional}
LEXDB_CPU_QUOTA=${LEXDB_CPU_QUOTA:-}
PG_CPU_QUOTA=${PG_CPU_QUOTA:-}
MODES=${TPCH_ONLY:-lexdb,pg1,pg4}
MODES=${MODES//,/ }
TABLES="region nation part supplier partsupp customer orders lineitem"

want() {
    case " $MODES " in
        *" $1 "*) return 0 ;;
        *) return 1 ;;
    esac
}

for m in $MODES; do
    case $m in
        lexdb|pg1|pg4) ;;
        *) echo "run.sh: unknown mode '$m' in TPCH_ONLY" >&2; exit 2 ;;
    esac
done
case $TPCH_INDEXES in
    conventional|none) ;;
    *) echo "run.sh: TPCH_INDEXES must be conventional or none" >&2; exit 2 ;;
esac

[ -x "$BIN" ] || { echo "run.sh: $BIN is not an executable" >&2; exit 2; }
case $QUERY_TIMEOUT in
    ''|*[!0-9]*) echo "run.sh: QUERY_TIMEOUT must be a whole number of seconds" >&2; exit 2 ;;
esac
[ "$QUERY_TIMEOUT" -gt 0 ] || { echo "run.sh: QUERY_TIMEOUT must be positive" >&2; exit 2; }
command -v psql >/dev/null || { echo "run.sh: psql is not on PATH" >&2; exit 2; }
command -v systemd-run >/dev/null || { echo "run.sh: systemd-run is not on PATH" >&2; exit 2; }
command -v python3 >/dev/null || { echo "run.sh: python3 is not on PATH" >&2; exit 2; }

if [ -n "${TPCH_DBGEN:-}" ]; then
    DBGEN=$TPCH_DBGEN
    [ -d "$DBGEN" ] && DBGEN=$DBGEN/dbgen
else
    DBGEN=$W/tpch-kit/dbgen/dbgen
fi
if [ ! -x "$DBGEN" ]; then
    echo "run.sh: no dbgen at $DBGEN" >&2
    echo "  run: lexell/bench/tpch/fetch.sh $W/tpch-kit" >&2
    echo "  or set TPCH_DBGEN to a dbgen binary" >&2
    exit 2
fi
DISTS=$(dirname "$DBGEN")/dists.dss
[ -f "$DISTS" ] || { echo "run.sh: $DISTS is missing" >&2; exit 2; }

POSTGRES=${POSTGRES:-$(command -v postgres || true)}
[ -n "$POSTGRES" ] || { echo "run.sh: postgres is not on PATH (set POSTGRES)" >&2; exit 2; }
PG_BIN=$(dirname "$POSTGRES")
INITDB=$PG_BIN/initdb
[ -x "$INITDB" ] || { echo "run.sh: $INITDB is missing" >&2; exit 2; }

NQ=$(find "$HERE/queries" -maxdepth 1 -name 'q[0-9]*.sql' | wc -l)
[ "$NQ" -eq 22 ] || { echo "run.sh: expected 22 queries in $HERE/queries, found $NQ" >&2; exit 2; }

for d in "$W"/sf*; do
    [ -e "$d" ] || continue
    [ "$d" = "$DATA" ] || {
        echo "run.sh: WORKDIR already has $d; use one WORKDIR per scale factor" >&2
        exit 2
    }
done

psql_at() {
    local port=$1
    shift
    psql -X -q -v ON_ERROR_STOP=1 -h 127.0.0.1 -p "$port" \
         -U "$DBUSER" -d "$DBNAME" "$@"
}

psql_admin() {
    local port=$1
    shift
    psql -X -q -v ON_ERROR_STOP=1 -h 127.0.0.1 -p "$port" \
         -U "$DBUSER" -d postgres "$@"
}

stop() { systemctl --user stop "tpch-$1" 2>/dev/null || true; }

# CPU frequency boost. With it on, a core's clock follows how many other
# cores are busy and how warm the machine is, and the same query moved
# 10-25% between runs; with it off every run is at the base clock. It is
# turned off for the run and restored on exit (also on an interrupt), by
# bench/tpch/cpu-boost, installed root-owned in /usr/local/sbin with a
# sudoers rule for exactly its "on" and "off" (README.md).
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
    # systemd-run does not inherit the caller's environment: the pool knobs
    # must be passed explicitly or they never reach the server.
    for v in LEXDB_CACHE_MB LEXDB_CKPT_POOL LXL_PAR; do
        if [ -n "${!v:-}" ]; then
            envargs+=(--setenv="$v=${!v}")
        fi
    done
    if [ -n "$TPCH_CPUS" ]; then
        cap+=(-p "CPUAffinity=$TPCH_CPUS")
    fi
    if [ -n "$LEXDB_CPU_QUOTA" ]; then
        cap+=(-p "CPUQuota=$LEXDB_CPU_QUOTA")
    fi
    mkdir -p "$W/lexdb"
    systemd-run --user --quiet --collect -u "$UNIT_L" "${cap[@]}" "${envargs[@]}" \
        "$BIN" "$W/lexdb" "127.0.0.1:$LPORT"
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
    if [ -n "$TPCH_CPUS" ]; then
        cap+=(-p "CPUAffinity=$TPCH_CPUS")
    fi
    if [ -n "$PG_CPU_QUOTA" ]; then
        cap+=(-p "CPUQuota=$PG_CPU_QUOTA")
    fi
    mkdir -p "$W/psock"
    systemd-run --user --quiet --collect -u "$UNIT_P" "${cap[@]}" \
        "$POSTGRES" -D "$W/pg" -k "$W/psock" -p "$PPORT" \
        -c listen_addresses=127.0.0.1 -c shared_buffers="$PG_SHARED_BUFFERS" \
        -c effective_cache_size=34GB -c work_mem=64MB -c maintenance_work_mem=1GB \
        -c random_page_cost=1.1 -c effective_io_concurrency=200 -c max_wal_size=8GB
    for _ in $(seq 100); do
        psql_admin "$PPORT" -Atc 'select 1' >/dev/null 2>&1 && return 0
        sleep 0.1
    done
    echo "run.sh: PostgreSQL did not start" >&2
    journalctl --user -u "$UNIT_P" -n 20 --no-pager || true
    exit 1
}

load_tables() {
    local port=$1 label=$2
    local file=$OUT/load-$label.tsv
    : > "$file"
    psql_at "$port" -f "$HERE/schema.sql"
    local total=0
    for t in $TABLES; do
        local t0 t1 n ms
        t0=$(date +%s%N)
        # dbgen from tpch-kit already omits the trailing '|'; an official
        # dbgen leaves it, so drop it if it is there.
        sed 's/|$//' "$DATA/$t.tbl" |
            psql_at "$port" -c "\copy $t from stdin with (format text, delimiter '|')"
        t1=$(date +%s%N)
        n=$(psql_at "$port" -Atc "select count(*) from $t")
        ms=$(( (t1 - t0) / 1000000 ))
        printf '%s\t%s\t%s\n' "$t" "$n" "$ms" >> "$file"
        total=$((total + ms))
        printf 'load  %-6s %-8s %9s rows  %7d ms\n' "$label" "$t" "$n" "$ms"
    done
    local i0 i1
    i0=$(date +%s%N)
    if [ "$TPCH_INDEXES" = conventional ]; then
        psql_at "$port" -f "$HERE/indexes.sql"
    fi
    i1=$(date +%s%N)
    echo $(( (i1 - i0) / 1000000 )) > "$OUT/index-$label.ms"
    printf 'load  %-6s indexes %d ms\n' "$label" "$(( (i1 - i0) / 1000000 ))"
    local a0 a1
    a0=$(date +%s%N)
    if [ "$label" = pg ]; then
        psql_at "$port" -c 'VACUUM (ANALYZE)'
    else
        psql_at "$port" -c 'ANALYZE'
    fi
    a1=$(date +%s%N)
    echo $(( (a1 - a0) / 1000000 )) > "$OUT/analyze-$label.ms"
    printf 'load  %-6s total %d ms (+ analyze %d ms)\n' \
        "$label" "$total" "$(( (a1 - a0) / 1000000 ))"
}

gen_data() {
    if [ ! -f "$DATA/.done" ]; then
        rm -rf "$DATA"
        mkdir -p "$DATA"
        echo "tpch: dbgen -s $SF -> $DATA"
        DSS_PATH="$DATA" DSS_CONFIG="$(dirname "$DBGEN")" DSS_DIST=dists.dss \
            "$DBGEN" -s "$SF" -f
    fi
    for t in $TABLES; do
        [ -s "$DATA/$t.tbl" ] || {
            echo "run.sh: $DATA/$t.tbl is missing; remove $DATA/.done" >&2
            exit 1
        }
    done
    : > "$DATA/.done"
}

run_bench() {
    local label=$1 unit=$2 port=$3 pgoptions=$4
    local client_timeout=$((QUERY_TIMEOUT + 30))
    local cmd=(python3 "$HERE/bench.py" --label "$label" --unit "$unit"
        --port "$port" --user "$DBUSER" --db "$DBNAME"
        --queries "$HERE/queries" --out "$OUT/$label.tsv"
        --runs "$RUNS" --timeout "$client_timeout")
    if [ -n "${TPCH_QUERIES:-}" ]; then
        cmd+=(--only "$TPCH_QUERIES")
    fi
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
    [ "$r" -eq 0 ]
}

mkdir -p "$OUT"

if [ -n "${TPCH_CHECK_ONLY:-}" ]; then
    echo "tpch: check ok"
    echo "  binary  $BIN"
    echo "  dbgen   $DBGEN"
    echo "  workdir $W (SF $SF, $RUNS runs, modes: $MODES)"
    echo "  data    $DATA ($([ -f "$DATA/.done" ] && echo present || echo 'will be generated'))"
    echo "  results $OUT"
    exit 0
fi

case "${TPCH_BOOST:-off}" in
    keep) ;;
    off)
        if [ "$BOOST_WAS" = 1 ]; then
            if sudo -n /usr/local/sbin/cpu-boost off; then
                BOOST_SET=1
            else
                echo "run.sh: cannot turn CPU boost off; install bench/tpch/cpu-boost (README.md) or set TPCH_BOOST=keep" >&2
                exit 1
            fi
        fi ;;
    *) echo "run.sh: TPCH_BOOST is off or keep" >&2; exit 2 ;;
esac

rm -f "$OUT"/lexdb.tsv "$OUT"/pg1.tsv "$OUT"/pg4.tsv \
      "$OUT"/load-*.tsv "$OUT"/analyze-*.ms "$OUT"/*.log "$OUT"/summary.md \
      "$OUT"/summary.txt
{
    printf 'scale\t%s\n' "$SF"
    printf 'runs\t%s\n' "$RUNS"
    printf 'modes\t%s\n' "$MODES"
    printf 'cpus\t%s\n' "${TPCH_CPUS:-all}"
    printf 'indexes\t%s\n' "$TPCH_INDEXES"
    printf 'lexdb_binary\t%s\n' "$BIN"
    printf 'lexdb_cpu_quota\t%s\n' "${LEXDB_CPU_QUOTA:-none}"
    printf 'lexdb_cache_mb\t%s\n' "${LEXDB_CACHE_MB:-default}"
    printf 'lexdb_ckpt_pool\t%s\n' "${LEXDB_CKPT_POOL:-default}"
    printf 'lxl_par\t%s\n' "${LXL_PAR:-default}"
    printf 'pg_cpu_quota\t%s\n' "${PG_CPU_QUOTA:-none}"
    printf 'pg_shared_buffers\t%s\n' "$PG_SHARED_BUFFERS"
    printf 'pg_binary\t%s\n' "$POSTGRES"
    # the clock the run had: boost, governor, the servers' first CPU's limits
    c0=${TPCH_CPUS%%[-,]*}; c0=${c0:-0}
    fq=/sys/devices/system/cpu/cpu$c0/cpufreq
    printf 'cpu_boost\t%s\n' "$(cat "$BOOST_FILE" 2>/dev/null || echo unknown)"
    printf 'cpu_governor\t%s\n' "$(cat "$fq/scaling_governor" 2>/dev/null || echo unknown)"
    printf 'cpu_epp\t%s\n' "$(cat "$fq/energy_performance_preference" 2>/dev/null || echo unknown)"
    printf 'cpu_max_khz\t%s\n' "$(cat "$fq/scaling_max_freq" 2>/dev/null || echo unknown)"
} > "$OUT/config.txt"
gen_data

rc=0

if want lexdb; then
    if [ ! -f "$W/lexdb.loaded" ] || [ ! -d "$W/lexdb" ]; then
        rm -rf "$W/lexdb" "$W/lexdb.loaded"
        mkdir -p "$W/lexdb"
        chattr +C "$W/lexdb" 2>/dev/null || true
        start_lexdb
        load_tables "$LPORT" lexdb
        : > "$W/lexdb.loaded"
    else
        start_lexdb
    fi
    run_bench lexdb "$UNIT_L" "$LPORT" "" || rc=1
    stop lexdb
fi

if want pg1 || want pg4; then
    if [ ! -f "$W/pg.loaded" ] || [ ! -d "$W/pg" ]; then
        rm -rf "$W/pg" "$W/pg.loaded"
        mkdir -p "$W/pg"
        chattr +C "$W/pg" 2>/dev/null || true
        "$INITDB" -D "$W/pg" -U "$DBUSER" --auth=trust -E UTF8 --no-locale \
            >/dev/null
        start_pg
        psql_admin "$PPORT" -c "create database $DBNAME"
        load_tables "$PPORT" pg
        : > "$W/pg.loaded"
    else
        start_pg
    fi
    if want pg1; then
        run_bench pg1 "$UNIT_P" "$PPORT" \
            "-c max_parallel_workers_per_gather=0" || rc=1
    fi
    if want pg4; then
        run_bench pg4 "$UNIT_P" "$PPORT" \
            "-c max_parallel_workers_per_gather=3 -c max_parallel_workers=3" || rc=1
    fi
    stop pg
fi

if [ -f "$OUT/lexdb.tsv" ] || [ -f "$OUT/pg1.tsv" ] || [ -f "$OUT/pg4.tsv" ]; then
    python3 "$HERE/compare.py" "$OUT" ${TPCH_REF:+"$TPCH_REF"} | tee "$OUT/summary.txt"
    echo "tpch: results in $OUT/summary.md"
else
    echo "tpch: no results to compare" >&2
    rc=1
fi
exit "$rc"
