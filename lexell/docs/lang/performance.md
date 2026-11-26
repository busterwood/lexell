# Measuring and speeding up Lexell code

How to time a program, find where it spends its time, compare two builds
honestly, and write code that is fast to begin with. The machine is shared and
its numbers drift, so most of this page is about what to trust. The idioms that
make code fast are in [idioms.md](idioms.md); the benchmark programs are
described in [bench/README.md](../../bench/README.md).

## Time and profile `-O` builds, natively

```sh
lexell/compiler/out/lxlc prog.lxl -O -o prog
```

`-O` adds loop optimisation (bounds and overflow checks proved away, array
headers hoisted), reuse of repeated loads, and borrow inference for `str`
parameters. Without it a program is not what you ship: lexdb's TPC-H q1 is
about 14% slower (design/lexdb-layers.md 6.3, Q1; design/lexdb-benchmarks.md).
Build natively. `--c` goes through gcc, takes far longer, and its code is not
the code that runs in production, so its profile misleads.

## Profile with perf

A native executable has a symbol table, so `perf` shows Lexell's functions.
Names carry the module prefix: `fib` in `hot.lxl` is `f1_hot_fib`.

```sh
lexell/compiler/out/lxlc hot.lxl -O -o hot
perf record -e cycles:u -g ./hot args...
perf report --stdio --no-children | head -40
```

Two switches of the compiler help when `perf` is not enough:

- `LXL_NATIVE_MAP=hot.map` also writes one line per function, runtime functions
  included: `address size name`, all in hex without `0x`
  (`403380 ac f1_hot_fib`). The executable loads at `0x400000`, so match the
  addresses of `perf script -F ip` against the map. `objdump -d hot` disassembles it
  with the function names, since the file has a symbol table.
- `LXL_NATIVE_IR=hot.ir` writes the IR the backend would compile, after the
  optimisation passes (`-O` adds the borrow, fold, loop and load-reuse passes),
  printed as C, and builds nothing. Read it to see which checks a loop keeps
  and what was hoisted. It stops before the map is written, so use the two in separate runs
  (design/native.md, section 4, describes both).

`LXL_RCSTAT=sites` counts the heap string copies a program makes at each site
that copies one; `tools/strsites.py` ranks the sites (its header gives the
three commands).
`lxlc --borrow-report prog.lxl` lists `str` parameters that should be `&str`.

## Compare builds by instructions

```sh
LXL_HASH_SEED=1 perf stat -e instructions:u ./prog_base
LXL_HASH_SEED=1 perf stat -e instructions:u ./prog_new
```

User-mode instruction counts repeat to within about 100 instructions when both
builds run with `LXL_HASH_SEED=1` (a fixed hash key; `Map` iteration order
never depends on it). Times spread by percents between runs of one binary.
Judge a change to what the code does (fewer checks, a better algorithm, fewer
copies) by instructions, and require cycles to agree in sign.
[HISTORY.md](../../../HISTORY.md), "Judging a pass", gives the rule for keeping
a compiler pass.

## A change of code shape moves no instruction

Alignment, padding and jump forms leave the instruction count alone and change
cycles, because functions and loops land on other cache lines. Rebuilding the
same source with other `LXL_PADB` (bytes before each function) and
`LXL_FALIGN` (function alignment, default 64) moved TPC-H q1 by 3.6% (4.7%
between single passes) and point selects by about 1.6% (design/lexdb-layers.md
6.2.7). A cycles difference below that is layout noise until shown otherwise.

```sh
python3 lexell/tools/perfsuite.py BASE NEW --placements 4 --cpu 2 -n 3
```

`BASE` and `NEW` are native-built compilers, given as paths (a git revision or
a source tree makes the script build its seed with gcc first). The script builds
every frozen benchmark program and tool with each compiler (`--native`, no `-O`: it
judges the compiler's default output), at 4 code
placements (`LXL_PADB` 0, 16, 32, 48), pins every run to CPU 2, interleaves the
runs, and prints per program the instructions (least of `-n`), the median
cycles over the placements, each side's spread over placements, and `apart`
when the two ranges of cycles do not overlap. Read it so:

- The load average is printed at the start and the end. Above 1 the cycles are
  unreliable: another job is running. An idle SMT sibling matters too: a core
  whose sibling is busy runs about 10% slower in cycles at equal instructions.
- A move not marked `apart` is layout noise. Only `apart` rows, with the
  instructions behind them, count as a change.
- `tools/placement.py LXLC OUT.json` is the older single-compiler test: each
  benchmark at eight placements, to see one program's spread. It also builds
  through C unless `ONLY=native` is set.

## The machine is shared: pin, lock, check the clock

- **Pinning.** The server under test goes on CPUs 0-3 and its clients on
  4-7,12-15. SMT siblings are N and N+8 (`cat
  /sys/devices/system/cpu/cpu0/topology/thread_siblings_list` prints `0,8`),
  so 8-11 stay idle. Use `taskset -c`.
- **The bench lock.** A timing holds `~/tpch/.bench.lock` exclusively; builds
  and test runs hold it shared, so neither disturbs the other:

  ```sh
  flock ~/tpch/.bench.lock taskset -c 4-7 ./prog     # a timing
  flock -s ~/tpch/.bench.lock python3 lexell/tests/run.py   # a build or test
  ```
- **CPU boost.** `bench/tpch/run.sh` turns boost off for a run and restores it
  on exit and on INT or TERM. A run that is killed harder, or a session that
  turned it off by hand, leaves `/sys/devices/system/cpu/cpufreq/boost` at 0,
  and every program runs about 20% slower (about 3.8 GHz against 4.97). Read
  the file before you publish a timing. If it is 0 and no run holds the lock,
  `sudo -n /usr/local/sbin/cpu-boost on` restores it. A TPC-H run in progress
  turns it off on purpose: leave that alone.
- **One benchmark at a time**, on a quiet machine (load under 1), and check the
  results (row counts, checksums) as well as the clock.
- **PostgreSQL in parallel is capped at the leader plus 3 workers**
  (`max_parallel_workers_per_gather = 3`, `max_parallel_workers = 3`), lexdb's
  shape of a main process and three replicas. Figures with all its CPUs are not
  comparable.

## lexdb: point selects never get slower

A single-row primary-key select is the path every client pays for. For any
change to planning, binding, sessions or the row path, count the server's user
instructions per statement before and after (`perf stat -e instructions:u` on
the server process, both builds with `LXL_HASH_SEED=1`, the same pgbench script
of `SELECT ... WHERE aid = :aid`, as `bench/sock/pgsel.sh` writes it), and fix
any real increase before the merge. Instructions per
statement agree within 0.15% across placements, which time over the wire does
not. Method and a worked case: design/lexdb-layers.md 6.2.7 and 6.2.9. New
executor code goes in its own module, not `lexdb_exec.lxl`.

## Where results are recorded

- Every comparison with another engine (PostgreSQL, SQL Server) goes in
  [design/lexdb-benchmarks.md](../../design/lexdb-benchmarks.md): section 1
  holds the current numbers and section 4 the record, one row per run, newest
  first, each linking the design note with the detail. Section 2 has the
  host and the rules; section 3 the commands.
- The lexdb tables of the published pages hold only the latest numbers, never
  history: [PERFORMANCE.md](../../../PERFORMANCE.md) for the language, and
  [lexell/docs/lexdb/performance.md](../lexdb/performance.md) and
  [LEXDB.md](../../../LEXDB.md) for lexdb. A comparison with an earlier build
  goes in the commit message and the design note, not there.

## Code that is fast to begin with

The patterns are in [idioms.md](idioms.md); the reasons here are speed.

- **`&str` for a parameter that only reads.** A `str` parameter takes ownership,
  so the caller clones. `-O` infers a borrow where a function only reads, but
  say so: `lxlc --borrow-report prog.lxl` lists the parameters (idiom 1).
- **No clone you do not keep.** `split`, `cut`, `lines` and `s[a..b]` return
  views; clone where a piece is stored (idiom 1). For the sites, `LXL_RCSTAT`.
- **Build once.** `out += piece` and `addInt` append in place; `a + b` in a loop
  allocates every time. `var xs: []T = withCapacity(n)` when the size is known
  (idiom 2).
- **`value record` for small plain data**, which is inline and copies without
  an allocation (idiom 5).
- **Consume, do not copy**: `for x in move(xs)` and a `match` that owns its
  fields (idiom 6).
- **`par.map` for CPU-bound work** over a slice, with a pure closure, mapping
  over chunks and merging on the caller (idiom 10, [concurrency.md](concurrency.md)).
- **Let the loop pass see the bound.** It hoists array headers and proves
  checks from the conditions and ranges it sees. `LXL_LOOPS=v` prints what it
  proved, and `LXL_NATIVE_IR` shows which checks a loop keeps.

## The benchmark programs and their drivers

| Driver | Measures |
|---|---|
| `python3 lexell/bench/bench.py [-n RUNS] [--only NAME ...] [--opt] [--perf]` | twenty programs in `lexell/bench/` (`fib loop array sieve alloc lists trees strings tokens maps nbody interp closures matmul pingpong bitpack btree hashagg varint_csv enum_eval`), native against C, Rust and Java; `--perf` adds instructions and cycles. It builds each program through C for its native/C column, so use `perfsuite.py` for your own A/B |
| `python3 lexell/bench/apps.py` | regex, JSON, jq, cmark and Decimal, native `-O`, pinned to one CPU |
| `python3 lexell/tools/optcost.py --compiler PATH` | the compile cost of `-O` against the default build |
| `python3 lexell/bench/compile.py -n 3` | compile time and executable size against rustc and gcc |
| `bench/tpch/run.sh LEXDB WORKDIR [SF] [RUNS]` | the derived TPC-H queries against lexdb and PostgreSQL |

The method for a performance experiment (read the code first, one experiment
at a time, measure the whole query, report spread and counters, keep scripts and
raw results) is in [design/perf-ideas.md](../../design/perf-ideas.md) section 5.
A saving under about 5% on a real target, or a 2x microbenchmark that moves no
application, does not earn its complexity there.
