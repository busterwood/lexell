#!/bin/sh
# Checks that a change to the compiler's source keeps its behaviour: builds a compiler from the
# source as it is now (with compiler/out/lxlc), then compiles every program with both and compares
# the C they emit. Prints the programs whose C differs (and those only one compiler rejects);
# nothing means the same output everywhere. Exits 1 on a difference.
#     lexell/tools/same_output.sh            P sets the parallel compiles (default 4)
set -e
D=$(cd "$(dirname "$0")/.." && pwd)
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
export LXL_LIB="$D/lib" T
cd "$D"
OLD="$D/compiler/out/lxlc"
"$OLD" compiler/main.lxl --native -o "$T/new" || { echo "the edited compiler does not build" >&2; exit 1; }
export OLD
{ echo compiler/main.lxl
  find tests cmd lib/tests lib/examples bench redteam design/experiments -name '*.lxl' |
      grep -v -e '^tests/error' -e '^lib/tests/error' | xargs grep -l '^fn main'
} > "$T/progs"
xargs -P "${P:-4}" -I{} sh -c '
    a=$("$OLD" "{}" --emit-c 2>&1 | md5sum)
    b=$("$T/new" "{}" --emit-c 2>&1 | md5sum)
    [ "$a" = "$b" ] || echo "DIFF {}"' < "$T/progs" > "$T/out"
sort "$T/out"
[ ! -s "$T/out" ]
