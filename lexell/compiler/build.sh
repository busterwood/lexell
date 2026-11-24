#!/bin/sh
# Builds the Lexell compiler, out/lxlc, from the checked-in seed: only gcc is needed.
#     lexell/compiler/build.sh
# Stage 1 is the seed's C built with gcc (out/lxlc.seed). On x86-64 Linux, stage 1 then builds the
# compiler natively from the sources, and that is out/lxlc: the compiler runs as the native
# backend compiles it, which is the backend Lexell is meant to be fast with. Elsewhere, or when
# the native build fails (a source change that does not compile yet), out/lxlc is stage 1.
# LXL_SEED_ONLY=1 keeps stage 1 as out/lxlc.
# out/lxlc finds the library at ../../lib (lexell/lib); set LXL_LIB to use another.
set -e
D=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$D/out"
gcc -O2 -w -std=gnu11 -o "$D/out/lxlc.seed" "$D/seed/lxlc.c" -lm
if [ "$(uname -sm)" = "Linux x86_64" ] && [ "${LXL_SEED_ONLY:-0}" != 1 ]; then
    if LXL_LIB="${LXL_LIB:-$D/../lib}" "$D/out/lxlc.seed" "$D/main.lxl" --native -o "$D/out/lxlc.tmp"; then
        mv "$D/out/lxlc.tmp" "$D/out/lxlc"
        echo "built $D/out/lxlc (native, built by the seed's gcc build out/lxlc.seed)"
        exit 0
    fi
    rm -f "$D/out/lxlc.tmp"
    echo "build.sh: the native build failed; out/lxlc is the seed's gcc build" >&2
fi
cp "$D/out/lxlc.seed" "$D/out/lxlc"
echo "built $D/out/lxlc"
