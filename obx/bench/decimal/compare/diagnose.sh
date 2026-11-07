#!/bin/sh
# Threshold and breakdown diagnostics for decimal-performance.md.
#
#     ./diagnose.sh
#
# Prints: where obx's add/mul time goes; .NET decimal's multiply path
# thresholds; Java BigDecimal's compact-value thresholds.  Same toolchain
# environment as run.sh.
set -e
D=$(cd "$(dirname "$0")" && pwd)
OBXC=${OBXC:-$D/../../../compiler/out/obxc}
OBX_LIB=${OBX_LIB:-$D/../../../lib}
DOTNET=${DOTNET:-dotnet}
JAVAC=${JAVAC:-javac}
JAVA=${JAVA:-java}
CPU=${CPU:-2}
TMP=${TMP:-$(mktemp -d)}
: "${XDG_RUNTIME_DIR:=/tmp/xdg}"

mkdir -p "$XDG_RUNTIME_DIR"
export XDG_RUNTIME_DIR OBX_LIB
export DOTNET_NOLOGO=1 DOTNET_SKIP_FIRST_TIME_EXPERIENCE=1
export DOTNET_TieredCompilation=0 DOTNET_TieredPGO=0

echo "building in $TMP"
"$OBXC" "$D/variants.obx" --native -O -o "$TMP/variants"
"$JAVAC" -d "$TMP" "$D/Scale.java"
mkdir -p "$TMP/cs2"
cp "$D/Scale.cs" "$D/Scale.csproj" "$TMP/cs2/"
"$DOTNET" build "$TMP/cs2/Scale.csproj" -c Release -o "$TMP/cs2/out" >/dev/null

echo "== obx: where add/mul time goes (ns/op)"
taskset -c "$CPU" "$TMP/variants"

echo "== .NET decimal: multiply path thresholds (ns/op)"
for d in 6 9 10 13; do
    taskset -c "$CPU" "$DOTNET" "$TMP/cs2/out/Scale.dll" mul "$d" 4000
done
echo "== .NET decimal: add is flat (ns/op)"
for d in 9 19 26; do
    taskset -c "$CPU" "$DOTNET" "$TMP/cs2/out/Scale.dll" add "$d" 4000
done

echo "== Java BigDecimal: multiply path thresholds (ns/op)"
for d in 6 9 10 12 19 38; do
    taskset -c "$CPU" "$JAVA" -Xms2g -Xmx2g -cp "$TMP" Scale mul "$d" 4000
done
echo "== Java BigDecimal: add path thresholds (ns/op)"
for d in 9 18 19 26 38; do
    taskset -c "$CPU" "$JAVA" -Xms2g -Xmx2g -cp "$TMP" Scale add "$d" 4000
done
