#!/usr/bin/env bash
# usage: lexell/tools/mssql_container.sh create|start|stop|status|logs|sql|rm
#
# The SQL Server container for the live `sqlserver` tests (design/tds.md) and
# for checking lexdb's TDS endpoint and T-SQL against the real thing: rootless
# podman, image mcr.microsoft.com/mssql/server:2022-latest (Developer edition),
# named lxl-mssql, port 1433 published on 127.0.0.1:14330 only, so that 1433
# stays free for lexdb. `create` pulls the image, makes a random sa password,
# starts the container and writes the test connection string to
# ~/.obo-mssql-dsn (mode 600), where the live tests look for it. No password
# is printed. Running the image accepts Microsoft's licence for it
# (ACCEPT_EULA=Y).
#
# Not 2025-latest: on this machine's kernel (7.2) SQL Server 2025's sqlservr
# dies at startup inside its lsass/samsrv layer (Reason 0x00000002); 2022
# starts.
#
# `sql` runs a batch on stdin through sqlcmd in the container (as sa), for
# looking at what the real server does: echo "SELECT @@VERSION" | ... sql
set -u
if [ -z "${XDG_RUNTIME_DIR:-}" ] || [ ! -w "${XDG_RUNTIME_DIR:-}" ]; then
  export XDG_RUNTIME_DIR=/tmp/lxl-podman-$(id -u)
  mkdir -p -m 700 "$XDG_RUNTIME_DIR"
fi
NAME=lxl-mssql
IMAGE=mcr.microsoft.com/mssql/server:2022-latest
PORT=14330
DSN_FILE=$HOME/.obo-mssql-dsn
SA_FILE=$HOME/.obo-mssql-sa
P=podman

# 3 of SQL Server's 4 classes: upper, lower, digit
pw() { local s; s=$(head -c 200 /dev/urandom | tr -dc 'A-Za-z0-9' | head -c 24); echo "Lx${s}7"; }

wait_ready() {
  for _ in $(seq 1 60); do
    if $P logs $NAME 2>/dev/null | grep -q 'Recovery is complete'; then echo "ready"; return 0; fi
    if [ "$($P inspect -f '{{.State.Running}}' $NAME 2>/dev/null)" != true ]; then echo "not running"; return 1; fi
    sleep 3
  done
  echo "not ready after 3 minutes"; return 1
}

case "${1:-}" in
  create)
    if $P container exists $NAME 2>/dev/null; then echo "$NAME exists: use start"; exit 1; fi
    $P pull -q $IMAGE >/dev/null || exit 1
    sa=$(pw)
    umask 077
    env_file=$(mktemp)
    printf 'ACCEPT_EULA=Y\nMSSQL_PID=Developer\nMSSQL_SA_PASSWORD=%s\n' "$sa" > "$env_file"
    $P run -d --name $NAME --restart=on-failure -p 127.0.0.1:$PORT:1433 \
      -v $NAME-data:/var/opt/mssql --env-file "$env_file" $IMAGE >/dev/null
    rc=$?
    rm -f "$env_file"
    [ $rc -eq 0 ] || exit $rc
    printf '%s\n' "$sa" > "$SA_FILE"
    printf 'Server=127.0.0.1,%s;UID=sa;PWD=%s;TrustServerCertificate=yes\n' $PORT "$sa" > "$DSN_FILE"
    chmod 600 "$SA_FILE" "$DSN_FILE"
    echo "created $NAME on 127.0.0.1:$PORT; test DSN in $DSN_FILE"
    wait_ready
    ;;
  start) $P start $NAME >/dev/null && wait_ready ;;
  stop) $P stop $NAME >/dev/null && echo stopped ;;
  status) $P ps -a --filter name=$NAME --format '{{.Names}} {{.Status}} {{.Ports}}' ;;
  logs) $P logs --tail 40 $NAME 2>&1 | grep -v -i password ;;
  sql)
    # the password goes in through the environment, not the command line
    $P exec -i -e SQLCMDPASSWORD="$(cat "$SA_FILE")" $NAME \
      /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -C -b -W -s '|' "${@:2}"
    ;;
  rm) $P rm -f $NAME >/dev/null && $P volume rm -f $NAME-data >/dev/null && rm -f "$DSN_FILE" "$SA_FILE" && echo removed ;;
  *) echo "usage: $0 create|start|stop|status|logs|sql|rm" >&2; exit 2 ;;
esac
