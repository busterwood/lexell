#!/bin/bash
# fetch.sh: fetch the ClickBench hits TSV dataset (full 100M or a prefix slice).
#
#   bench/clickbench/fetch.sh WORKDIR [ROWS]
#
# ROWS defaults to 1000000 (1M rows, ~170 MB downloaded over the wire, ~700 MB
# uncompressed TSV). Pass 10000000 (10M) or 'all' (full ~99.99M rows) as needed.
# Writes WORKDIR/hits_<ROWS>.tsv and WORKDIR/hits_<ROWS>.done.
set -euo pipefail

if [ $# -lt 1 ]; then
    echo "usage: $0 WORKDIR [ROWS]" >&2
    exit 2
fi

W=$1
ROWS=${2:-1000000}
URL=${CLICKBENCH_URL:-https://datasets.clickhouse.com/hits_compatible/hits.tsv.gz}

mkdir -p "$W"
W=$(realpath "$W")
OUT="$W/hits_${ROWS}.tsv"
DONE="$W/hits_${ROWS}.done"

if [ -f "$DONE" ] && [ -s "$OUT" ]; then
    echo "$OUT"
    exit 0
fi

TMP="$OUT.tmp"
rm -f "$TMP" "$DONE"

if [ "$ROWS" = "all" ] || [ "$ROWS" = "100000000" ]; then
    echo "clickbench: downloading full hits.tsv.gz -> $OUT" >&2
    curl -fsSL "$URL" | gzip -dc > "$TMP"
else
    case "$ROWS" in
        ''|*[!0-9]*) echo "fetch.sh: ROWS must be a positive integer or 'all'" >&2; exit 2 ;;
    esac
    echo "clickbench: streaming first $ROWS rows from hits.tsv.gz -> $OUT" >&2
    # head closes its pipe once ROWS lines are written, causing curl/gzip to exit
    # with SIGPIPE (141) — expected and handled cleanly below.
    set +o pipefail
    curl -fsSL "$URL" | gzip -dc | head -n "$ROWS" > "$TMP"
    set -o pipefail
    GOT=$(wc -l < "$TMP")
    if [ "$GOT" -lt "$ROWS" ]; then
        echo "fetch.sh: expected $ROWS rows, got $GOT" >&2
        rm -f "$TMP"
        exit 1
    fi
fi

mv "$TMP" "$OUT"
: > "$DONE"
echo "$OUT"
