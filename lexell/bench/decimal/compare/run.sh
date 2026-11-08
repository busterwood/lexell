#!/bin/sh
# Builds and runs the three matched decimal harnesses and prints one line per
# case. Needs the Lexell compiler, a C# toolchain (dotnet) and a JDK.
#
#     ./run.sh                    # runs on CPU 2
#     CPU=10 ./run.sh
#     DOTNET=... JAVAC=... JAVA=... LXLC=... ./run.sh
#
# On WSL, .NET's first run wants a writable XDG_RUNTIME_DIR:
#     XDG_RUNTIME_DIR=/tmp/xdg ./run.sh
set -e
D=$(cd "$(dirname "$0")" && pwd)
LXLC=${LXLC:-$D/../../../compiler/out/lxlc}
LXL_LIB=${LXL_LIB:-$D/../../../lib}
DOTNET=${DOTNET:-dotnet}
JAVAC=${JAVAC:-javac}
JAVA=${JAVA:-java}
CPU=${CPU:-2}
TMP=${TMP:-$(mktemp -d)}
: "${XDG_RUNTIME_DIR:=/tmp/xdg}"

mkdir -p "$XDG_RUNTIME_DIR"
export XDG_RUNTIME_DIR LXL_LIB
export DOTNET_NOLOGO=1 DOTNET_SKIP_FIRST_TIME_EXPERIENCE=1
export DOTNET_TieredCompilation=0 DOTNET_TieredPGO=0

echo "building in $TMP"
"$LXLC" "$D/decbench.lxl" --native -O -o "$TMP/decbench-lxl"
"$LXLC" "$D/decbench-big.lxl" --native -O -o "$TMP/decbench-big-lxl"
"$JAVAC" -d "$TMP" "$D/DecBench.java" "$D/DecBenchBig.java"
cp "$D/DecBench.csproj" "$D/DecBench.cs" "$TMP/"
"$DOTNET" build "$TMP/DecBench.csproj" -c Release -o "$TMP/cs" >/dev/null

echo "== lxl (native -O)"
taskset -c "$CPU" "$TMP/decbench-lxl"
taskset -c "$CPU" "$TMP/decbench-big-lxl"
echo "== .NET System.Decimal"
taskset -c "$CPU" "$DOTNET" "$TMP/cs/DecBench.dll"
echo "== Java BigDecimal"
taskset -c "$CPU" "$JAVA" -Xms2g -Xmx2g -cp "$TMP" DecBench
taskset -c "$CPU" "$JAVA" -Xms2g -Xmx2g -cp "$TMP" DecBenchBig
