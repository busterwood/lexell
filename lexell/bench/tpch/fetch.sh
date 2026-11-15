#!/bin/bash
# fetch.sh: get and build dbgen for the TPC-H derived workload.
#
#   bench/tpch/fetch.sh DIR
#
# DIR gets a checkout of tpch-kit at a fixed commit, built with
# MACHINE=LINUX DATABASE=POSTGRESQL. Its dbgen is DIR/dbgen/dbgen.
# run.sh looks there by default (WORKDIR/tpch-kit), or take TPCH_DBGEN.
#
# tpch-kit is Greg Rahn's copy of the TPC-H tools; its dbgen is the
# official generator with the trailing record delimiter removed. The
# generator and its distribution file are the TPC's, under the TPC-H
# tools' terms, not this repository's license. Nothing is added to git.
set -euo pipefail

DIR=${1:-}
if [ -z "$DIR" ]; then
    echo "usage: $0 DIR" >&2
    exit 2
fi

REPO=https://github.com/gregrahn/tpch-kit.git
COMMIT=852ad0a5ee31ebefeed884cea4188781dd9613a3

if [ ! -d "$DIR/.git" ]; then
    mkdir -p "$(dirname "$DIR")"
    git clone --quiet "$REPO" "$DIR"
fi

if ! git -C "$DIR" cat-file -e "$COMMIT^{commit}" 2>/dev/null; then
    git -C "$DIR" fetch --quiet origin "$COMMIT"
fi
git -C "$DIR" checkout --quiet "$COMMIT"

make -C "$DIR/dbgen" MACHINE=LINUX DATABASE=POSTGRESQL >/dev/null

if [ ! -x "$DIR/dbgen/dbgen" ]; then
    echo "fetch.sh: $DIR/dbgen/dbgen was not built" >&2
    exit 1
fi
if [ ! -f "$DIR/dbgen/dists.dss" ]; then
    echo "fetch.sh: $DIR/dbgen/dists.dss is missing" >&2
    exit 1
fi
echo "$DIR/dbgen/dbgen"
