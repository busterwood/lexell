#!/bin/sh
# The LXL_OWNED_STR worklist (design/owned-str.md): every site that would need an edit if str
# were owned, over the compiler and every program in tests/, cmd/, lib/tests/, lib/examples/, bench/,
# redteam/ and design/experiments/ (not lexdb).
#     lexell/tools/owned_str_sweep.sh [-a] [file.lxl ...]
# Prints "kind file:line name what-took-it", sorted and unique. With file names (base names, such
# as fs.lxl), only the sites in those files. Free moves (kind "move") are left out unless -a.
# LXLC is the compiler to use (default compiler/out/lxlc); P the parallel compiles (default 4). Programs the mode cannot finish are
# listed on stderr as "STOPPED file: error"; a program that does not compile even without the flag
# (other than an error test) as "BROKEN file: error", so a broken build never looks like a clean one. LXL_OWNED_STR= (empty) measures something else alone, such as
# LXL_OWNED_SHARED=1.
set -e
D=$(cd "$(dirname "$0")/.." && pwd)
LXLC=${LXLC:-$D/compiler/out/lxlc}
ALL=0
if [ "$1" = "-a" ]; then ALL=1; shift; fi
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
LXL_OWNED_STR=${LXL_OWNED_STR-1}
export LXL_LIB="$D/lib" LXL_OWNED_STR LXLC T
cd "$D"
{ echo compiler/main.lxl
  find tests cmd lib/tests lib/examples bench redteam design/experiments -name '*.lxl' | grep -v -i lexdb |
      grep -v -e '^tests/error' -e '^lib/tests/error' |
      xargs grep -l '^fn main'
} > "$T/progs"
# Each program: its notes into $T/<n>.log; a program the checker stops on is reported, unless it
# also stops without the flag (an expected-error test).
n=0
while read -r f; do n=$((n + 1)); echo "$n $f"; done < "$T/progs" |
    xargs -P "${P:-4}" -L 1 sh -c '
        if ! timeout 60 "$LXLC" "$1" --emit-c > /dev/null 2> "$T/$0.err"; then
            if LXL_OWNED_STR= LXL_OWNED_SHARED= timeout 60 "$LXLC" "$1" --emit-c > /dev/null 2>&1; then
                echo "STOPPED $1: $(grep -v "^OWNED_STR" "$T/$0.err" | head -1)" >&2
            else
                # fails without the flag too: an error test, or a program the edits broke
                case "$1" in */error/*) ;; *) grep -q "^ *// *error:" "$1" ||
                    echo "BROKEN $1: $(grep -v "^OWNED_STR" "$T/$0.err" | head -1)" >&2 ;; esac
            fi
        fi
        grep "^OWNED_STR" "$T/$0.err" > "$T/$0.log" || true'
cat "$T"/*.log | sed 's/^OWNED_STR //' | sort -u > "$T/all"
if [ $ALL -eq 0 ]; then grep -v '^move ' "$T/all" > "$T/sel" || true; else cp "$T/all" "$T/sel"; fi
if [ $# -gt 0 ]; then
    for b in "$@"; do grep -E "^[a-z]+ $b:" "$T/sel" || true; done
else
    cat "$T/sel"
fi
