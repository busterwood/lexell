#!/usr/bin/env bash
# usage: lexell/tools/gate.sh quick|full|live
# quick: the C seed's fixed point (it also builds compiler/out/lxlc from the seed, the compiler
#        every later step uses), the conformance suite, the compiler tests, the library tests,
#        the native backend against the C backend (run + lib tests; with io_uring where the kernel
#        has it, and again with epoll and the helper pool, LXL_URING=0) and the native self-build.
# full:  quick, then the red-team harnesses (rounds 1-5) and the task, net, url, http and http
#        server library tests under ASan+UBSan, the helper-pool and net tests under TSan, then
#        the native backend on the red-team corpora and on generated value-record and array-loop
#        programs, the http client on generated reply framings (both backends), the http server's
#        request parsing against Go's net/http and Node's llhttp on generated request streams
#        (each oracle skipped when not installed), the regex tests under ASan+UBSan and the regex
#        library against Go's regexp on random patterns (skipped without go).
# live:  the library tests that need a database or another running service (the `*_live*`
#        tests), and the native backend on the same. These are not part of quick or full so
#        that those tiers stay hermetic and deterministic.
# Builds are cached (tools/cbuild.py; LXL_NOCACHE=1 disables, LXL_CACHE sets the directory).
set -u
tier=${1:-}
case "$tier" in quick|full|live) ;; *) echo "usage: $0 quick|full|live" >&2; exit 2;; esac
R=$(cd "$(dirname "$0")/../.." && pwd)
cd "$R"
if [ "$tier" = live ]; then
  steps=(
    "lib (live)|python3 lexell/lib/run_tests.py --live -j 8"
    "native lib+run (live)|python3 lexell/tests/run_native.py --lib --live"
    "redteam live|python3 lexell/redteam/rt.py lexell/lib/tests/run/pgwire_live.lxl lexell/lib/tests/run/pgwire_live_tls.lxl lexell/lib/tests/run/task_postgres_async.lxl lexell/lib/tests/run/task_postgres_pool.lxl"
    "redteam live tsan|LXL_SAN=thread python3 lexell/redteam/rt.py lexell/lib/tests/run/task_postgres_async.lxl lexell/lib/tests/run/task_postgres_pool.lxl"
  )
else
  steps=(
    "seed fixed point|python3 lexell/tools/seed_check.py"
    "conformance|python3 lexell/tests/run.py"
    "compiler tests|python3 lexell/tests/compiler/run_tests.py"
    "lib|python3 lexell/lib/run_tests.py -j 8"
    "native lib+run|python3 lexell/tests/run_native.py --lib"
    "native -O lib+run|python3 lexell/tests/run_native.py --lib --opt"
    "native lib epoll|LXL_URING=0 python3 lexell/tests/run_native.py --lib"
    "native selfbuild|bash lexell/tools/native_selfbuild.sh"
  )
fi
if [ "$tier" = full ]; then
  steps+=(
    "redteam round 1|python3 lexell/redteam/rt.py"
    "redteam round 2|python3 lexell/redteam/round2/rt.py"
    "redteam round 3|python3 lexell/redteam/round3/rt.py"
    "redteam round 4|python3 lexell/redteam/round4/rt.py"
    "redteam round 5|python3 lexell/redteam/round5/rt.py"
    "redteam tasks|python3 lexell/redteam/rt.py $(ls lexell/lib/tests/run/task_*.lxl lexell/lib/tests/run/net_*.lxl lexell/lib/tests/run/proc_*.lxl lexell/lib/tests/run/url_*.lxl lexell/lib/tests/run/http_*.lxl lexell/lib/tests/run/pgwire_*.lxl lexell/lib/tests/run/redis_*.lxl | grep -v -e '_live' -e 'task_postgres_' | tr '\n' ' ')"
    "redteam regex|python3 lexell/redteam/rt.py lexell/lib/tests/run/regex_*.lxl lexell/lib/tests/run/regex_re2search/main.lxl"
    "redteam tsan|LXL_SAN=thread python3 lexell/redteam/rt.py lexell/lib/tests/run/task_blocking_*.lxl lexell/lib/tests/run/net_*.lxl lexell/lib/tests/run/redis_basic.lxl"
    "native redteam|python3 lexell/tests/run_native.py --lib --redteam"
    "native generated|python3 lexell/tests/vrgen.py -n 200"
    "native loops gen|python3 lexell/tests/loopgen.py -n 200"
    "http framing gen|python3 lexell/tests/httpgen.py -n 40"
    "http server gen|python3 lexell/tests/httpsrvgen.py -n 5000"
    "regex vs Go|python3 lexell/tests/regexgen.py --fast"
  )
fi
log=$(mktemp -d); status=0; summary=(); t0=$SECONDS
for st in "${steps[@]}"; do
  name=${st%%|*}; cmd=${st#*|}; t=$SECONDS
  echo ">> $name: $cmd"
  bash -c "$cmd" > "$log/out.txt" 2>&1; rc=$?
  tail -n 3 "$log/out.txt"
  # the red-team runners exit 0 whatever they find: any class but OK is a failure
  if [[ $name == redteam* ]] && grep -Eq '^[A-Z]+ +[A-Za-z0-9_]+:' "$log/out.txt"; then rc=1; grep -E '^[A-Z]+ +[A-Za-z0-9_]+:' "$log/out.txt" | head -20; fi
  [ $rc -ne 0 ] && { status=1; [[ $name != redteam* ]] && tail -n 30 "$log/out.txt"; }
  summary+=("$(printf '%-18s %-5s %4ds' "$name" "$([ $rc -eq 0 ] && echo ok || echo FAIL)" $((SECONDS - t)))")
done
echo; echo "== $tier gate"; printf '%s\n' "${summary[@]}"
echo "total $((SECONDS - t0))s: $([ $status -eq 0 ] && echo PASS || echo FAIL)"
rm -rf "$log"; exit $status
