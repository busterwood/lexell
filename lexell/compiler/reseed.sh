#!/bin/sh
# Rebuilds seed/lxlc.c from the current sources and checks the fixed point:
# out/lxlc builds stage 2, stage 2 builds stage 3, and the C of stages 2 and 3
# must be identical. Run it after changing the compiler (build out/lxlc first,
# with build.sh). tools/seed_check.py checks the same without writing the seed.
#     lexell/compiler/reseed.sh
set -e
D=$(cd "$(dirname "$0")" && pwd)
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
export LXL_LIB="$D/../lib"
python3 "$D/gen_rt.py" >/dev/null
"$D/out/lxlc" "$D/main.lxl" --c -o "$T/s2"
"$T/s2" "$D/main.lxl" --emit-c > "$T/c2.c"
"$T/s2" "$D/main.lxl" --c -o "$T/s3"
"$T/s3" "$D/main.lxl" --emit-c > "$T/c3.c"
cmp "$T/c2.c" "$T/c3.c" || { echo "reseed: no fixed point: stage 2 and stage 3 C differ" >&2; exit 1; }
cp "$T/c2.c" "$D/seed/lxlc.c"
echo "seed/lxlc.c: fixed point reached ($(wc -c < "$D/seed/lxlc.c") bytes)"
