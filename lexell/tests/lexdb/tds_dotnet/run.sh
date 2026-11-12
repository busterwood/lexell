#!/usr/bin/env bash
# usage: tests/lexdb/tds_dotnet/run.sh "Server=127.0.0.1,1433;User Id=sa;Password=x;TrustServerCertificate=true"
#
# Microsoft.Data.SqlClient (6) against a server speaking TDS, in the .NET SDK
# image (rootless podman, host network): parameters (sp_executesql), a
# prepared statement (sp_prepexec, sp_execute), an OUTPUT parameter,
# transactions (Transaction Manager requests), an error's number and class,
# and a pooled connection reset (RESETCONNECTION). Run it against lexdb's
# --tds listener and against the oracle (tools/mssql_container.sh: its DSN in
# ~/.obo-mssql-dsn) and compare: the database's name is all that differs
# (design/lexdb-tds.md). The table it makes, people, must not exist.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cp "$here/Program.cs" "$here/tds_dotnet.csproj" "$work/"
podman run --rm --network host -v "$work:/src:Z" -w /src mcr.microsoft.com/dotnet/sdk:9.0 \
  sh -c 'dotnet build -o out -v q >/dev/null && dotnet out/tds_dotnet.dll "$0"' "$1"
