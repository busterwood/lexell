#!/bin/bash
# selfhost.sh: build the self-hosted compiler (lexell/compiler, which uses if/match expressions, late
# borrows and constant arms since 193fdae) with ASan+UBSan, and run its --dump-ast and --dump-types
# on every test and red-team program under LXL_CHECK=1. Reports sanitizer errors, leaks and
# crashes (exit codes other than 0 and 1). -O0: at -O1 LeakSanitizer reports false leaks when the
# program stops through exit(1) with pointers still in registers.
here=$(cd "$(dirname "$0")" && pwd)
root="$here/../.."
b="$here/build/selfhost"
mkdir -p "$b"
export LXL_LIB="$root/lib"
"${LXLC:-$root/compiler/out/lxlc}" "$root/compiler/main.lxl" --emit-c > "$b/lxlc.c" || exit 1
${CC:-gcc} -g -O0 -std=gnu11 -fsanitize=address,undefined -fno-sanitize-recover=undefined -w -o "$b/lxlc" "$b/lxlc.c" -lm || exit 1
bad=0; n=0
for f in $(find "$root/tests" "$root/redteam" "$root/compiler/tests" -path '*/build*' -prune -o -name '*.lxl' -print | sort); do
  for mode in --dump-ast --dump-types; do
    n=$((n+1))
    LXL_CHECK=1 ASAN_OPTIONS=detect_leaks=1:exitcode=99 "$b/lxlc" $mode "$f" > /dev/null 2> "$b/err.txt"
    rc=$?
    if [ $rc -ne 0 ] && [ $rc -ne 1 ]; then
      bad=$((bad+1)); echo "rc=$rc $mode $f: $(grep -m1 -E 'ERROR|runtime error|Lexell:' "$b/err.txt")"
    fi
  done
done
echo "runs=$n bad=$bad"
