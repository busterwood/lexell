#!/usr/bin/env bash
# End-to-end driver & ORM compatibility verification suite across all three LexDB doors
# (PostgreSQL, SQL Server / TDS, Oracle / TNS).
#
# Usage:
#   ./run.sh [--all | --python | --dotnet | --node] [--lexdb PATH]
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LEXELL_DIR="$(cd "$DIR/../../.." && pwd)"
CACHE="$DIR/.cache"
mkdir -p "$CACHE"

RUN_PY=0
RUN_NET=0
RUN_NODE=0
LEXDB_BIN=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --all) RUN_PY=1; RUN_NET=1; RUN_NODE=1; shift ;;
    --python) RUN_PY=1; shift ;;
    --dotnet) RUN_NET=1; shift ;;
    --node) RUN_NODE=1; shift ;;
    --lexdb) LEXDB_BIN="$2"; shift 2 ;;
    -h|--help)
      echo "Usage: $0 [--all | --python | --dotnet | --node] [--lexdb PATH]"
      exit 0
      ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done

if [[ $RUN_PY -eq 0 && $RUN_NET -eq 0 && $RUN_NODE -eq 0 ]]; then
  RUN_PY=1; RUN_NET=1; RUN_NODE=1
fi

if [[ -z "$LEXDB_BIN" ]]; then
  LEXDB_BIN="$CACHE/lexdb"
  echo "Building lexdb -> $LEXDB_BIN ..."
  (cd "$LEXELL_DIR" && ./compiler/out/lxlc cmd/lexdb.lxl -O -o "$LEXDB_BIN")
fi

PG_PORT="${PG_PORT:-15433}"
TDS_PORT="${TDS_PORT:-11433}"
ORA_PORT="${ORA_PORT:-11521}"
export PG_PORT TDS_PORT ORA_PORT

SRV_PID=""
TMP_DATA=""
cleanup() {
  if [[ -n "$SRV_PID" ]]; then
    kill "$SRV_PID" 2>/dev/null || true
    wait "$SRV_PID" 2>/dev/null || true
    SRV_PID=""
  fi
  if [[ -n "$TMP_DATA" && -d "$TMP_DATA" ]]; then
    rm -rf "$TMP_DATA"
    TMP_DATA=""
  fi
}
trap cleanup EXIT

start_fresh_server() {
  cleanup
  TMP_DATA="$(mktemp -d)"
  "$LEXDB_BIN" "$TMP_DATA" "127.0.0.1:$PG_PORT" --tds "127.0.0.1:$TDS_PORT" --tns "127.0.0.1:$ORA_PORT" >"$CACHE/server.log" 2>&1 &
  SRV_PID=$!
  for _ in $(seq 1 50); do
    if ss -tln | grep -q ":$PG_PORT "; then return 0; fi
    sleep 0.1
  done
  echo "ERROR: lexdb failed to listen on :$PG_PORT (see $CACHE/server.log)" >&2
  tail -n 20 "$CACHE/server.log" >&2 || true
  exit 1
}

FAILS=0

# ---- Python suite (psycopg3, asyncpg, pymssql, oracledb, SQLAlchemy, Alembic, Django) ----
if [[ $RUN_PY -eq 1 ]]; then
  VENV="$CACHE/venv"
  if [[ ! -x "$VENV/bin/python" ]]; then
    echo "Setting up Python test venv in $VENV ..."
    if command -v uv >/dev/null 2>&1; then
      uv venv "$VENV"
      uv pip install --python "$VENV/bin/python" sqlalchemy alembic django "psycopg[binary]" asyncpg pymssql oracledb
    else
      python3 -m venv "$VENV"
      "$VENV/bin/pip" install -q sqlalchemy alembic django "psycopg[binary]" asyncpg pymssql oracledb
    fi
  fi
  start_fresh_server
  "$VENV/bin/python" "$DIR/test_pg_door.py" || FAILS=$((FAILS + 1))
  echo ""
  "$VENV/bin/python" "$DIR/test_tds_door.py" || FAILS=$((FAILS + 1))
  echo ""
  "$VENV/bin/python" "$DIR/test_ora_door.py" || FAILS=$((FAILS + 1))
  echo ""
fi

# ---- .NET suite (EF Core Npgsql, EF Core SqlServer, Oracle.ManagedDataAccess.Core) ----
if [[ $RUN_NET -eq 1 ]]; then
  if command -v dotnet >/dev/null 2>&1; then
    dotnet build -v q "$DIR/efcore/EfCompat.csproj" >/dev/null
    EF_BIN="$DIR/efcore/bin/Debug/net10.0/EfCompat"
    for d in PG TDS ORA; do
      start_fresh_server
      DOORS="$d" "$EF_BIN" || FAILS=$((FAILS + 1))
      echo ""
    done
  else
    echo "[SKIP] .NET suite (dotnet not installed)"
  fi
fi

# ---- Node.js suite (pg + Knex, mssql + Knex, node-oracledb thin) ----
if [[ $RUN_NODE -eq 1 ]]; then
  if command -v node >/dev/null 2>&1 && command -v npm >/dev/null 2>&1; then
    if [[ ! -d "$DIR/node/node_modules" ]]; then
      echo "Installing Node.js dependencies in $DIR/node ..."
      (cd "$DIR/node" && npm install --no-audit --no-fund --silent)
    fi
    start_fresh_server
    node "$DIR/node/test_node.mjs" || FAILS=$((FAILS + 1))
    echo ""
  else
    echo "[SKIP] Node.js suite (node/npm not installed)"
  fi
fi

cleanup
if [[ $FAILS -gt 0 ]]; then
  echo "Compat suite finished with $FAILS failing sub-suite(s)." >&2
  exit 1
fi
echo "All compatibility sub-suites passed."
