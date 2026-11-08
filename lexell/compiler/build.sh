#!/bin/sh
# Builds the Lexell compiler, out/lxlc, from the checked-in seed: only gcc is needed.
#     lexell/compiler/build.sh
# out/lxlc finds the library at ../../lib (lexell/lib); set LXL_LIB to use another.
set -e
D=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$D/out"
gcc -O2 -w -std=gnu11 -o "$D/out/lxlc" "$D/seed/lxlc.c" -lm
echo "built $D/out/lxlc"
