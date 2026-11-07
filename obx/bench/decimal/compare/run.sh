#!/bin/sh
# Builds and runs the three matched decimal harnesses and prints one line per
# case. Needs the obx compiler, a C# toolchain (dotnet) and a JDK.
#
#     ./run.sh                    # runs on CPU 2
#     CPU=10 ./run.sh
#     DOTNET=... JAVAC=... JAVA=... OBXC=... ./run.sh
#
# On WSL, .NET's first run wants a writable XDG_RUNTIME_DIR:
#     XDG_RUNTIME_DIR=/tmp/xdg ./run.sh
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
"$OBXC" "$D/decbench.obx" --native -O -o "$TMP/decbench-obx"
"$OBXC" "$D/decbench-big.obx" --native -O -o "$TMP/decbench-big-obx"
"$JAVAC" -d "$TMP" "$D/DecBench.java" "$D/DecBenchBig.java"
cp "$D/DecBench.csproj" "$D/DecBench.cs" "$TMP/"
"$DOTNET" build "$TMP/DecBench.csproj" -c Release -o "$TMP/cs" >/dev/null

echo "== obx (native -O)"
taskset -c "$CPU" "$TMP/decbench-obx"
taskset -c "$CPU" "$TMP/decbench-big-obx"
echo "== .NET System.Decimal"
taskset -c "$CPU" "$DOTNET" "$TMP/cs/DecBench.dll"
echo "== Java BigDecimal"
taskset -c "$CPU" "$JAVA" -Xms2g -Xmx2g -cp "$TMP" DecBench
taskset -c "$CPU" "$JAVA" -Xms2g -Xmx2g -cp "$TMP" DecBenchBig
