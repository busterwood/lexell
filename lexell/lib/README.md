# Lexell library

The standard library, written as ordinary Lexell code over a few intrinsics.
`std.lxl` is the prelude: every program sees its `pub` names unqualified.
The other modules are imported by name, `import "strings"`, and used
qualified, `strings.join(...)`; this directory is the compiler's default import
root (`$LXL_LIB` replaces it), as are any `-L` roots. A bare import path names a
library module only: a program's own modules are imported with `./` or `../`
(`import "./money"`), relative to the importing file, so a local file never
shadows a library module.

    python3 lexell/lib/run_tests.py -j 8        # the library tests (LXL_CHECK=1)
    python3 lexell/lib/tests/gen_decimal_random.py   # regenerate decimal_random.lxl

Tests are in `tests/run` and `tests/error`, in the conformance suite's format
(`// expect:`, `// exit:`, `// stdin:`, `// error:`); the runner is the
conformance runner pointed at this directory, and every run test is checked
for leaks.

## Modules

| Module | Lines | Contents |
|---|---:|---|
| `std.lxl` | 537 | the prelude facade: Option, Result, Unit, Where; Eq/Ord/Hash/Show for the primitives; checked arithmetic and float methods; print/println/eprint/eprintln; min/max; prelude aliases/wrappers for Decimal, Map, StrBuf and sort |
| `hash.lxl` | 224 | SipHash-1-3 and the per-process hash key (AT_RANDOM); `sipHash13`, `sipStr`, `sipWords`, `hashSeed`; CRC32C with the CPU's crc32 instruction, `crc32c`, `crc32cMore` |
| `decimal.lxl` | 1,041 | Decimal, Rounding, DecError, exact arithmetic, parse/format, POW10, sumDecimals (the `m` literal's implementation) |
| `money.lxl` | 196 | Currency, USD/EUR/GBP/JPY/CHF, Money[C] |
| `math.lxl` | 306 | float constants, parse, fixed, toDecimal, near, IEEE bit patterns |
| `collections.lxl` | 1,080 | Map (insertion-ordered, SipHash by default, opt-in Fx), sort (unstable heap sort), sortBy/sortStable, searching, rearranging, copying, Set, UniqueList, Heap |
| `strings.lxl` | 1,025 | StrBuf; SIMD-backed search (indexOf/indexOfAny/count), split/splitByte/join, replace, trim, ASCII case (`toUpperAscii`/`toLowerAscii`/`equalFoldAscii`), int parse/format, padding, UTF-8, eza's natcmp/quoteName |
| `io.lxl` | 454 | IoError, whole-file read/write/append, readLines, readStdin, streaming Reader, buffered Writer, ChunkReader/copy/count/readAll |
| `fs.lxl` | 485 | stat/lstat, list, mkdirAll, remove/removeAll, rename, symlink, chmod, paths, walk, realpath, temp/atomic write |
| `os.lxl` | 263 | arguments, environment, pid, working directory, quit, ids, user database, tempDir |
| `time.lxl` | 908 | wall and monotonic clocks, sleep, UTC dates, ISO 8601, Tm/strftime/strptime, HTTP date |
| `fmt.lxl` | 115 | number padding and eza's permission string |
| `paths.lxl` | 135 | lexical Rust Path components: join, lastComponent, parentOf, ext |
| `cli.lxl` | 451 | the eza/obo option grammar: Spec, Command, parse, structured Error |
| `unicode.lxl` | 84 | Unicode 15.0.0 classification, simple lower/upper/fold, White_Space; no regex or Markdown data |
| `unicode_data.lxl` | 2,170 | generated (`gen_unicode_data.py`): Unicode 15.0.0 categories, simple lower/upper, simple fold and White_Space |
| `unicode_width.lxl` | 287 | generated from unicode-width 0.1.14: `displayWidth`, `runeWidth`, East Asian width ranges |
| `errors.lxl` | 73 | Rust-style debugPath and osError |
| `binary.lxl` | 286 | endian reads/writes over bytes, str, and StrBuf |
| `glob.lxl` | 408 | Unix path globbing: `*`, `?`, sets, ASCII POSIX classes, dotfiles, optional `**`, options, `escape`, and `expand` under a root |
| `base64.lxl` | 107 | standard base64, strict and jq-lenient decoders |
| `uuid.lxl` | 260 | RFC 9562 UUIDs: parse/format, v4/v5/v7, bytes, version/variant |
| `tz.lxl` | 421 | time zones from TZif files (version 2+, 64-bit transitions) and their POSIX footer rules, as glibc applies them: utc, local (TZ or /etc/localtime), fromSpec, load, at, localTime; tested against zoneinfo by `tests/gen_tz.py` |
| `sqldialect.lxl` | 260 | Value, DbError and its codes, SQL fragments with placeholders per dialect, exact decimal text and (p, s) checks |
| `ffi.lxl` | 129 | C memory for modules that call C: owned `Mem` (alloc, cstr, copyBytes), unchecked peek/poke/bytes |
| `sqlite.lxl` | 433 | SQLite 3 through libsqlite3: Db, Stmt |
| `pgwire.lxl` | 2,872 | PostgreSQL's wire protocol, native: connection strings and `.pgpass`, TLS, SCRAM and MD5 login, the Session (simple and extended queries, named statements, portals, cancel requests), raw rows and the text codecs |
| `postgres.lxl` | 560 | PostgreSQL on `pgwire`, no C library: Conn, Rows, Prepared (`prepare`, `queryPrepared`, `closePrepared`), Pool, Lease (on `pool`), Stream (portal batches) |
| `pool.lxl` | 188 | the connection pool the clients share (design/pool.md): Pooled (open, waitFailed, release, reuse), Pool, Lease, PoolStats; generic over the connection type |
| `sqlrows.lxl` | 423 | streamed results into the program's records: Columns (bind once, by name or position, types checked), RowView (typed accessors by index), Kind, Codec; shared by sqlserver, postgres and oracle |
| `codepage.lxl` | 66 | single-byte code pages 1252 and 28591 (ISO-8859-1): decode to UTF-8, encode, supported; tables generated by `gen_codepages.py` into `codepage_data.lxl` |
| `codepage_data.lxl` | 19 | generated by `gen_codepages.py`: the byte tables of `codepage` |
| `tds.lxl` | 3,914 | the TDS 7.4 protocol of SQL Server, from MS-TDS: packets, PRELOGIN with TLS inside, LOGIN7, SQLBatch, sp_executesql RPCs with table-valued parameters, RPCs to procedures by name, bulk load, transaction requests, a checked token decoder for every core type, sessions over net and tls |
| `sqlserver.lxl` | 1,262 | Microsoft SQL Server natively over `tds`, for tasks: connection strings, Conn, parameters, procedures by name, table-valued parameters, bulk copy, every result set, errors, transaction[T], buffered Rows, Stream, Pool/Lease on `pool` (stages T1, T2, T3 streams and pool) |
| `crypto.lxl` | 161 | digests (SHA-1, SHA-512, MD5), PBKDF2-HMAC-SHA512, AES-CBC and random bytes from libcrypto, for Oracle's password authentication |
| `tns.lxl` | 3,308 | Oracle's TNS and TTC protocol, ported from python-oracledb's thin mode: packets, connect (TLS renegotiation over tcps), fast auth and the classic login with the 12c and 11g verifiers, execute, fetch, binds, the value codecs (NUMBER, DATE, TIMESTAMP[ TZ], BINARY_FLOAT/DOUBLE, BOOLEAN), OUT and IN OUT binds, REF CURSORs and implicit results, the bind placeholder parser |
| `oracle.lxl` | 1,696 | Oracle Database natively over `tns`, for tasks: connection strings, Conn, Value and typed Param binds, buffered Rows, Stream, errors with ORA- codes, transaction[T], call with OUT binds and REF CURSORs, Pool/Lease on `pool` (stages O1 to O3, O5) |
| `task.lxl` | 702 | concurrent tasks on one thread: Scope, Future, Promise, Shared, Frozen, all/any, yield, cancellation, sleep, deadlines; signals; worker processes |
| `net.lxl` | 1,077 | TCP over IPv4 and IPv6 for tasks: listen (also with SO_REUSEPORT), accept, connect, read, write; name lookup and dial |
| `tls.lxl` | 1,113 | TLS 1.2 and 1.3 through OpenSSL 3: an engine over memory buffers, and connections over net sockets for tasks; client and server contexts, verification, pins, client certificates, ALPN (a client offers, a server selects) |
| `proc.lxl` | 614 | other programs: start with pipes, a Command's environment, directory and streams; wait on a pidfd as a task; output, communicate, run; cancellation sends SIGTERM then SIGKILL; PATH lookup in the child's environment; optional process group |
| `url.lxl` | 552 | URLs for http and https (RFC 3986): parse, resolve, percent-encoding, queries |
| `http.lxl` | 1,687 | an HTTP/1.1 client for http and https (pool, strict framing, redirects, retries, deadlines) and the head parsing the server shares |
| `httpserver.lxl` | 3,417 | an HTTPS and HTTP/1.1 server: TLS (S2), Go 1.22 routing, middleware, streaming bodies, forms and multipart, server-sent events, strict parsing, every limit and timeout, cancellation on hangup, request ids, access log, graceful drain |
| `sse.lxl` | 188 | a broadcast hub for server-sent events: Feed, Event, publish, a Cursor per subscriber, Last-Event-ID resume, wait with a keep-alive timeout |
| `redis.lxl` | 1,380 | Redis over RESP2 and RESP3 for tasks: Config and redis:// URLs, Conn, Value/Pair, Pool/Lease; strings, hashes, lists, sets, pub/sub, SCAN and transactions; TLS and Unix sockets |
| `markdown.lxl` | 2,626 | CommonMark 0.31.2: parse to a tree (arena of nodes, walker) and render HTML as cmark does; with `markdown_entities.lxl` (HTML5 entities) and `markdown_unicode.lxl` (punctuation, space, full case folding) |
| `markdown_entities.lxl` | 16 | generated by `gen_markdown_data.py`: the HTML5 named character references |
| `markdown_unicode.lxl` | 21 | generated by `gen_markdown_data.py`: Markdown's punctuation (P+S), space and full case-folding ranges |
| `regex.lxl` | 2,139 | regular expressions (RE2 syntax, linear time; a port of Go's regexp): compile, find, findAll, captures, replace, split, quote |
| `regex_dfa.lxl` | 1,423 | the regex engine's lazy DFA (after RE2's) and literal searches (after Rust's regex) |
| `regex_syntax.lxl` | 3,057 | the regex parser, simplifier and compiler to a program, forward and reversed (Go's regexp/syntax) |
| `regex_unicode.lxl` | 2,019 | generated (`gen_regex_unicode.py`): Unicode 15.0.0 categories, scripts and simple case folding |
| `json.lxl` | 1,944 | JSON values (shared, copy on write; objects in insertion order), parsing with positioned errors, a decoder for sequences, compact and indented writing with jq's options |

### std (prelude)

`std` is a facade over the modules below. The prelude names stay
unqualified, but the implementations of `Decimal` are in `decimal`, `Map`
and `sort` in `collections`, `StrBuf` in `strings`, and SipHash in `hash`.
The basic string helpers (`substr`, `indexOf`, `startsWith`, `endsWith`,
`contains`, `split`, `trim`, `repeat`, `isSpace`, `isDigit`, `parseInt`) are
in `strings` only and are imported explicitly; `split` there is
`splitByte` for the byte separator. Primitive methods (`int.checkedAdd`,
`float.sqrt`, `str.hash`, ...) stay in `std` because the compiler only allows
methods of the primitive types there.

- **Option[T]** `Some(T)`/`None`: `isSome`, `isNone`, `unwrap`, `expect(msg)`,
  `unwrapOr(d)`, `map(&f)`, `eq` (T: Eq), `toStr` (T: Show). **Result[T, E]**
  `Ok`/`Err` (the `try` lang item): `isOk`, `isErr`, `unwrap`, `expect`,
  `unwrapOr`, `unwrapErr`, `expectErr(msg)`, `map(&f)` (the Ok value),
  `mapErr(&f)` (the Err value: `try r.mapErr(toError)`), `ok()`, `err()`,
  `toStr`. **Unit**. Both take `borrow` type parameters (SPEC 6.1), so
  `Option[&str]` and `Result[Token, &str]` hold views; such a value follows
  the rules for values that hold borrows (SPEC 10).
- **Where** (a lang item, SPEC 15): a call site, the text `"file:line"` in
  the program's static data (`toStr`, `cstr()` for C). A call of a library
  function whose last parameter is a `Where` may leave it out: the compiler
  passes the call's location. `here(): Where` is the location of its own call
  (or the `Where` passed to it). `task` uses it to name the user's line when a
  task parks inside `with` or deadlocks.
- **Eq, Ord, Hash, Show** with implementations for `int i32 u32 u64 byte i128
  u128 float bool str` (float has no `hash`). `min`, `max` for `T: Ord + copy`.
- **Keyed hashing** (implementation in `hash`). A `Map` keyed by input (query parameters, header names,
  JSON keys, ids) must not let the sender pick keys that collide (hash
  flooding: n colliding keys cost n² probes). So `str`, `i128`, `u128` and
  `Decimal` (and so `Money`) hash with **SipHash-1-3** under a 128-bit key
  chosen at random per process, as Rust's std does; a seeded FNV or Murmur
  would not do, their collisions are found without the seed (Aumasson and
  Bernstein 2012). The key is derived (with SipHash) from the 16 random
  bytes the kernel gives every process (`AT_RANDOM`, no system call; glibc
  uses those bytes for its stack canary, hence derived, never used as is).
  The 64-bit integers keep a multiplicative hash, a bijection, and `Map`
  mixes a per-process seed into the slot of every hash, so integer keys land
  in slots no sender can predict either. Workers forked by `task.workers`
  share their supervisor's key; another run gets another key. `Map` keeps
  insertion order, so the key changes no program's output; a hash value is
  never meant to be printed or stored. `sipHash13(k0, k1, &s)` (prelude
  wrapper; `hash.sipHash13` is the implementation) is SipHash-1-3 of a
  string's bytes under a key you give (tests, or a hash you need to be the
  same across runs).
- **Checked arithmetic** on every integer type: `a.checkedAdd(b)`,
  `checkedSub`, `checkedMul`, `checkedDiv`, `checkedRem` return `None` exactly
  where the operator would stop the program (overflow, zero divisor,
  `MIN / -1`). Use them where the operands come from input; the operators stop
  on what would be a bug. Decimal has the same through `Result`: `addExact`,
  `subExact`, `mulExact`, `remExact`, and `div`.
- `print`, `println`, `eprint`, `eprintln` (one `Show` argument; stdout is
  buffered and flushed at exit and before stderr writes).
- **float**: `toStr` is the shortest text that reads back as the same value
  (`0.1`, `1e25`, `1.5e-7`, `5e-324`, `-0`, `inf`, `NaN`). Math methods, which
  are the runtime's own, not the C library's (see **math** below):
  `sqrt cbrt pow powi exp exp2 expm1 ln ln1p log2 log10 sin cos tan asin acos
  atan atan2 sinh cosh tanh floor ceil trunc round roundEven abs mod hypot
  copySign fma isNaN isInf isFinite`.
- **StrBuf** (in `strings`, re-exported by the prelude): `newStrBuf`, `add`
  (one copy of the string's bytes, `appendStr`), `addByte`, `addInt`,
  `addLine`, `size`, `clear`, `toStr`. The string helpers are in `strings`
  only: `substr`, `indexOf(s, sub, from)`, `startsWith`, `endsWith`,
  `contains`, `split(code point separator)` and `splitByte`, `trim`,
  `isSpace`, `isDigit`, `parseIntOpt(s): Option[int]` and `repeat`.
- **Decimal** (in `decimal`, re-exported by the prelude): a coefficient below 10^38, an exponent and a
  display scale; zero is unsigned. Literals `1.25m` are Decimals (the
  `fromFraction` lang item); also `decimalOf(n)`, `Decimal.fromUnits(units,
  scale)`, `Decimal.fromInt`, `Decimal.parse(s): Result[Decimal, DecError]`.
  Operators `+ - * %` and unary `-` are exact and stop the program with exit
  code 10 when the result is not representable; `addExact`/`mulExact` return
  a Result instead. `div(b, scale, mode)`, `quantize(scale, mode)`,
  `toInt(mode)` return Results, and so do `round(scale)` (HALF_EVEN),
  `roundAway`, `floor`, `ceil`, `trunc` and `withScale(s)`. `cmp`/`eq`/`hash`
  compare values (`1.0m == 1.00m`, equal hashes). `toStr` keeps the display
  scale (`0.50`), `format()` is the same as a Result (an error when the scale
  would drop digits), `canonical()` has no trailing zeros; `scale`, `exponent`,
  `coefficient`, `sign`, `isZero`, `isNeg`, `abs`, `neg`, `toFloat`,
  `sumDecimals`. For storage, `toBin()` writes the fields as 2 to 22 bytes
  (a flag byte, the display scale, the exponent if not 0, the coefficient's
  bytes little-endian), and `Decimal.fromBin(s, at, n): Result[Decimal,
  DecError]` reads them back with the same display scale; bytes `toBin`
  never writes are DecError.Invalid. **Rounding** (written qualified, `Rounding.HALF_EVEN`):
  `HALF_EVEN HALF_AWAY HALF_TOWARD_ZERO TOWARD_ZERO AWAY FLOOR CEILING
  UNNECESSARY`. A fractional literal is `fromFraction(units: i128, scale:
  int)` (`1.5e3` is units 15, scale -2); a scale over 38 stops with
  DecError.Range. The stop helpers (`orStop`, money's `stop`) return `never`. **DecError** codes:
  DecError.Overflow 1, DecError.Inexact 3, DecError.Invalid 4, DecError.DivZero 5, DecError.Range 6,
  DecError.Precision 7, DecError.Exponent 8, DecError.Display 9.
- **sort(xs: mut &[]T)** for `T: Ord`: heap sort, in place, not stable. The
  implementation is `collections.sort`; the prelude keeps a wrapper.
- **Map[K: Eq + Hash, V]** (in `collections`, re-exported by the prelude): insertion-ordered entries plus an open-addressing
  index. `newMap`, `size`, `has(&k)`, `get(&k): Option[V]` and `getOr(&k, d)`
  (V: copy), `at(k): &V`, `atMut(k): mut &V`, `atOrPut(k, d): mut &V`,
  `put(k, v)`, `remove(&k): Option[V]`, `removeStable(&k): Option[V]`,
  `clear`, `keyAt(i)`, `valAt(i)`,
  `valAtMut(i)` for walking, `each(fn(k, v) {...})` and `eachMut(fn(k, v)
  {...})` (v is `mut &V`) in insertion order, `keys()`/`values()` (copy
  types). `remove` is O(1) and moves the last entry into the hole, so it
  changes the iteration order; `removeStable` shifts the tail down and keeps
  it, at O(size). `newMapWith[K, V](hashFn)` takes a supplied `fn(&K): u64`
  instead of `K.hash()`; `fxHashStr` and `fxHashInt` are the rustc-hash Fx
  scheme. They are fast but **not** collision-resistant: use them only for
  trusted input, and keep the default `newMap` for network-controlled keys.
  Slots come from
  `(hash ^ seed) * GOLDEN` (the seed per process, above); the index is an
  array of u32 slots, each an entry number with some bits of that mixed hash
  beside it, so a probe passes other keys' slots without loading them. A Map
  (and so a Set) holds at most 2^31 entries: the `put` (or `atOrPut`) that
  would add one more stops the program with `Lexell: panic: Map: more than 2^31
  entries` (exit code 12). Experimental:
  `for e in m.iter()` walks the entries in insertion order as
  `MapEntry{key: &K, value: &V}` (`MapIter` holds a borrow of the map, which
  is frozen for the loop; design/borrow-types.md).
- Powers of ten for Decimal come from `decimal.POW10`, a constant table (read-only
  static data) instead of a 39-arm match.

### money

`Money[C: Currency]` is a value record over a Decimal; the currency is a
type, so `usd + eur` does not compile. `money.of[C](d)` is exact (stops with
exit 10 when `d` has more decimals than the currency), `money.round[C](d,
mode)`, `fromMinor(units)`, `zero()`, `parse[C](s): Result`. Methods:
`amount`, `code`, `toMinor(): Result`, `isZero`, `isNeg`, `abs`, `+ - neg`,
`times(rate)` (HALF_EVEN), `timesWith(rate, mode)`, `timesInt(n)`, `cmp`, `eq`,
`hash`, `toStr` (`"12.50 USD"`), `allocate(n)` and `allocateBy(&weights)`
(largest remainder; the parts always add up to the amount), `money.sum(&xs)`.

### math

`PI TAU E SQRT2 LN2 LN10`, `inf()`, `nan()`, `parse(s): Option[float]`
(decimal, hex `0x1p3`, `inf`, `nan`; no spaces), `fixed(x, places)` (rounds
the shortest decimal form half to even: `fixed(2.675f, 2)` is `"2.68"`),
`toDecimal(x): Option[Decimal]` (exact, from the shortest form), `near(a, b,
tol)`.

The float methods need no libm and no libc: a native program that uses them is
a static ELF, and a C-backend program links no `-lm`.

- **Single instructions** (bit for bit what C's libm returns, on both
  backends): `sqrt` (sqrtsd: a negative gives NaN), `floor ceil trunc
  roundEven` (roundsd; `roundEven` is rint, halves to even; -0 and the sign of
  a zero result are kept: `ceil(-0.5)` is -0; infinities and NaN come back
  unchanged, a signaling NaN quiet), `round` (halves away from zero:
  trunc(x + copysign(0.49999999999999994, x)); `round(-0.3)` is -0),
  `abs` (clears the sign bit, so `abs(-0)` is 0 and a NaN keeps its payload),
  `copySign` (the magnitude of x with the sign bit of y, also for NaN and
  zeros), and `x.fma(y, z)` (x * y + z with one rounding: vfmadd213sd, FMA3;
  NaN and infinity as in IEEE 754).
- **The rest** is musl 1.2.5's `src/math` (MIT; NOTICE) in
  `compiler/lxlmath.inc`, one C text that both the C backend and the native
  runtime compile, so both give the same bits: `exp exp2 log log2 pow` are
  Arm's optimized-routines (about 0.51 ULP; they use `fma`), `sin cos tan asin
  acos atan atan2 sinh cosh tanh expm1 log1p log10 cbrt hypot` are FreeBSD
  msun (the table below) and `mod` (fmod) is exact. Results can differ
  from glibc's in the last bit for the msun ones (sin, cos, tan, asin, acos, atan, atan2, tanh, cbrt,
  hypot, sinh), for 1 to 55 of 100 inputs; exp, exp2, log, log2, log1p and pow
  agree with glibc on 99.9% or more. Special values (NaN, infinities, zeros,
  signs, pow's edge cases) are the C99 ones. `lexell/tools/mathulp.c` measures
  the error against libquadmath (1M random inputs per function; glibc 2.39 in
  brackets): exp 0.51 (0.51), exp2 0.51 (0.51), log 0.50 (0.50), log2 0.50
  (0.50), pow 0.51 (0.51), log10 0.57 (1.48), log1p 0.51 (0.51), expm1 0.76
  (0.76), cbrt 0.67 (3.10), sin 0.78 (0.52), cos 0.76 (0.52), tan 0.85
  (0.57), asin 0.84 (0.51), acos 0.88 (0.52), atan 0.83 (0.51), atan2 1.45
  (0.52), hypot 0.92 (0.53), sinh 1.51 (1.54), cosh 0.99 (1.49), tanh 2.02
  (2.02). sin, cos and tan are good to 1e22 (musl's argument reduction).
  Specials: 0 of 6,650 differ from glibc in kind (NaN, inf, zero, sign).
- Programs need an x86-64-v3 CPU (AVX2, BMI1, BMI2, FMA3, F16C, LZCNT, MOVBE;
  Intel Haswell, 2013, AMD Excavator, 2015, or later); the runtime checks this
  once at startup (CPUID, XGETBV) and exits with code 16 and one line on
  stderr when a feature is missing.

### collections

`sortBy(xs, cmp: &fn(&T, &T): int)` and `sortStable(xs)` (sortBy with
`cmp`): a stable merge sort over an index array followed by an in-place
permutation, so owned elements work. Every predicate and callback is a
closure type (`&fn`), so it may use the caller's locals:
`count(&xs, fn(x) { return x > lo })`; a named function also works. `isSorted`, `binarySearch(xs, &x): Result[int, int]` (Ok index or Err
insertion point), `lowerBound`, `upperBound`, `find`, `findBy`, `contains`,
`count(xs, pred)`, `any(xs, pred)`, `all(xs, pred)`, `equal`, `reverse`, `rotateLeft`, `insert(xs, i, x)`,
`removeAt(xs, i): T`, `swapRemove`, `retain(xs, pred)`, `dedup`,
`copyRange(xs, a, b)`, `copyOf`, `extend`, `filter`, `mapTo`.
**Set[T: Eq + Hash]** (a Map to Unit): `newSet`, `setOf(&xs)`, `size`,
`isEmpty`, `has`, `add(x): bool`, `remove(&x): bool` (O(1), order changes),
`removeStable(&x): bool` (O(size), order kept), `clear`, `at(i)`,
`each(f)`, `filter(pred): Set[T]`, `items()`, `sorted()`, `union`,
`intersect`, `minus`, `isSubset`, `eq`.
**UniqueList[T: Eq + Hash]** is a list of unique elements in insertion order, a port of
busterwood/Goodies' UniqueList (C#, inspired by Python 3.6's dict): an open-addressing index
over dense arrays of hashes and values, with DELETED marks and a quarter of its slots spare.
`newUniqueList`, `uniqueListOf(&xs)`, `size`, `isEmpty`, `has(&x)`, `indexOf(&x): Option[int]`,
`at(i): &T` (out of range stops the program, as an array index does), `add(x): bool` (false when
x is present), `addOrUpdate(x)`, `replace(i, x): bool` (false, and no change, when x is already
at another index), `remove(&x): bool`, `removeAt(i): T` (both shift the later elements down, O(n)),
`clear`, `copy()`, `each(f)`, `items()`, `filter(pred)`, `union`, `intersect`, `minus`,
`symmetricMinus`, `isSubset`, `isSuperset`, `overlaps`, `eq` (set equality, order ignored).
Slots come from the hash mixed with a per-process seed, as Map's do.
**Heap[T: Ord]** (min-heap): `newHeap`, `push`, `pop(): Option[T]`, `peek`,
`size`, `isEmpty`.

### fmt

`digits(n)` (decimal width, `digits(0) == 1`), `appendPadded(mut buf, n,
width)`, `writePadded(w, n, width)` (through an `io.Writer`, no `Result`: the
Writer keeps the first write error for `flush`/`close`), and
`modeString(mode)` (eza's ten-character permission form: type, rwx triples,
`s/S` and `t/T`; no xattr `@`). `strings.padLeft` remains the string
primitive.

### paths

Lexical path primitives over bytes, Rust `Path::components` semantics:
`isAbsolute`, `hasTrailingSlash`, `isDotName`, `lastComponent`, `parentOf`,
`join`, and `ext` (the extension without its dot, unlike `fs.extension`,
which keeps the dot). No filesystem, `~`, glob, shell or symlink resolution:
`fs.realpath` is the filesystem operation. `lastComponent`, `parentOf` and
`ext` scan backwards and allocate nothing, which matters for a caller that
formats a name per entry (eza).

### cli

The eza/obo option grammar. `Spec {short, long, arity, consume, accept,
choices, default}` (`Arity` = `Flag`, `Value`, `Optional`), `Command {opts,
operands}`, `Opt {short, long, value, hasValue}`, and
`parse(args, from, specs): Result[Command, Error]`. It handles `--`,
`--name=value`, short clusters, attached values, optional defaults and the
`consume`/`accept` sets; values are validated after the whole token walk.
`Error` is structured (`ErrorKind`, token, option, short, value, choices);
the module never prints or exits, so each caller keeps its exact messages and
exit codes.

### unicode

Unicode 15.0.0 classification and simple case mapping over
`unicode_data.lxl`: `lower`, `upper`, `fold`, `isLetter`, `isDigit`,
`isSpace`, `isUpper`, `isLower`, `isPunct`, `category`. `isSpace` is the
Unicode `White_Space` property; `isPunct` is general category P (symbols are
not punctuation). `unicode` no longer imports `regex_unicode` or the Markdown
tables. Scripts and category aliases stay in `regex_unicode`; full case
folding for link labels is in `markdown_unicode` (a Markdown-only table).
`strings` case mapping stays
ASCII and is named `toUpperAscii`/`toLowerAscii`/`equalFoldAscii`; callers that
need Unicode use `unicode.upper`/`lower`/`fold`. Terminal width is
`unicode_width.displayWidth`/`runeWidth`, so text search and case mapping do
not pay for the width table.

### errors

`debugPath(p)` (Rust `Path`/`OsStr` Debug quoting: quotes, `\" \' \\ \0 \t
\r \n`, `\u{h}` for other controls and DEL, bytes >= 0x80 copied) and
`osError(errno)` (`io.errorText(errno)` plus `" (os error N)"`). There is one
errno table (`io.errorText`); `errors.text` is a thin alias.

### binary and math bits

`binary`: `readU16/32/64LE/BE`, signed `readI16/32/64LE/BE`, the `...Str`
variants over `&str`, `appendU16/32/64LE/BE`, in-place `setU16/32LE/BE`, and
`addU16/32/64LE/BE` into a `StrBuf`. Reads use the language's checked index
and trap if `at` is out of range; callers validate wire lengths. `math.bitsOf`
/`fromBits` give the exact IEEE 754 double bit pattern as a 64-bit signed int
(the sign bit makes it negative); `bitsOf32`/`fromBits32` and their `Int`
forms do the same for single precision.

### glob

Unix path globbing, with bash's defaults: `compile`, `compileWith`, `matchPath`,
`matchPathWith`, `Pattern.matches`, `escape` and `expand`. `*`, `?` and sets
stop at `/`; `*` and `?` do not match a leading `.` unless the pattern starts
with a literal `.` or `Options.dot` is set; `**` is a plain `*` unless
`Options.globstar` is set; `Options.caseFold` folds ASCII only; POSIX classes
(`[[:alpha:]]`, `[[:digit:]]`, ...) are ASCII/C-locale. Sets support
`[abc]`, `[a-z]`, `[!abc]` and `[^abc]`; `\` escapes. `expand(root, pattern,
options)` walks `root` without following symlinks, matches relative paths and
returns them sorted; a bad pattern and an I/O error are `ExpandError.Pattern`
and `ExpandError.Io`. Brace and tilde expansion are shell features and are not
here. Matching is by Unicode code point, so `?` matches one character. grep
keeps its byte-wise GNU matcher. zoxide's Rust-crate-compatible matcher is
`cmd/zoxide_glob.lxl`, not a library module.

### base64
### uuid

RFC 9562 identifiers as a two-int value record (`hi`, `lo`), so a Uuid is a
copy type: a Map key, a sort value, and compared with `eq`/`cmp`/`hash`.
`parse` accepts the canonical 36-character form or bare 32 hex digits, either
case; `toStr` writes lowercase canonical. `fromBytes`/`bytes` convert exactly
16 bytes. `nil`, `max`, `isNil`, `version` and `variant` (0 NCS, 2 RFC,
6 Microsoft, 7 future) are plain code. `v4` (random), `v5` (SHA-1 name-based)
and `v7` (48-bit Unix milliseconds + random, RFC 9562 layout) use `crypto`,
so a program that generates them links libcrypto; `v4From`/`v7At` take fixed
bytes for tests.


`encode(s)` (standard alphabet, padded), `decodeStrict(s): Option[str]` (the
crypto/pgwire rules: whole groups of four, padding required) and
`decodeLenient(s): Result[str, str]` (jq's `@base64d`: `=` ends the data,
unpadded input accepted, a single trailing byte is an error). `crypto.base64`
and `crypto.unbase64` delegate.

### strings

Searching walks the runtime's SIMD builtins: `indexOf`/`trim`/`count`/`split`
and `splitByte` use `strFind` (memmem) and `strFindAny` (memchr2/3) for long haystacks, with
a scalar path for short strings where a call does not pay. On a 50 MB file
that is 27x to 32x fewer instructions for absent-byte and absent-substring
scans, 9.5x for `count`, and 9.3x for a byte `split`. A negative `from`
clamps to 0 (it used to trap).

`substr`, `indexOf(s, sub, from)`, `startsWith`, `endsWith`, `contains`,
`trim`, `repeat`, `isSpace`, `isDigit`, `parseIntOpt` returning `Option`,
`StrBuf` (`newStrBuf`, `add`, `addByte`, `addInt`, `addLine`, `size`, `clear`,
`toStr`), `lastIndexOf`, `lastIndexOfByte`, `indexOfByte`, `indexOfAny(s, byteSet, from)`,
`count`, `equalFoldAscii`, `split(&s, sep):
[]&str`, `splitN(&s, sep, n)` (n < 0: all), `fields(&s): []&str`, `cut(&s,
sep): Option[Cut]` (`before` and `after` are views), `owned(&pieces): []str`,
`lines(&text)` and `fieldsIter(&text)`, `join(&parts, sep)` (parts:
`&[&str]`, views or, read as views, owned strings),
`splitByte(s, sep: byte): []str`, `replaceAll`, `replaceN`, `trimLeft`, `trimRight`, `trimPrefix`, `trimSuffix`,
`toUpperAscii`, `toLowerAscii` (ASCII), `isLetter`, `isAlnum`; `parseInt(s)` and
`parseIntBase(s, base)` return `Result[int, ParseError]` (`Empty`,
`Invalid(at)`, `OutOfRange`); `formatInt(n, base)`, `hex`, `hex64`, `zeroPad`,
`groupDigits(n, sep)`, `padLeft`, `padRight`, `center`. UTF-8: `decodeAt(s,
i): Decoded {rune, size, ok}` (strict; an invalid part gives U+FFFD and takes
its maximal subpart, as Rust's `from_utf8_lossy`), `runes`, `runeCount`,
`isValidUtf8`, `lossy(s)` (invalid parts replaced by U+FFFD), `addRune(mut
&buf, r)`, `fromRune`, `fromRunes`. Terminal columns are
`unicode_width.displayWidth(s)` and `unicode_width.runeWidth(r)` (per
unicode-width 0.1.14: wide East Asian and emoji 2, combining marks, format
and control characters 0).
eza's name order is here too: `natcmp`/`natcmpFold` (natord-plus-plus
2.0.0: whitespace skipped, digit runs compared naturally, the documented
partial Unicode lowercase table for the fold) and their aliases
`naturalCompare`/`naturalCompareFold`. The comparison runs in one pass: an
ASCII byte is compared directly, and the first byte >= 0x80 hands the whole
comparison to the code-point loop, so a pure ASCII name is never scanned
twice. `quoteName(name, quoteSpaces)` and
`parentPrefix(parent, quoteSpaces)` are eza's QuoteSpaces escaping;
`isPrint`, `isBlank`, `isWordByte` are the byte predicates; `utf8Error(s):
Option[str]` gives Rust's first-invalid-UTF-8 message and index (valid data is
`None`).
Splitting gives views (design/borrow-types.md): the pieces are `&str` views
of the text, not copies and not counted, and the text is frozen while they
live (SPEC 10, until their last use); a piece converts to `str` where one is
expected, and `owned(&pieces)` keeps a whole array past its text. `join`
takes the pieces as they are, and an array of owned strings too (`&names` is
read as `&[]&str`, SPEC 4.1). `lines` and `fieldsIter` are iterators
for `for x in ...` (a line has no `"\n"`; a final line without one is a line;
`""` has none). Separators are `&str`, so a literal is passed as it is
(`strings.split(&line, ",")`). std's `split(s, sep: byte): []str` (the
prelude's split at a byte) is a different function and gives owned pieces.

### io, fs, os, time

- **io**: `IoError {errno, op, path}` with `toStr` (`"open x: No such file or
  directory"`), `isCancelled()` and `isTimeout()` (`ECANCELED`, `ETIMEDOUT`:
  a `net` call cut short by `task`), `errorText(errno)`, `read(path): Result[str, IoError]`,
  `readLines`, `readStdin`, `splitLines`, `write(path, data)`,
  `appendTo(path, data)`. `Writer` (`stdout()`, `stderr()`, `create(path)`,
  `openAppend(path)`): `write`, `writeln`, `writeByte`, `flush(): Result`,
  `close(): Result`; flushed and closed when dropped (errors then are lost); the
first error of an implicit flush (buffer over 64 KiB) is kept for the next
`flush` or `close`, and a stdout writer's `flush` also flushes the runtime's
buffer behind `print`. `flushStdout(): Result` does that and reports the first
failed write to stdout since the last call (so a program can see `ENOSPC` on a
full disk). `Reader` (`stdin()`, `open(path): Result`): `read(dst: mut
&[byte]): Result[int, IoError]` fills the front of `dst` (0 at the end),
`readLine(): Result[Option[str], IoError]` (no `"\n"`, no `"\r"` before it,
as `splitLines`), `seek(offset, whence: Whence): Result[int, IoError]` (`Whence`:
`Start Current End`; the new offset; `ESPIPE` for a pipe), `close(): Result`; the end is not sticky (a later read tries
again: a growing file, a terminal), `EINTR` is retried, a file reader is
closed when dropped. `isTerminal(fd)`, `terminalWidth(fd): Option[int]`.
`createExclusive(path)` opens with `O_CREAT|O_EXCL`. `ChunkReader`
(`newChunkReader`, `newChunkReaderSize(src, size)`) owns one buffer and
exposes `fill(): int` plus `buf[0..n]`/`pos`; `copy(dst, src)`, `count(src)` and
`readAll(src)` are the streaming helpers (one chunk-sized conversion per
chunk).
- **fs**: `stat`/`lstat(path): Result[Stat, IoError]` (`size mode mtime
  mtimeNs nlink uid gid ino dev blocks`, `kind() isDir() isFile() isLink()
  perm()`), `Kind` (`File Dir Link Fifo Socket CharDev BlockDev Other`,
  `kindOfMode(mode)`), `exists`, `isDir`, `isFile`, `list(path):
  Result[[]Entry]` (`name`, `kind` from readdir, or lstat when readdir does
  not say), `listNames` (sorted), `mkdir`, `mkdirAll`, `remove`, `removeAll`
  (does not follow links), `rename`, `symlink`, `readlink`, `chmod`; paths: `join`, `baseName`, `dirName`, `extension`.
  `walk(root, followLinks, visit)` visits the root then descendants, skips a
  subtree when the callback returns false, tracks `dev:ino` to prevent symlink
  cycles, and returns the first list/stat error. `createTemp(dir, prefix)`
  returns an `io.Writer` with mode 0600; `writeAtomic(path, data)` writes a
  temp in the same directory and renames it over `path`; `realpath(path)`
  resolves links with the 40-link `ELOOP` limit. Positioned I/O on a
  descriptor: `pread`/`pwrite(fd, buf: ptr, n, off)` (`preadDirect` for an
  `O_DIRECT` descriptor: through the ring it goes to the kernel's workers at once,
  where `pread` tries inline first, for the page cache), `fdatasync(fd)`,
  `fsync(fd)`, `fallocate(fd, off, n)` return a count or 0, or -errno, and
  park the task until done: through io_uring with the native backend
  (unless `LXL_URING=0`), else as blocking calls on the helper pool. `Stat` keeps its existing
  fields (no atime/ctime: the compiler imports `fs`, so changing the record
  forces a seed reseed, and no caller needs them yet).
- **os**: `argv()`, `arguments()`, `env(name): Option[str]`, `envOr`,
  `setEnv`, `unsetEnv`, `pid`, `cwd`, `setCwd`, `quit(code)`.
  `environ(): []Env {name, value}` reads `/proc/self/environ` and replays
  `setEnv`/`unsetEnv` changes; `uid`/`gid`/`effectiveUid`/`effectiveGid`;
  `users()`, `userById`, `userByName` (`User {uid, gid, name, home, shell}`)
  through getpw*; `tempDir()` ($TMPDIR when absolute, else /tmp). The getpw*
  and getuid calls (including `userName`/`homeDir`) are libc symbols: calling
  them makes a native binary dynamically linked and adds loader work at
  startup. A program that must stay static reads `/proc/self/status` and
  `/etc/passwd` itself, as `zoxide` and `eza` do.
- **time**: `Time {sec, nsec}` (`now`, `fromNanos`, `cmp`, `eq`, `toStr`,
  `addMillis`, `millisUntil`), `unixSeconds`, `unixMillis`, `monotonicNs`,
  `sleepMs` (blocks the thread, every task with it: in tasks use
  `task.sleep`); `Date {year, month, day}`: `dateOf(sec)`, `dateOfDays`,
  `daysOfDate`, `weekday`, `isLeapYear`, `daysInMonth`, `valid`,
  `parseDate`, `isoDate`, `isoDateTime`.
  Civil date-times, the values of SQL `time`, `datetime2` and
  `datetimeoffset` and Postgres `time`, `timestamp` and `timestamptz` (no
  zone rules, no leap seconds):
  - `TimeOfDay {nanos}`, nanoseconds since midnight: `timeOfDay(h, m, s,
    ns): Option`, `hour`, `minute`, `second`, `nano`, `eq`, `cmp`,
    `toStr` ("13:45:07.25"), `parseTimeOfDay` ("HH:MM[:SS[.f]]", 1 to 9
    digits), `MIDNIGHT`.
  - `LocalDateTime {date, time}`, no zone: `localDateTime(d, t)`, `eq`,
    `cmp`, `toStr` ("2026-11-05T13:45:07.25"), `parseLocalDateTime` ('T',
    't' or a space between), `atUtc(): Time`, `withOffset(minutes):
    Option[OffsetDateTime]`, `localOf(t: Time)` (UTC).
  - `OffsetDateTime {local, offset}`, the offset in minutes east of UTC
    within ±23:59 (`MAX_OFFSET`): `instant(): Time`, `Time.atOffset(minutes):
    Option[OffsetDateTime]`, `eq` (same local date-time and offset),
    `sameInstant`, `cmp` (by instant, then offset), `toStr`
    ("...+01:00"; 0 is "+00:00"), `parseOffsetDateTime` ("Z", "+HH:MM",
    "+HHMM" or "+HH").
  - `Tm` is the C `struct tm` view (`year` since 1900, `mon` 0..11, `wday`,
    `yday`, `fsec`): `gmtimeOf(sec)`, `timegm(t)`, `tmOf(local)`,
    `localDateTimeOf(tm)`, `strftime(t, fmt, zoneName)`, `strftimeLocal`,
    `strptimePrefix(s, fmt): Result[Strptime {tm, rest}]`, `strptime(s, fmt):
    Result[Tm]`, `strptimeLocal(s, fmt): Result[LocalDateTime]`, and
    `httpDate(sec)` (RFC 7231 IMF-fixdate, GMT). `zoneName` is the `%Z` label;
    `%z` is `+0000`. Unknown format tokens pass through.

### ffi

C memory for modules that declare externs (SPEC 12), used by sqlite,
postgres and the ODBC oracle (its bound parameters). `Mem` is owned memory C may
use, freed when dropped: `alloc(n)` (zeroed, never a null pointer),
`cstr(s)` (the bytes and a NUL), `copyBytes(s)`; `ptr()`, `size()`, index-checked `get`/`set` (bytes),
`getI32`/`setI32`, `getPtr`/`setPtr`, `toStr()`. For memory C owns, at a
pointer C returned: `peek`/`poke`, `peekI32`/`pokeI32`,
`peekPtr`/`pokePtr` (element `i`) and `bytes(p, n)` (a copy); these are as
unchecked as an extern call, so wrap them like one. A null pointer is the
built-in `nullPtr()`; arrays and slices of integers, `float` and `ptr` can
be passed to C directly (`&[]T`, `mut &[]T` extern parameters), as postgres
does for `PQexecParams`'s types and values.

### task

Concurrent tasks on one thread (SPEC 16; design/concurrency.md, stages
C1a and C1b): stackful coroutines, scheduled cooperatively, with one epoll
loop for the sockets of `net` and the timers; signals as events of that
loop and worker processes for several cores (stage C2), at the end.

Every function below that can park (`scope`, `scoped`, `wait`, `all`, `any`,
`yield`, `sleep`) and `with` has a last parameter `w: Where`, the caller's location,
which a call leaves out (SPEC 15): it is not shown in the signatures here. A
call through a function value passes it (`here()`), and so does a function
of the program that wants its own caller's line reported (`fn waitAt(f:
task.Future[int], w: Where)` calls `f.wait(w)`).

- `scope(f: &fn(mut &Scope))` runs `f` with a new scope and returns when
  every task started on it has finished; `scoped[R](f: &fn(mut &Scope): R):
  R` is the same for an `f` with a result.
- `s.start[A, T](f: fn(A): T, arg: A): Future[T]` (on `s: mut &Scope`)
  starts `f(arg)`. `f` is a plain function value and `arg` is moved in.
  `s.spawn[A, T](f, arg)` starts it with no future: nobody waits for it, its
  result is dropped, and it is not cancelled until the scope's task is (an
  accept loop's connections; dropping the futures of `start` would cancel
  them). The scope waits for it either way.
- `Future[T]` (owned): `wait(): Result[T, Cancelled]` consumes it and parks
  until the task has finished. Dropped without waiting, it cancels its task.
  `waitFor(ms)` is `wait` with a deadline `ms` milliseconds from now; the
  earlier deadline of an enclosing `within` still wins.
- `all[T](fs: []Future[T]): Result[[]T, Cancelled]` waits for each in
  order; on an error the rest are dropped (cancelled).
  `any[T](fs: []Future[T]): Result[T, Cancelled]` gives the first result,
  cancels the others and waits until they have finished (`fs` must not be
  empty).
- `promise[T](): Handoff[T]`: `Handoff { promise: Promise[T]; future:
  Future[T] }`, the two ends of one hand-over (`let task.Handoff{promise: p,
  future: f} = task.promise[int]()`). `p.complete(v: T)` consumes the promise and never
  parks; a promise dropped without it makes `wait` give
  `Err(Cancelled.Abandoned)`.
- `yield(): Result[Unit, Cancelled]` lets the other runnable tasks run;
  `cancelled(): bool` tells whether the running task has been cancelled.
- `sleep(ms: int): Result[Unit, Cancelled]` parks for `ms` milliseconds
  (none when `ms <= 0`); `Err(Cancelled)` when the task is cancelled (at
  once, or while it sleeps), `Err(Timeout)` when the deadline of an
  enclosing `within` comes first.
- `within[R](ms: int, f: &fn(): R): R` runs `f` with a deadline `ms`
  milliseconds from now; the earlier one wins when nested, and tasks started
  during `f` inherit it. Every call that can park in them returns
  `Err(Timeout)` (`ETIMEDOUT` from `net`) once it has passed, so `f` ends
  through its `Result`s: `task.within(500, fn(): Result[int, io.IoError] {
  return c.read(mut &buf) })` is a read with a timeout, and a deadline
  around several calls bounds them together. `f` returns a value (a closure
  with no result cannot give `R`); `within` itself never parks.
- `Cancelled` is `value closed { Cancelled; Abandoned; Timeout }` (`eq`,
  `toStr`).
- `shared[T](v: T): Shared[T]`: a counted copy handle (a lang item, SPEC 15);
  `sh.with(f: &fn(mut &T))` is the only access. Parking inside `with`, or a
  `with` on a value whose `with` is open, is exit 13. If every task is
  parked the program stops with exit 14 (deadlock). The messages name the
  user's lines (SPEC 14): `Lexell: a task parked inside Shared.with (the with
  at a.lxl:37) at a.lxl:41`, `Lexell: Shared.with on a value whose with is
  already open (the with at a.lxl:30) at a.lxl:35`, `Lexell: deadlock: every
  task is parked at a.lxl:41`.
- `freeze[T](v: T): Frozen[T]`: a counted copy handle, like `Shared`, to a
  value that never changes again. `fr.read(f: &fn(&T): R): R` lends it as
  `&T`, and `f` **may park**: no writer exists, and the handle that `read`
  borrows keeps a count, so the value cannot go away meanwhile (the reason
  set-once globals are sound). Any number of tasks may be inside `read` at
  once. `fr.get(): T` copies a copy value. The value is dropped with the last
  handle. For what every connection's task reads and none writes: a router,
  configuration, templates. A forked worker gets its own copy with its own
  count. It is a closure, not `get(): &T`, because a result may only borrow
  a place rooted at the receiver (SPEC 10 rule 5) and the value lives in the
  runtime's box.

The scheduler waits in `epoll_wait` only when no task is runnable, and checks
sockets and timers every 64 switches otherwise. A task parked in `sleep`, on
a socket or in a blocking C call is never a deadlock; a program whose tasks
all wait on futures nobody will complete still is (exit 14).

**Blocking C calls** (SPEC 12, stage C1c). A module marks an extern that may
take long `blocking`; while another task could run, a call parks its task
and runs on a helper thread. The pool starts with the first such call:
`LXL_HELPERS` threads (default 4, at most 64; `LXL_HELPERS=0` runs every
call on the program's thread, as when nothing else could run). A round trip
through the pool costs about 0.4 us (C backend) to 0.8 us (native) while the
helpers and the event loop spin for each other (50 us each, not when the
process may use only one CPU: then about 6 us). The library's blocking
calls: sqlite's `sqlite3_step` and `sqlite3_exec`; postgres's
`PQconnectStart`, `PQconnectPoll` and `PQcancel` (the libpq oracle only: `postgres` has none); the ODBC oracle's calls.

A blocking call is not cut short by itself when its task is cancelled or
its deadline passes: the task sees that at its next call that can park.
`onCancelCall(f: fn(ptr), arg: ptr): CancelCall` registers a C function
that makes the call return early; while the guard lives, if the task is
cancelled or a `within` deadline passes while it is parked in a blocking
call, the runtime calls `f(arg)` once, on the program's thread, while the
call goes on running on its helper. `f` must be safe to call at the same
time as the call: `sqlite` registers `sqlite3_interrupt` around its steps
(the step returns `SQLITE_INTERRUPT`, error 9) and the ODBC oracle's `SQLCancel` around
statement calls. With a registration and a deadline a blocking call always
runs on a helper, so that the deadline is seen. Registrations nest; the
innermost counts.

**Signals** (SPEC 16, stage C2). A watched signal is an event of the loop
instead of its default action (for `SIGTERM` and `SIGINT`, the end of the
process); watching cannot be undone.

- `watchSignals(sigs: &[]int)` starts watching without waiting, so that an
  arrival before the first wait is kept, not lost. Constants: `SIGHUP`,
  `SIGINT`, `SIGQUIT`, `SIGUSR1`, `SIGUSR2`, `SIGTERM` (any signal 1 to 31
  a program may handle works; `SIGKILL`, `SIGSTOP` and the faults are a
  panic).
- `waitSignal(sigs: &[]int): Result[int, Cancelled]` watches `sigs` and
  parks until one arrives: its number. Every task waiting for it then gets
  it; with none waiting it is kept for the next wait (repeats before a wait
  are one). `terminated(): Result[int, Cancelled]` waits for `SIGTERM` or
  `SIGINT`. Cancellation and `within` end the wait as usual.

**Worker processes** (SPEC 16, stage C2): the way a program uses several
cores. Make what the workers share first (a listener, read-only data; each
gets a copy), then:

- `workers(n: int, f: &fn(int)): Result[[]WorkerEnd, GaveUp]` forks `n`
  processes, runs `f(i)` in process `i` and ends it (exit 0; a runtime
  error ends it with its code), and supervises them until all have ended;
  `workersWith(n, p: WorkerPolicy, f)` with a policy of its own.
- The supervisor restarts a crashed worker (a signal or an exit code other
  than 0) after a backoff, gives up after more than `p.maxCrashes` crashes
  of workers that were not yet ready (`workerReady`) within `p.windowMs` (sends the others `SIGTERM`, then `Err(GaveUp)`),
  forwards `SIGTERM` and `SIGINT` to every worker (a drain: no restarts;
  after `p.drainMs`, when it is more than 0, or a second signal from
  outside, `SIGKILL`), and returns when all have ended.
- `WorkerPolicy {maxCrashes, windowMs, backoffMs, maxBackoffMs, drainMs}`;
  `workerPolicy()` gives the defaults 5, 10,000, 100, 5,000 and 0 (the
  backoff doubles for each crash in a row of one worker, up to
  `maxBackoffMs`; a run that lasted `windowMs` ends the row).
- `WorkerEnd {index, pid, code, signal, drained, restarts}` (`toStr`: `worker
  2 (pid 4711): exit 0, drained, 1 restart`): the last process of each
  worker; `code` is -1 when `signal` ended it. `GaveUp {crashes, ends}`.
- `workerReady(): bool` (in a worker) marks the worker ready: it has set
  itself up and serves. A crash after that is restarted with the policy's
  backoff but never counts toward giving up, so only crashes before ready
  (a bad configuration, a missing file) can stop the supervisor, and a
  request that kills a worker cannot stop the server however often it is
  sent. False outside a worker. `httpserver.serve` calls it once it
  accepts.
- `stopWorkers(): bool` (in a worker) asks the supervisor for the drain
  (every worker gets `SIGTERM`, this one too); asking again, or from
  several workers, is one request. False outside a worker.
- A worker that serves calls `watchSignals(&[SIGTERM, SIGINT])` first and
  stops when `terminated()` returns (dropping its accept loop's future
  cancels the loop and its connections).
- `workers` stops the program with exit 15 at its call when the fork would
  not be safe: after the helper pool has started, while another task
  exists, or while the event loop holds a registration (a socket that has
  been waited on, a signal watch, a database connection's socket). Open
  database connections and pools in each worker.
- The supervisor runs no task while it supervises. Output written before the
  call is flushed first. A worker drops the globals at its end, as `main`'s
  end does; then under `LXL_CHECK=1` it checks its own objects: the count of
  live objects must not be above the one at its fork.

### net

TCP over IPv4 and IPv6 for tasks (SPEC 16; design/concurrency.md, stage C1b).
Sockets are non-blocking and registered with the runtime's epoll loop; a call
that would block parks the task until the socket is ready, so other tasks run
meanwhile, and a plain program (its main task) uses the same calls.

- Addresses are text: `"127.0.0.1:8080"`, `"[::1]:8080"`, `":8080"` and
  `"0.0.0.0:8080"` (every IPv4 interface), `"localhost:8080"` (127.0.0.1),
  port 0 for any free port. `listen` and `connect` take numeric addresses
  and `localhost`; `dial` also takes names. `canonicalAddr(addr): Option[str]` checks and normalizes one
  (IPv6 in RFC 5952 form). A malformed address is `EINVAL`.
- `listen(addr): Result[Listener, IoError]` (`SO_REUSEADDR`, backlog 4096);
  `Listener`: `localAddr(): str`, `accept(): Result[Conn, IoError]`,
  `close()`. A listener joins the event loop at its first `accept`, so one
  made before `task.workers` is shared by the workers: one accept queue,
  each worker accepting from it in its own loop (`EPOLLEXCLUSIVE`: one
  waiting worker is woken per connection).
- `listenReusePort(addr): Result[Listener, IoError]` is `listen` with
  `SO_REUSEPORT`: several sockets, in one process or in workers, listen on
  one port and the kernel spreads new connections between them by a hash of
  the addresses. Each socket has its own queue: connections queued at one
  whose process dies are reset. With port 0 each call gets a port of its
  own, so take the port from a first socket and close it before the
  workers listen.
- `connect(addr): Result[Conn, IoError]`: a non-blocking connect that parks
  until it is done (`ECONNREFUSED` and the like come from it).
- `resolve(host, port): Result[[]str, IoError]`: the addresses of a name as
  text (`"93.184.215.14:443"`, `"[2606:2800:21f::1]:443"`), in
  `getaddrinfo`'s order, without duplicates; an IP address comes back
  without a lookup. `getaddrinfo` is a `blocking` extern: it runs on the
  helper pool while the task parks, and cannot be cancelled while it runs
  (the cancellation or deadline is seen when it returns). A failed lookup
  is `op` `lookup` with errno `io.LOOKUP + n` (`isLookup()`, and
  `errorText` gives `gai_strerror`'s text).
- `dial(addr): Result[Conn, IoError]`: `connect` for `"host:port"` where
  host may be a name. Its addresses are tried in turn, IPv6 and IPv4
  interleaved; under a `task.within` deadline each attempt gets an equal
  share of the time left, at least 2 s. The error is the first attempt's.
  Native programs that reach `dial` or `resolve` are linked dynamically
  (libc's resolver needs nsswitch); programs that do not stay static.
- `Conn.readNow(buf)`: one read that never parks (`EAGAIN` when nothing is
  there); the http pool uses it to see whether an idle connection was
  closed. `Conn.quiet()`: that check for any pool (true when nothing has
  arrived and the peer has not closed); the database pools call it before
  they hand an idle connection out. `Conn.writeNow(data)`: one write that never parks (the count
  written, 0 when the socket's buffer is full), usable in a `drop` or
  inside `with` (`tls` sends close_notify with it). `Conn.take()` moves the
  socket out of a `Conn` (left closed), for a wrapper that gives its socket
  back (`tls.Conn.detach`).
- `Conn`: `read(buf: mut &[byte]): Result[int, IoError]` (0: the peer has
  closed), `write(data: &[byte]): Result[Unit, IoError]` (all of it, parking
  while the socket's buffer is full), `writeStr(s)`, `closeWrite()`
  (shutdown of the write side: the peer reads the end), `setNoDelay(on)`
  (`TCP_NODELAY`), `localAddr()`, `peerAddr()`, `close()`.
- Errors are `io.IoError {errno, op, path}`: `op` is `listen`, `accept`,
  `connect`, `read`, `write`, ...; `path` is the address (the peer's for a
  `Conn`). A call made by a cancelled task, or past the deadline of a
  `task.within`, does nothing and returns `ECANCELED` or `ETIMEDOUT`
  (`isCancelled()`, `isTimeout()`); so does a call parked when that happens.
  A write to a peer that has closed is `EPIPE` or `ECONNRESET`, never
  `SIGPIPE`.
- `Listener` and `Conn` are owned: dropping one (or `close()`) closes its
  socket and never parks, so it may happen inside `Shared.with`. The calls
  that can park take a last `w: Where` like `task`'s, and stop the program
  inside `with` (exit 13).

For servers (stage S1 of design/http-server.md):

- `c.split(): Halves` (`Halves {read: ReadHalf, write: WriteHalf}`) gives
  the two sides of a connection as owned values, so a request and a
  response can each hold one; the socket is closed when both have been
  dropped. `ReadHalf`: `read`, `readNow`, `peerAddr`, `remote` (the
  address `accept` saw, with no system call), `localAddr`, `writeInterim`
  (a short interim reply the reader owes, such as `100 Continue`) and
  `cancelOnHangup(halfClose): HangupGuard`. `WriteHalf`: `write`,
  `writeStr`, `writeStalled(data, stallMs)` (`ETIMEDOUT` when the peer
  takes nothing for `stallMs`; no limit on the whole write),
  `closeWrite`, `setNoDelay`, `peerAddr`.
- `cancelOnHangup` cancels the running task, as dropping its future does,
  when the peer resets the connection or (with `halfClose`) ends its
  stream, until the guard is dropped. It is not a read: data that arrives
  stays for the reader (`EPOLLRDHUP` in the event loop). A reset already
  seen cancels at once; an end of stream already pending when it is armed
  does not count, so a client that sends its request and shuts down its
  side still gets the reply.
- `l.setDeferAccept(secs)` (`TCP_DEFER_ACCEPT`: a connection reaches
  `accept` only once it has sent something); `spare()` reserves a spare
  descriptor (`/dev/null`) and `l.shed(mut &spare)`, after `accept`
  failed with `outOfDescriptors(&e)` (`EMFILE`, `ENFILE`), frees it,
  accepts and closes one waiting connection, and reserves it again, so the
  queue drains and its clients see a close instead of waiting. It gives
  `Ok(true)` when it closed a connection and `Ok(false)` when none was
  waiting. Linux's `accept` takes a descriptor before it looks at the
  queue, so at the limit it fails even with an empty queue; after
  `Ok(false)` the caller should wait (for a new connection or a freed
  descriptor) instead of calling `accept` again at once.

A `Conn` is used by one task at a time (it is owned). `httpserver` is an
HTTP/1.1 server built on it, `cmd/httpd.lxl` an example program on that
(with worker processes and a shared listener: `httpd ADDR POOL WORKERS`),
`cmd/httpload.lxl` a load client, and `http` an HTTP client.

### proc

Starting other programs, talking to them through pipes, and waiting for them
as part of the task model.

```lxl
let r = proc.output(&proc.command("git", ["rev-parse", "HEAD"])).expect("git")
println(r.stdoutStr())

var c = proc.command("sort", [])
c.stdin = proc.Stdio.Pipe
c.stdout = proc.Stdio.Pipe
var child = proc.start(&c).expect("sort")
child.stdin.writeStr("b\na\n").unwrap()
child.stdin.close()                                  // the child's end of input
let text = child.takeStdout().readAll().unwrap()
let exit = child.wait().unwrap()                     // Exit.Code(0)
```

- `command(program, args): Command` with the public fields `args`, `env`
  (`"NAME=value"` entries added to the parent's environment; `setEnv(name,
  value)` replaces one of the same name), `cleanEnv` (only `env`), `newGroup`, `cwd`,
  and `stdin`, `stdout`, `stderr` of type `Stdio`: `Inherit` (the default),
  `Pipe`, `Null` (/dev/null), `File(path)` (read for stdin, created and
  emptied for the others), `Append(path)` and, for stderr only, `Stdout`
  (2>&1). `arg(a)` adds an argument.
- `start(&cmd): Result[Child, ProcError]`. A program name without "/" is
  looked up before the fork in the PATH the child will get (a `PATH=` entry of
  `env`; else, with `cleanEnv`, `/usr/local/bin:/usr/bin:/bin`; else the
  parent's), so a missing program is an ordinary `Err` (ENOENT, `isNotFound()`). If the exec fails the child
  reports its errno through a close-on-exec pipe, and `start` returns it. The
  child has only descriptors 0 to 2, the default signal mask and
  dispositions.
- `Child`: `stdin: PipeWriter` and `stdout`, `stderr: PipeReader` (public
  fields; closed unless the stream is a `Pipe`), `takeStdin()`,
  `takeStdout()`, `takeStderr()` to move one into a task, `pid()`,
  `signal(sig)`, `kill()`, `wait(w): Result[Exit, ProcError]`. A `PipeReader`
  has `read(buf)` (0 at the end), `readAll()`, `close()`; a `PipeWriter` has
  `write(data)`, `writeStr(s)`, `close()`. The pipe ends are non-blocking and
  parked on like net's sockets, so a program without tasks works too. A write
  to a child that has closed its input is EPIPE, never SIGPIPE.
- `Exit` is `Code(n)` or `Signaled(sig)`, with `ok()`, `code()` (-1 when
  signaled), `signal()` (0 when not) and `toStr()` ("exit 3", "signal 9").
- `wait` parks on a pidfd in the event loop (Linux 5.3; an older kernel, or
  `LXL_NO_PIDFD=1`, polls every 10 ms). Cancellation or a `task.within`
  deadline while a child runs: SIGTERM, after 2 s SIGKILL, the child is
  collected, and the call returns ECANCELED or ETIMEDOUT
  (`isCancelled()`, `isTimeout()`). A second `wait` gives the same `Exit`.
- `newGroup` puts the child in a process group of its own (`setpgid` in the
  child and the parent). `signal`, `kill`, cancellation (SIGTERM, SIGKILL)
  and drop then signal the whole group, so grandchildren die too; `pgid()`
  is the group (the pid), 0 without `newGroup`. Waiting still collects the
  child only. It is off by default: a process in a group of its own cannot
  read the terminal under job control (SIGTTIN).
- Dropping a `Child` that was not waited for sends SIGKILL and collects it
  (no zombie, no orphan) and closes its pipes.
- `run(&cmd): Result[Exit, ProcError]` starts and waits with the streams as
  set (inherited by default). `output(&cmd): Result[Output, ProcError]`
  collects `stdout` and `stderr` (`[]byte`; `stdoutStr()`, `stderrStr()`) and
  the `exit`; `communicate(&cmd, input)` also writes `input` to the child's
  stdin. Both read standard output and standard error in tasks of their own,
  at once, so a full pipe cannot deadlock the child; the command's stdout and
  stderr settings are replaced by pipes, its stdin by a pipe unless it is
  `Null` or a `File`.
- `ProcError` is `errno`, `op` and `program`, with `toStr()`
  ("start nosuch: No such file or directory").
- `s.start(runOutput, cmd)` with a top-level `fn runOutput(c: proc.Command): Result[proc.Output, proc.ProcError] { return proc.output(&c) }` is a `Future`, so `task.all` and
  `task.any` run processes side by side; the loser of `any` is cancelled and
  its child stopped. A process with a live `Child` has descriptors in the
  event loop, so `task.workers` refuses to fork then (exit 15).

### tls

TLS 1.2 and 1.3 through the system's OpenSSL 3 (`libssl.so.3`,
`libcrypto.so.3`, by externs: no headers, no C shim), design/tls.md.

```
let ctx = try tls.client(tls.defaults())           // once: loads the system's trust store
var c = try ctx.connect(try net.dial("example.com:443"), "example.com")
try c.writeStr("GET / HTTP/1.1\r\nHost: example.com\r\nConnection: close\r\n\r\n")
let n = try c.read(mut &buf)                        // 0: the peer closed
try c.close()                                       // close_notify
```

- `Options` (`defaults()`): `caFile`, `caDir` (trust these instead of the
  system's store; see below), `insecureSkipVerify` (false), `pins` (SHA-256
  fingerprints, hex, comma-separated: the peer's certificate must be one),
  `certFile`, `keyFile` (a server's certificate, or a client's),
  `clientCaFile` (a server asks for and verifies client certificates),
  `minVersion` `Version.Tls12`, `maxVersion` `Version.Tls13`, `alpn`
  ("h2,http/1.1"): a client offers these; a server selects the first of
  its own that the client offers, refuses a client that offers ALPN but
  none of them (`no_application_protocol`), and with `""` answers without
  ALPN. `ctx.alpn()` gives the list, trimmed.
- `Context` (`client(o)`, `server(o)`): an SSL_CTX, owned, freed by its
  drop; `share()` gives another handle on it (to move into a task or a
  pool). `engine(serverName)`, `connect(sock, serverName)`,
  `accept(sock)`.
- A client verifies by default: the chain against the trust store, the
  name given to `connect` (`SSL_set1_host`; an IP literal is checked as an
  address, `[::1]` brackets dropped), SNI for a name. A name is required
  unless verification is off. Renegotiation is refused. Pins apply with
  or without verification.
- `caFile` and `caDir` **replace** the system's trust store; they do not
  add to it. With neither, a client trusts the system's store (which
  honours `SSL_CERT_FILE` and `SSL_CERT_DIR`). With either, it trusts only
  the CAs given (both, when both are set): a private CA's server verifies,
  a public site fails with `Verify` code 20 (untrusted issuer). To trust
  a private CA and the public ones, give one file that holds both:
  `cat /etc/ssl/certs/ca-certificates.crt corp-ca.pem > bundle.pem`. The
  bundle is a copy of the system's store and misses its later updates, so
  remake it when they come. `insecureSkipVerify` ignores both; a server
  verifies client certificates against `clientCaFile`.
- `Conn` (a socket): `read(buf)` (0 at close_notify, or the socket's end
  at a record boundary; the end inside a record is `Protocol`),
  `readNow(buf)` (never parks: `WANT_INPUT` when nothing is there),
  `quiet()` (net's, for TLS: a record without application data, such as a
  TLS 1.3 session ticket, does not count),
  `write(data)`, `writeStr(s)`, `handshake()`, `shutdown()` (close_notify,
  reading goes on), `close()`, `detach(): Detached {sock, rest}` (TLS ends
  without close_notify; the socket and what arrived after the last
  record), `version()`, `cipher()`, `alpn()`, `peer()`, `closeNotified()`,
  `engine()`, `peerAddr()`, `localAddr()`, `setNoDelay(on)`; `over(e,
  sock)` puts an engine (from memory mode) over a socket. Calls park their
  task on the socket; dropping an open `Conn` sends close_notify if the
  socket takes it at once (never parks).
- `Engine` (memory mode, for protocols that carry TLS in their own
  packets): `feed(ciphertext)`, `handshake(): Result[bool]` (true when
  done), `pending()`, `output(buf)`, `takeOutput()` (send these after every
  call), `read(buf)` (`WANT_INPUT`: feed more), `write(data)`,
  `shutdown()`, `unread()` (fed but not used), `isOpen()`, `version()`,
  `cipher()`, `alpn()`, `peer(): Option[Cert]` (`Cert {subject, issuer,
  notBefore, notAfter, sha256}`), `verifyResult()`, `verifyText()`,
  `resumed()`, `closeNotified()`.
- `Error {kind, msg, code, peer, cause}`, `toStr()` `tls: KIND: msg
  (peer)`; `Kind`: `Config`, `Handshake`, `Verify` (code is X509's verify
  result: 10 expired, 20 unknown issuer, 62 name mismatch, 64 address
  mismatch), `Protocol`, `Io`, `Timeout`, `Cancelled` (cause is the
  socket's `IoError`). msg is OpenSSL's error queue, which every call
  clears before and reads after, on the program's thread.
- `openHandles()` counts live contexts and engines (tests check it
  returns to 0); `libVersion()`.

Tests: `tests/run/tls_*.lxl` (against `openssl s_server`, two engines in
memory, and a server in the program, with a PKI made by the `openssl`
command at test time; skipped without it or without libssl) and
`http_tls.lxl`.

### url

URLs for http and https (RFC 3986), strict (design/http-client.md, H1).

- `parse(s): Result[Url, Error]`. `Url` is a value record: `scheme`, `host`
  (lowercased; IPv6 without brackets, in RFC 5952 form), `port` (the
  default when none is written), `path`, `query`/`hasQuery`,
  `fragment`/`hasFragment`, as written (escapes kept).
- Refused, with an `Error {msg, input}` that says why: other schemes, no
  authority, user information (`user:pass@`: sent in clear text), a
  non-ASCII, percent-encoded or empty host, an IPv6 zone, a host whose last
  label is a number but that is not a dotted quad (`1.2.3`, `0x7f.1`,
  `2130706433`: C's resolver reads those as addresses), a port outside 1 to
  65535, spaces, control characters, a character RFC 3986 does not allow
  where it stands, a `%` not followed by two hex digits.
- Methods: `target()` (path and query: what a request sends),
  `authority()` (`host[:port]`, the port only when not the default),
  `hostText()`, `hostPort()`, `origin()`, `isDefaultPort()`, `toStr()`
  (normalized: an explicit default port is dropped), `eq`,
  `withoutFragment()`, `withQuery(&q)`, `resolve(ref)` (a relative
  reference against the URL, RFC 3986 section 5, with dot segments
  removed).
- `encode(s)` (everything but the unreserved characters as `%XX`),
  `decode(s)`; `Query` (`newQuery`, `add`, `get`, `all`, `size`, `at`,
  `encode`) and `parseQuery(s)` (`+` is a space in a query).

### http

An HTTP/1.1 client for tasks over TCP and TLS (https, through `tls`), and the
head parsing servers share (design/http-client.md, H1 and H2). A reply
with any status is `Ok`; `r.ok()` says whether it is 2xx.

```
let r = try http.get("http://api.example.com/v1/rates?ccy=EUR")
let body = try r.text()

var o = http.defaults()
o.maxPerHost = 8
let c = http.newClient(o)
var rq = http.request("POST", "http://api.example.com/v1/orders")
rq.header("Content-Type", "application/json")
rq.body = json
let r = try c.send(&rq)
```

- `Request {method, url, headers, body}` from `request(method, url)`, with
  `header(name, value)`. Host, User-Agent and Content-Length are added when
  not given. Refused before sending (`Invalid`): a method that is not a
  token, a header name that is not a token, a control character in a value,
  a Transfer-Encoding, a Content-Length that is not the body's.
- `Options` (`defaults()`): `maxPerHost` 16, `timeoutMs` 30000 (the whole
  call, redirects included, and then the body's reads; 0: none), `maxBody`
  16 MiB (for `text` and `bytes`), `redirects` true, `maxRedirects` 10,
  `allowHttpsToHttp` false, `idleTimeoutMs` 90000, `userAgent` "lxl",
  `tls` (`tls.Options` for https): `tls.defaults()` with `alpn`
  "http/1.1", so the server's certificate is verified against the system's
  store and its name against the URL's host. `o.tls.caFile = "ca.pem"`
  trusts that CA instead of the system's store (not as well as it: see
  tls above); `o.tls.insecureSkipVerify = true` turns verification
  off; pins and a client certificate are `tls` options too.
- `Client` (`newClient(o)`) is a copy handle over a `task.Shared` pool:
  copies share it. `send(&rq)`, `get(u)`, `head(u)`,
  `post(u, contentType, body)`, `put(...)`, `delete(u)`; `options()`,
  `stats()` (`Stats {open, idle, waiting, dials, reuses, retries}`),
  `closeIdle()`. The module's `get`, `head`, `post`, `put`, `delete` and
  `send` use one default client made on first use.
- `Response`: `status`, `reason`, `minor`, `headers`, `url` (after
  redirects); `ok()`, `header(name)`, `contentLength()` (-1 when not
  given), `text()` and `bytes()` (the whole body, at most `maxBody`, else
  `TooLarge`), `read(mut &buf)` (streams; 0 at the end), `discard(limit)`,
  `close()`.
- `Error {kind, msg, url}`; `Kind`: `Url`, `Invalid`, `Dns`, `Connect`,
  `Tls`, `Timeout`, `Cancelled`, `Io`, `Protocol`, `TooLarge`,
  `Redirects`, `Process`. `toStr()` is `http: KIND: msg (url)`.
- The pool keeps at most `maxPerHost` connections per scheme, host and
  port; callers past that wait in FIFO order. An idle connection is closed
  after `idleTimeoutMs`, or after the server's `Keep-Alive: timeout=N`
  less one second, and one idle for more than 100 ms is checked (a read
  that does not park) before reuse.
- A `Response` holds its connection. Dropped with its body read to the end
  (or with all of it already arrived) on a connection the server keeps,
  the connection goes back to the pool; otherwise it is closed. A
  cancelled or timed-out call closes its connection.
- A request that fails on a reused connection before any of the reply came
  (the server closed it meanwhile) is sent once more on a new connection,
  for GET, HEAD, PUT, DELETE, OPTIONS and TRACE, never POST or PATCH.
- Redirects (301, 302, 303, 307, 308) are followed up to `maxRedirects`:
  303, and 301/302 after POST, become GET without a body; Authorization,
  Cookie and Proxy-Authorization are dropped when the origin changes; https
  to http is refused unless `allowHttpsToHttp`.
- Replies are framed strictly (RFC 9112 section 6.3): Content-Length with
  Transfer-Encoding, differing Content-Lengths, a coding other than
  chunked, obsolete line folding, a bare LF, a bad chunk size and a
  connection closed inside a head or a framed body are `Protocol` errors.
  Limits: a head of 64 KiB and 100 lines (trailers too), 8 interim (1xx)
  replies, a 4 KiB chunk-size line.
- A client used in another process than the one that made it (after a
  fork) refuses with `Process`: make clients inside each worker.
- https: a client makes one `tls.Context` from `o.tls` at its first https
  request (bad options fail with `Tls` before connecting); each connection
  does its own handshake (no session resumption yet). A certificate that
  does not verify, a failed handshake and a damaged record are `Tls`
  errors whose msg names the reason (`verify: certificate has expired`,
  `handshake: unsupported protocol`); socket errors during the handshake
  are `Connect` (or `Timeout`, `Cancelled`). Pools are per scheme, host
  and port, so http and https connections to one host are separate.
- Shared parsing, used by `httpserver`: `headEnd`, `parseFields`,
  `contentLength`, `parseRequest` (`RequestHead {method, target, minor,
  headers}`, `keepAlive()`, `bodyLength()`), `equalFold`, `isToken`,
  `isFieldValue`, `Headers` (`get`, `has`, `values`, `add`, `set`,
  `remove`, `hasToken`, ...).

Tests: `tests/run/url_*.lxl`, `http_*.lxl` (against the route and scripted
servers of `tests/support/httptest.lxl`; `http_tls.lxl` against an https
server of `tests/support/tlstest.lxl`; `http_live.lxl` only with
`LXL_HTTP_LIVE=1`, else it exits 77), and `tests/httpgen.py`, which
generates reply framings and checks every body on both backends.

`both` and `forEach` (concurrent children that borrow the parent's locals)
are not there yet: a task's function is a plain `fn`, and passing borrows
into a task needs the checker's help (design/concurrency.md, section 5).

### httpserver

An HTTP/1.1 server for tasks (design/http-server.md, stage S1). A module of
its own: the client in `http` already has a `Request`, `Response`, `Error`
and `defaults`, so a program that has both imports `"http"` and
`"httpserver" as hs`. The handler API is meant to stay the same for
HTTP/2 (S3).

```
import "httpserver" as http

type App = value record { db: postgres.Pool }      // a copy type: handles only

fn account(app: &App, rq: mut &http.Request, w: mut &http.Response): Result[Unit, http.Error] {
    let id = try rq.paramInt("id")                          // 400 when not an integer
    var c = try http.check(app.db.acquire(), 503)           // any error as a 503
    let rows = try http.check(c.conn().query("SELECT name FROM account WHERE id = $1", &[postgres.Value.Int(id)]), 500)
    if rows.rowCount() == 0 { return w.fail(404) }
    return w.json(toJson(&rows))
}

var r = http.router[App]()
r.use(http.requestId[App])
r.use(http.accessLog[App])
r.handle("GET /accounts/{id}", account)
let st = try http.serve(net.listen(":8080").expect("listen"), app, r, http.defaults())
```

- `serve[A: copy](ln, app: A, r: Router[A], cfg: Config): Result[Stats,
  Error]` serves until `rq.stopServer()`, or `SIGTERM`/`SIGINT` when
  `cfg.signals`. Then it drains: it closes the listener (new connections are
  refused) and the idle connections, lets the requests in flight finish
  (their replies say `Connection: close`) for up to `drainMs`, cancels the
  rest, and returns its counters. One task per connection, keep-alive,
  pipelined requests answered in order. Each handler gets `&app`, a copy per
  connection. `Err` (kind `Config`) before anything is accepted when a
  pattern is invalid or two conflict, or when `RLIMIT_NOFILE` (raised as
  far as the hard limit allows) or `vm.max_map_count` is too low for
  `maxConns`. In a worker it marks the worker ready (`task.workerReady`);
  `workerPolicy()` is task's with a 35 s drain.
- `Handler[A] = fn(&A, mut &Request, mut &Response): Result[Unit, Error]`.
  `router[A]()`; `r.handle(pattern, h)`; `r.handleWith(pattern, h,
  RouteOpts{deadlineMs, maxBody})` (`routeOpts()` gives -1 for both: the
  Config's; `deadlineMs` 0 is none, for server-sent events).
- Patterns are Go 1.22's: `"[METHOD ][HOST]/[PATH]"`, `{name}` one
  segment, `{name...}` the rest, `{$}` the end of a path ending in `/`, a
  pattern ending in `/` matches everything under it. GET also answers HEAD
  (no body sent). The most specific pattern wins; a path that matches with
  another method gets 405 with `Allow`; `/dir` is redirected (301) to
  `/dir/` when only the subtree pattern matches; otherwise 404.
- Middleware: `Middleware[A] = fn(&A, mut &Request, mut &Response,
  Next[A]): Result[Unit, Error]`; `next.run(app, rq, w)` runs the rest.
  `r.use(m)` for every request (404s and 405s too), `r.useUnder(prefix,
  m)` for paths under prefix; the first added runs outermost. In the
  library: `requestId` (16 random bytes in hex, or a trusted proxy's
  `X-Request-Id` of 1 to 64 token characters; sent back as
  `X-Request-Id`), `accessLog` (below) and `securityHeaders`
  (`Content-Security-Policy: default-src 'self'; frame-ancestors 'none'`,
  `Referrer-Policy: no-referrer`, `Cross-Origin-Opener-Policy:
  same-origin`).
- `Request`: `method`, `path` (decoded once), `host` (validated,
  lowercase), `proto`, `headers` (`http.Headers`), `peer`, `id`, `pattern`;
  `param(name)`, `paramInt(name)`, `query(name)` (decoded), `header(name)`,
  `rawTarget()`, `rawQuery()`, `client()` (the peer, or for a trusted proxy
  the rightmost untrusted `X-Forwarded-For` address), `note(key, value)`
  (a field for the access log), `serverStats()`, `stopServer()`. The body:
  `read(mut &buf)` (streams; 0 at the end), `bytes(limit)` and
  `text(limit)` (413 past the limit or the route's `maxBody`; 400 when the
  text is not UTF-8), `bodyRead()`, `trailers()`. With `Expect:
  100-continue` the 100 is sent at the first read; a body nobody read is
  read and dropped up to `maxDrain`, else the connection closes.
- `Response`: `status(code)`, `header(name, value)` (replaces),
  `addHeader` (adds: `Set-Cookie`), `trailer(name, value)`, `write(data)`,
  `writeStr(s)`, `flush()`, `text(s)`, `json(s)`, `fail(code)` (the
  library's fixed body: the status line and the request id),
  `redirect(code, location)`, `startEvents()` and `event(name, data)`
  (server-sent events), `statusCode()`, `headWritten()`, `bodyBytes()`.
  Nothing is sent before the handler returns, `flush` is called, or 32 KiB
  of body is buffered; a finished reply whose head was not yet written gets
  a `Content-Length`, others are chunked (until the close for HTTP/1.0). A
  `Response` that is not written to answers 200 with an empty body.
- `Error {status, kind, msg}` (`ErrorKind`: `Client`, `Server`, `Gone`,
  `Timeout`, `Limit`, `Protocol`, `Config`); `error(status, msg)`;
  `check(r, status)` turns any `Result[T, E: Show]` into one. A handler's
  `Err` before the head is written answers `status` with the fixed body
  (headers it had set are dropped; `msg` goes to the log, never to the
  client); after the head is written, the connection is closed short of the
  body's end, so the client sees a truncated reply.
- The route's deadline (`deadlineMs`, 30 s) is a `task.within` around the
  middleware and the handler; past it, a reply not yet started is 503.
  While the handler runs, a client that hangs up (a reset, or with
  `cancelOnHalfClose` also a half-close) cancels the connection's task:
  the handler's next call that can park returns `Cancelled`, a Postgres
  query is cancelled on the server (a CancelRequest), a SQLite step is
  interrupted, an ODBC call gets `SQLCancel`.
- `Stats {accepted, requests, open, rejected, timeouts, gone, errors, shed,
  idleClosed, c2xx, c3xx, c4xx, c5xx, logDropped}` (`toStr`: the first
  seven).

**TLS.** `serveTls(ln, ctx, app, r, cfg)` is `serve` over TLS: `ctx` is
`tls.server(options)` with `certFile` and `keyFile` (and optionally
`clientCaFile`). The handshake runs on the connection's task and parks on
the socket, bounded by `headerTimeoutMs`; a failed or late handshake closes
the connection without an HTTP reply.
The context's `alpn` is `""` (ALPN not answered: any client gets HTTP/1.1)
or `"http/1.1"` (a client that offers ALPN without it, such as an `h2`-only
one, is refused with `no_application_protocol`); any other list is a
Config error, as the server speaks only HTTP/1.1. The request and
response sides share the one SSL object (takes, parks, gives back), so
HTTP/1.1's sequential reads and writes stay correct. Not yet: SNI
certificate selection, session tickets made before a worker fork, a
handshake cap, and HSTS.

**Forms.** `rq.form(limit)` reads and parses the body as
`application/x-www-form-urlencoded` or `multipart/form-data` (another type
is 415). It returns `Form`: `get(name)`, `values(name)`, `size()`, `at(i)`,
`fileCount()`, `fileAt(i)` and `file(name): Option[&File]`. A `File` has
`field`, `filename` (as sent; untrusted), `headers` and `data`. Multipart
fields must be UTF-8; a part with a filename may hold any bytes. `filename*`
(RFC 5987, UTF-8) is decoded. The body is held in memory, bounded by
`limit`, `maxBody`, `maxParams`, `maxParts`, `maxPartHeaders` and
`maxPartHeadBytes`; a part's headers are checked by `http.parseFields`.
The body is read completely, so unread parts cannot be streamed: keep
uploads within `maxBody` or use `rq.read` directly.

**Server-sent events.** `w.startEvents()` writes the head
(`text/event-stream`, `no-store`) and flushes it; `w.event(name, data)`
writes and flushes one event; `w.eventWith(id, name, data)` adds an `id`;
`w.retry(ms)` writes a reconnect delay; `w.comment(text)` writes a comment
and `w.keepAlive()` the bare `:\n\n`. The `sse` module provides a broadcast
hub for handlers: `sse.newFeed()`, `feed.publish(Event{id, name, data})`,
`feed.subscribe()` (or `feed.subscribeAfter(lastEventId)` for a
reconnecting client) for a handler's `Cursor`, and `cursor.wait(ms)`:
`Ok(Some(ev))`, `Ok(None)` on the keep-alive timeout, or `Err` when the
task is cancelled or an enclosing deadline passes. A handler that wants a
comment every 15 s calls `wait(15000)` and `w.keepAlive()` on `Ok(None)`.

**Parsing** is strict (design/http-server.md section 3.1–3.3): anything
two parsers could read differently gets a 4xx and the connection closed.
Refused: `Content-Length` with `Transfer-Encoding`, differing or listed
lengths, a coding other than `chunked`, obsolete line folding, whitespace
before a colon, a bare CR or LF, NUL and controls in a field, a bad
request line or version (`HTTP/2.0` and the h2 preface: 505), a bad chunk
size (more than 16 hex digits) or extension, a missing or repeated Host
(400) or one not in `hosts` (421), an absolute-form target whose host is
not the Host, dot segments (raw or encoded), encoded `/` or NUL, invalid
UTF-8 in the decoded path, `Expect` other than `100-continue` (417). Up to
two empty lines before a request are skipped. Response headers are checked
too: a name that is not a token or a value with CR, LF, NUL or other
controls fails the response (500, the header named in the log), and no
byte of it is sent. Every response has `Date` and `X-Content-Type-Options:
nosniff`; error responses `Cache-Control: no-store`; a body without a
`Content-Type` is `application/octet-stream`. `redirect` takes a path
starting with a single `/`, or an http(s) URL whose host is in
`redirectHosts`; anything else is a 500, never an open redirect.

**Limits and timeouts** (`Config`, `defaults()`):

| Field | Default | What happens past it |
|---|---:|---|
| `headerTimeoutMs` | 10,000 | the whole head from its first byte: 408 and close |
| `idleTimeoutMs` | 60,000 | a keep-alive connection waiting for its next request is closed |
| `idlePressureMs` | 5,000 | the idle timeout from 80 % of `maxConns` on |
| `bodyGraceMs`, `bodyMinRate` | 10,000, 1,024 bytes/s | a body: any rate for the grace, then at least the rate (credit at most 5 s ahead): 408 and close |
| `writeStallMs` | 30,000 | a write that makes no progress this long: the reply fails and the connection closes (no limit on a whole write) |
| `deadlineMs` | 30,000 | the route's deadline: 503 if nothing was written |
| `drainMs` | 30,000 | requests still running after a stop are cancelled |
| `maxConns` | 10,000 | the accept loop waits; new connections wait in the kernel's queue |
| `maxConnsPerIp` | 0 (off) | per worker: 503 and close |
| `maxRequestsPerConn` | 1,000 | `Connection: close` on the last |
| `maxHeadBytes`, `maxHeaders`, `maxLineBytes` | 16,384, 100, 8,192 | 431 and close |
| `maxTargetBytes` | 8,192 | 414 and close |
| `maxBody` | 1 MiB | 413 (a declared length over it before any byte is read) |
| `maxDrain` | 256 KiB | an unread body larger than this closes the connection |
| `maxParams` | 1,000 | 400 |
| `maxParts`, `maxPartHeaders`, `maxPartHeadBytes` | 1,000, 64, 16,384 | 413 |
| `maxTrailerBytes`, `maxTrailers` | 8,192, 32 | 431 and close |
| `memBudget` | 512 MiB | buffered bytes in the worker: new requests get 503 and close |
| `fdMargin` | 64 | descriptors kept free beyond `maxConns`, checked at start |
| `acceptBatch` | 16 | the accept loop yields after this many accepts |
| `deferAccept` | true | `TCP_DEFER_ACCEPT` with the head timeout |
| `cancelOnHalfClose` | true | a half-close cancels the running handler, as a reset does |
| `signals` | true | `SIGTERM`/`SIGINT` drain the server |
| `hosts`, `redirectHosts`, `trustedProxies` | empty | Hosts served (others 421); redirect targets; proxies believed |
| `logFd` | 1 | where `accessLog` writes (-1: nowhere) |

On `EMFILE`/`ENFILE` the accept loop uses the spare descriptor to accept
and close one waiting connection (`shed`, counted in `Stats.shed`); when
none was waiting, it sleeps 10 ms before trying again, so a server at its
descriptor limit does not spin. A connection's task yields after
each request and every 64 KiB of body copy, so a client that pipelines
without pause does not starve the others. After a reply that ends the
connection, the server shuts down its side and reads and drops what the
client still sends for up to 500 ms (256 KiB), so the client's unread
request bytes do not turn the close into a reset that loses the reply. An
idle connection costs about 15.5 KB (its task's stack pages, a 4 KiB read
buffer and a 512-byte output buffer, which grows as replies need).

**The access log** (`accessLog`) is one logfmt line per request, written by
the server through a `blocking` `write` (every 100 ms or 64 KiB; past
4 MiB unwritten, lines are dropped and counted in `logDropped`), never by
the request's task, so a slow reader of the log does not stall requests:

    time=2026-11-03T10:20:30Z id=1f0c... pid=4711 peer=10.0.0.7:51234 method=GET route="GET /accounts/{id}" path=/accounts/7 status=200 in=0 out=13 us=180 outcome=ok

Values from input are escaped (controls, quotes, backslashes and bytes past
0x7e as `\xHH`) and cut at 256 bytes. The query, `Authorization` and
`Cookie` are not logged; `rq.note` adds fields.

The router and middleware are held in a `task.Frozen`, which every
connection's task reads at once. Not there yet (parts of S2 and S4): SNI
certificate selection, session tickets across workers, a handshake cap,
HTTP/2, `w.hint` (103), full duplex, a `Cookie` type, `traceparent`, a JSON
log, `maxBlocking`, per-IP limits across workers, static files, compression
and WebSockets.

Tests: `tests/run/http_server_*.lxl` (the parsing corpus, routing, limits,
slow clients, hangup cancellation with Postgres and SQLite, drain, the
access log, an accept flood, running out of descriptors; through `tests/support/srvtest.lxl` and `srvrun.lxl`),
`task_workers_ready.lxl`, and `tests/httpsrvgen.py`, which checks the
parsing against Go's net/http and Node's llhttp on generated request
streams (`gate.sh full`).

### sse

A broadcast hub for server-sent events (import `"sse"`). `newFeed()` gives a
counted `Feed` that keeps the last `KEEP` (64) events;
`publish(Event{id, name, data})` adds one and wakes every waiting cursor.
`subscribe()` gives a `Cursor` that reads the events published after it,
in order, including those published while its handler was busy writing;
`wait(ms)` gives `Ok(Some(event))`, `Ok(None)` when its own timeout passes
(send a keep-alive then), or `Err` when the task is cancelled or an
enclosing deadline passes. A cursor more than `KEEP` behind skips to the
oldest kept event; `missed()` counts what it skipped.
`subscribeAfter(lastId)` resumes a reconnecting client after its
`Last-Event-ID`: the events after the newest kept one with that id, or from
the oldest kept event when the feed no longer has it (`""` is
`subscribe()`); resuming needs unique ids. Events are per process: workers
do not share a feed, so a reconnect that reaches another worker resumes
from that worker's oldest kept event.

```
let feed = sse.newFeed()
r.handleWith("GET /events", events, http.RouteOpts{deadlineMs: 0, maxBody: 0})

fn events(app: &App, rq: mut &http.Request, w: mut &http.Response): Result[Unit, http.Error] {
    var sub = app.feed.subscribeAfter(rq.headers.get("Last-Event-ID").unwrapOr(""))
    try w.startEvents()
    while true {
        match sub.wait(15000, here()) {
            Ok(v) {
                match v {
                    Some(ev) { try w.eventWith(ev.id, ev.name, ev.data) }
                    None { try w.keepAlive() }
                }
            }
            Err(_) { return Ok(Unit{}) }
        }
    }
}
```

### redis

A Redis client over RESP, for tasks (no Redis C library). It speaks RESP2 and asks
for RESP3 with `HELLO 3`, falling back to RESP2 on a server before Redis 6;
the parser handles every ordinary reply type of both versions, including
maps, sets, booleans, doubles, big numbers, verbatim strings, push messages
and attributes; streamed strings and aggregates (`$?`, `*?`) are not
supported. Calls park the task on the same epoll loop as `net`, `tls` and
the database clients; one connection is used by one task at a time.

```lxl
import "redis"

var c = try redis.connect("redis://127.0.0.1:6379/0")
try c.set("order:42", "24.49")
println((try c.get("order:42")).unwrapOr("missing"))
try c.hset("order:42", "amount", "24.49")
println((try c.hget("order:42", "amount")).unwrapOr("missing"))
```

- **Config** (`defaults()`): `host`, `port`, `unixPath`, `username`,
  `password`, `db`, `tls`, `tlsOptions` (`tls.Options`), `tlsName`,
  `timeoutMs` (each socket wait; 0 is none), `maxBulk` (64 MiB),
  `clientName`, `resp3`. `parseUrl` takes
  `redis://[[user]:password@]host[:port][/db]`, `rediss://` and
  `unix:///path`, with `?db=N&timeout=MS&resp3=0`; a bare `host:port` is
  also accepted. `connect(text)` parses and connects; `connectWith(&cfg)`
  takes a configuration. TLS is verified by default and uses the system's
  store; `tlsName` is the name sent as SNI and checked (the host when empty).
- **Value** is a closed type: `Nil`, `Status` (`+OK`), `Str` (bulk),
  `Int`, `Double`, `Bool`, `BigNumber`, `Verbatim`, `Array`, `Map`
  (`[]Pair`), `Set`, `Push` and `Error`. A server error is
  `Value.Error`, not a transport error; `command` returns it as `Ok`, while
  the typed helpers turn it into `Error{kind: Kind.Server}`. `text()`,
  `errorText()`, `count()` and `toStr()` read a reply.
- **Connection**: `command(args)`, `send`/`receive` for pipelining,
  `next` for a pub/sub or client-tracking push. `idle()` is true when no
  MULTI is open and no transport or protocol error has happened;
  `inTransaction()`, `database()`, `isResp3()`, `address()`. `close()`
  consumes it; dropping it closes the socket.
- **Commands**: `ping`, `echo`, `get`, `set`, `setEx`, `setNx`, `getDel`,
  `del`, `exists`, `expire`, `ttl`, `incr`/`incrBy`, `decr`/`decrBy`,
  `mset`, `mget`; hashes `hget`, `hset`, `hdel`, `hlen`, `hexists`,
  `hgetall` (RESP2's flat array and RESP3's map both become `PairStr`);
  lists `lpush`, `rpush`, `lpop`, `rpop`, `llen`, `lrange`; sets `sadd`,
  `srem`, `smembers`, `sismember`; `publish`, `subscribe`, `scan`,
  `multi`/`exec`/`discard`. Inside a MULTI, send the queued commands with
  `command` (they reply `QUEUED`); the typed helpers expect the command's
  final reply. `WATCH`/`UNWATCH` are generic and are not tracked by the pool,
  so use a dedicated connection for an optimistic transaction. Anything else
  is `command`.
- **Pool** (`newPool(url, size)` / `newPoolWith(cfg, size)`): at most
  `size` connections, `acquire()` parks until one is free, a `Lease` gives
  it back when dropped (a connection in MULTI or broken is closed
  instead), `stats()` gives open/idle/waiting. Copies of a `Pool` share it
  (a `task.Shared`). `Lease.conn()` is the `Conn`, for every command:
  `try l.conn().set(k, v)`. The shared `pool` module's
  (`pool.Pool[Conn, Config, Error]`, design/pool.md). Do not put a
  subscribed connection back in a pool.
- **Limits**: a protocol line of 64 KiB, a bulk value of `maxBulk`, one
  million elements or pairs in an aggregate, and 32 levels of nesting; a
  reply past one is a `Protocol` error and the connection is unusable.
  `Config.timeoutMs` bounds each socket wait; a caller can also use
  `task.within` for a whole operation.
- **Errors** are `Error{kind, msg}` with kind `Config`, `Connect`, `Dns`,
  `Tls`, `Timeout`, `Cancelled`, `Io`, `Protocol`, `Auth` or `Server`;
  `toStr()` is `redis: KIND: msg`. A program that uses the module is
  dynamically linked to OpenSSL for TLS (and to libc for name lookup), as
  `http` is.

#### Verification

`tests/run/redis_basic.lxl` runs against the in-process
`tests/support/redistest.lxl` (RESP2 and RESP3, strings, hashes, lists,
sets, pipelining, server errors, AUTH, pool tasks, URL parsing and the
reply-type corpus), and is part of the quick and full gates. In the full
gate it also runs under ASan and TSan, and through the native/C differential
runner. `tests/run/redis_live.lxl` and `tests/run/redis_live_extra.lxl` run
against a live server with `LXL_REDIS_LIVE=1` (default
`redis://127.0.0.1:6379/15`; otherwise exit 77). The extra test covers
`setEx`, `setNx`, `expire`/`ttl`, the hash, list and set tails, `SCAN`,
`MULTI`/`EXEC`, `WATCH`, binary values, pub/sub and a read timeout.

Checked on 2026-11-08:

- quick and full gates pass; the full gate includes `redis_basic` under
  ASan and TSan and in the native red-team run.
- `redis_basic` and `redis_gate.py` pass on the native and C backends.
- a live Redis 7.0.15 passed `redis_live` and `redis_live_extra` over TCP;
  a separate connection with a test CA passed over TLS, and the client was
  checked with password and ACL-user AUTH, `--insecure`, a task pool,
  pub/sub, transactions, `WATCH`, expiry, binary values and a `BLPOP` read
  timeout.
- `cmd/redis_gate.py` covers the CLI's one-shot, pipe, `-x`, `-r`,
  raw/formatted, error and exit-code paths on both backends; it is a CI
  step.

    python3 lexell/lib/run_tests.py redis          # the hermetic tests
    python3 lexell/cmd/redis_gate.py              # CLI, native
    python3 lexell/cmd/redis_gate.py --c          # CLI, through C
    LXL_REDIS_LIVE=1 LXL_REDIS=redis://127.0.0.1:6379/15 \
        python3 lexell/lib/run_tests.py --live redis

`--live redis` runs both live tests.

#### Not covered

- Live testing used Redis 7.0.15 only; older and newer servers, Cluster,
  Sentinel and managed Redis variants are untested. There is no cluster
  redirection or slot routing.
- Streamed RESP3 replies (`$?`, `*?`) are rejected as protocol errors.
- Unix sockets and IPv6 are implemented and parsed, but the live test uses
  TCP and IPv4. TLS client certificates, pins and `tlsName` are implemented
  but not exercised live.
- The interactive CLI prompt is not automated; one-shot and pipe modes are.
- Typed helpers inside `MULTI` see `QUEUED`; use `command` for queued
  commands. `WATCH` is not tracked by the pool; use a dedicated connection.
- A pool checks an idle connection before it hands it out (`quiet()`, no
  round trip): one the server has closed is replaced by a new one without
  an error. One that the server closes while it is leased fails as before.
- No performance benchmark is recorded for Redis.

### regex

Regular expressions with RE2's syntax, matched in time linear in the size of
the text whatever the pattern (design/regex.md, phases R1 and R2). A port of
Go's `regexp` and `regexp/syntax` (BSD-3-Clause; see `NOTICE`): the same
parser, errors and limits, the same program, the same three matchers, and
the same results, checked against Go's own tests and against Go on random
patterns; plus RE2's lazy DFA and literal searches after Rust's `regex`,
which find the same matches faster.

```lxl
import "regex"

let re = try regex.compile("(?P<y>\\d{4})-(?P<m>\\d{2})-(?P<d>\\d{2})")
if re.isMatch("on 2026-11-03") { ... }
match re.find(text) { Some(m) { m.start; m.end; m.text } None {} }
for m in re.findAll(text) { ... }
match re.captures(text) {
    Some(c) { let y = c.name("y").unwrap().text }
    None {}
}
let s = re.replaceAll(text, "$d/$m/$y")     // "${d}x" when a letter follows
let parts = re.split(text)
```

- **Compiling.** `compile(pattern): Result[Regex, Error]` (leftmost-first,
  Perl's syntax, as Go's `Compile`); `compileLongest` (leftmost-longest);
  `compilePosix` (POSIX syntax: no `\d` and the like, leftmost-longest);
  `mustCompile` (panics on an error: for constant patterns);
  `isMatchStr(pattern, text): Result[bool, Error]`. A `Regex` is immutable
  once compiled; each call has its own matching state.
- **Error** `{code: ErrorCode, expr, pos}`: `message()` is Go's text
  (`error parsing regexp: missing closing ): `(abc``), `toStr()` adds a
  hint for the refused features below.
- **Searching.** `isMatch(text)`; `find(text): Option[Match]` and
  `findFrom(text, from)`; `findIndex(text): Option[Span]`; `findAll`,
  `findN(text, n)`, `findAllIndex`, `findAllIndexN`. `Match {start, end,
  text}` and `Span {start, end}` are value records; offsets are byte offsets.
  A search with `n < 0` finds all; as in Go, an empty match right after the
  previous match is skipped.
- **Searchers.** `searcher(): Searcher` keeps a Regex's matching state (the
  DFA's states) between searches; `findWith(mut &s, text, from):
  Option[Span]` is `findFrom` through it, and `matchEndWith(mut &s, text,
  from): int` only says whether there is a match and gives the end of one
  (the first to end; -1 for none). Through a Searcher the DFA runs on short
  texts too, so searching a line at a time costs little.
  `matchingLines(mut &s, text, from, to, max, mut &out): int` appends the
  start and end of each line of `text[from..to]` with a match (whole lines;
  for patterns that cannot match a newline), at most `max`, and returns
  where it stopped: the DFA runs over the lines once and starts again after
  each line it reports. With them,
  `canMatchNewline()` (whether a match can contain `"\n"`) and
  `requiredLiteral()` (a literal every match contains, `""` if none is known)
  let a tool like grep search lines and literals first.
- **Groups.** `captures(text): Option[Captures]`, `capturesAll`,
  `capturesN`; `Captures`: `count()` (groups plus one), `get(i):
  Option[Match]` (None for a group that did not take part), `whole()`,
  `name(n): Option[Match]`, `str(i)` (`""` if unset), `indexes()`. The index
  forms are `submatchIndex(text): []int` (2 slots per group, -1 unset; empty
  when there is no match) and `allSubmatchIndex(text, n): [][]int`.
  `numGroups()`, `groupNames()` (`""` for group 0 and unnamed groups),
  `groupIndex(name)` (-1 if none).
- **Replacing.** `replaceAll(text, template)`, `replace` (the first match),
  `replaceN`; in the template `$1`, `$name`, `${name}` and `${1}` expand to
  the group (empty if unset or unknown), `$$` is `$`; the longest name is
  taken, so `$1x` is the group `1x`: write `${1}x`. `expand(template,
  &Captures)` expands one template. `replaceAllLiteral` (no expansion),
  `replaceAllFunc(text, f: &fn(str): str)`.
- **Others.** `split(text)`, `splitN(text, n)` (Go's semantics, n < 0 for
  all); `quote(s)` escapes ``\.+*?()|[]{}^$``; `literalPrefix(): Prefix
  {text, complete}`; `pattern()`; `isLongest()`; `matcherFor(n)` (which
  matcher a search of n bytes uses: `onepass`, `literal`, `dfa`,
  `backtrack` or `pike`); `literalSearch()` (the DFA's literal search:
  `prefix`, `inner`, `suffix`, `line` or `none`; `line`: matches start at
  line starts, so the DFA skips to the next line). For tests,
  `compileForcing(pattern, longest, matcher)` forces `pike`, `backtrack`,
  `dfa` (no literal search), `prefilter` (every literal search there is) or
  `dfatiny` (a cache of three states, cleared all the time).

**Syntax.** RE2's, as Go: literals and escapes (`\x41`, `\x{263a}`, `\Q...\E`,
`\a \f \t \n \r \v`, octal); `.`; classes `[...]`, `[^...]`, `[[:alpha:]]`
and the other POSIX classes; `\d \w \s \D \W \S` (ASCII); `\pL`, `\p{Lu}`,
`\p{Greek}`, `\PL`, `\p{^L}` (the general categories, scripts and Go's
category aliases, Unicode 15.0.0); `* + ? {n} {n,} {n,m}` and their lazy forms
(`*?`); `|`; `(...)`, `(?:...)`, `(?P<name>...)` and `(?<name>...)`; flags
`i m s U` as `(?i)` or `(?i:...)` (and `(?-i)`); `^ $ \A \z \b \B`. Patterns
and texts are UTF-8 and matched by code point; an invalid byte in the text
reads as U+FFFD, one byte wide, which only `.` and negated classes match.
`(?i)` uses Unicode's simple case folding (`k` matches `K` and the Kelvin
sign).

**Refused** (an error, with a hint saying why): backreferences (`\1`),
lookaround (`(?=`, `(?!`, `(?<=`, `(?<!`) and possessive repeats (`a++`):
they are what makes backtracking engines take exponential time, and an
engine with them cannot promise linear time. Also refused as in Go: `\C`,
`\Z`, a repeat count above 1000, nesting deeper than 1000, and a pattern
whose program would be too large, so a pattern cannot exhaust memory.

**Matching.** Per search: the one-pass matcher when the pattern allows it
(anchored, every step one choice); a memory search when the pattern is a
literal; the lazy DFA on texts of 128 bytes or more (states built while
searching in a 2 MB cache; a forward run finds where the match ends, the
reversed pattern run backward where it starts; for the groups the
backtracker or the Pike VM then runs on that span only), with a literal
search to skip ahead (the literals matches start with, a literal inside
the pattern, or one they all end with; without one, the next line when
matches start at line starts); Go's choice otherwise, and when the
DFA's cache fills too often: the bounded backtracker for small programs on
short texts (a visited bitmap: each instruction at each position once), and
the Pike VM (an NFA simulation). The DFA's states live in the call's
matching state, so a `findAll` reuses them but separate calls rebuild them
(a `Searcher` keeps them).
Speed: `PERFORMANCE.md` (via C 1.3 to 2.6 times Rust's `regex` on the
benchmark set, 2 to 650 times faster than Go's `regexp`).

### json

JSON (RFC 8259) values, parsing and writing. Where JSON leaves a choice,
the module follows jq 1.7 (design/json.md).

```lxl
import "json"

let v = try json.parse(`{"name": "lxl", "tags": ["a", "b"], "price": 12.50}`)
v.field("name").asStr()             // Some("lxl"); field of a missing key is null
v.field("price").asDecimal()        // Some(12.50), read from the literal exactly
for t in v.field("tags").items() { ... }
var out = json.object().with("ok", json.boolean(true))
out.set("ids", json.arrayOf([json.integer(1), json.integer(2)]))
out.toStr()                         // {"ok":true,"ids":[1,2]}
json.write(&out, &json.pretty())    // two spaces per level, newline at the end
```

- **Values.** A `Json` is `Null`, `Bool`, `Num`, `Str`, `Arr` or `Obj`.
  Arrays and objects are counted and shared: `clone()` is cheap, and
  changing a shared one copies it first. Readers (`field`, `item`, `items`)
  return owned values; `eachItem`, `eachEntry` and `withItems` lend them.
- **Objects** keep their keys in insertion order. A lookup scans up to 16
  keys; larger objects use a hash index.
- **Numbers** keep their literal text and the nearest double. `asInt` and
  `asDecimal` read the text exactly, and writing gives the text back.
  `cmp` and `eq` compare the texts exactly, so `1.0 == 1` and
  `0.0001e4 == 1`.
- **Strings** are bytes. Invalid UTF-8 and lone low surrogates become
  U+FFFD, as in jq; with `strictUtf8` they are errors.
- **Parsing.**
  - `parse(s)` reads one value.
  - `parseWith(s, options)` takes `maxDepth` (default 512), `strictUtf8`,
    and `lenient` (jq's `nan`, `+1` and the like).
  - `decoder(s).next()` reads a sequence of values.
  - An `Error` has a kind, a message, a byte offset, and the line and
    column.
- **Writing.** `write(&j, &options)` returns the text;
  `writeTo(mut &sink, &j, &options)` streams it. `WriteOptions` has
  `indent`, `tab`, `sortKeys`, `ascii`, `raw` and `jqNumbers`.
- **Order.** `cmp` is jq's total order.

**Tests:** `tests/run/json_*.lxl`, and `tests/jsonsuite.py`, which runs
JSONTestSuite (fetched at test time). **Speed:** `bench/json/bench.py`; the
results are in design/json.md, section 9.

### sqldialect, sqlite, postgres

Database adapters over the C client libraries (a program that imports one is
dynamically linked to libsqlite3.so.0, libpq.so.5 or libodbc.so.2; the tests
that need one are skipped when it is not installed). Examples:
`examples/sqlite_ledger.lxl`, `examples/postgres_ledger.lxl`.

- **sqldialect** (shared): `Value` (`Null Int Float Bool Text Bytes Dec`,
  `toStr` as an SQL literal), `DbError {code, state, msg}` (`"error 19:
  UNIQUE constraint failed: t.id"`, `"error 7 (23505): duplicate key ..."`)
  and the adapters' own codes `E_INPUT E_NULL E_TYPE E_NONFINITE E_INEXACT
  E_DEC_* E_CLOSED E_LIMIT E_CANCELLED E_TIMEOUT E_PROTOCOL E_IO` (1000
  and up, above every SQLite and libpq code); `Sql` fragments (`sql(text)`, `add`, `arg(v)`, `of(parts, args)`,
  `render(dialect)` with `?`, `$n`, `@pn`, `:n` placeholders); `parseDecimal`, `decimalText`,
  `fitDecimal(d, p, s)`.
- **sqlite**: `open(path)`, `openWith(path, flags)`; `Db`: `exec(script)`,
  `prepare(sql)` (one statement), `query(sql, &args)`, `querySql(&sql)`,
  `run(sql, &args)` (rows changed), `changes`, `lastInsertId`,
  `inTransaction`, `transaction(&fn)`, `close()`. `Stmt`: `step(): bool`,
  `reset`, `bind(i, v)`, `bindAll`, `bindDecimal(i, d, p, s)`,
  `columnCount`, `columnName`, and per column `isNull int bool float text
  bytes decimal decimalOrNull value`. Decimals are stored as exact TEXT.
  `step` and `exec` are blocking externs: in a program with other tasks a
  long query parks only its task (each step then pays the pool's round
  trip, 0.4 to 0.8 us, against 30 ns for a step of a cached table; alone, a
  program runs them inline). So they cannot be called inside `Shared.with`.
- **postgres** is native (`pgwire`, no libpq), so a query parks only its
  task: `connect` is `pgwire.parseConfig` and `pgwire.connect` (name lookup
  on the helper pool, PBKDF2 a blocking extern), `query` and `exec` write the
  messages and park the task on the socket. The task's cancellation and its
  `task.within` deadline end a wait: `Err` with `E_CANCELLED` (1020) or
  `E_TIMEOUT` (1021), after a CancelRequest has stopped the query on the
  server and its replies are drained (at most 5 s, not cancellable), so the
  connection is idle again. `connect_timeout` bounds the whole connect
  (`E_TIMEOUT`). A lost connection is `E_IO` and a malformed reply
  `E_PROTOCOL`; the connection is then broken. Every call that can park
  takes a last `w: Where`. The calls take `mut &Conn` (a Lease's `conn()`), as
  `oracle` and `sqlserver` do, and `transaction`'s body gets the connection
  back, `fn(mut &Conn)`.
- **postgres pools**: `newPool(conninfo, size): Result[Pool, Error]` (the
  string is parsed here: E_INPUT), a counted handle (copies reach the same
  pool); `acquire(): Result[Lease, Error]` gives an idle connection, opens
  one while fewer than `size` are open, or parks until a `Lease` is
  dropped (first come first served; cancellation and deadlines give
  `E_CANCELLED` / `E_TIMEOUT` and leave the queue). `Lease.conn()` is the
  connection, a `mut &Conn` (`try l.conn().query(...)`); the Lease gives it
  back when dropped, or closes it when it is not `idle()` (in a
  transaction, broken, a query abandoned): its place goes to the next
  waiter, which opens a new one. An idle connection that went bad, or that
  the server has closed (`net`'s and `tls`'s `quiet()`, a read that never
  parks), is closed at the next acquire and a new one opened, with no
  error for the caller (the same in sqlserver, oracle and redis). `stats(): PoolStats
  {open, idle, waiting}`. These are the shared `pool` module's
  (`pool.Pool[Conn, pgwire.Config, Error]`, design/pool.md): `Conn` is
  `pool.Pooled` (`open`, `waitFailed`, `release`, `reuse`).
  `cmd/httpd.lxl` serves `GET /db` through one.

The ODBC (`mssql`) and libpq (`postgres_libpq`) clients are not library modules.
They live in `lib/tests/support` as the oracles of `sqlserver_live_diff` and
`postgres_live_diff`.

### sqlrows: streams

`sqlserver`, `postgres` and `oracle` read a query a buffer at a time into
the program's own records (design/db-streaming.md; names provisional):

    var src = try conn.stream(sql, [Value.Int(7)], bindOrder, readOrder)   // holds conn (mut &)
    var buf = array(1024, Order{...})
    while true {
        let n = try src.fill(mut &buf)
        if n == 0 { break }
        for o in buf[0..n] { ... }
    }

- **bind**, once: `fn(&Columns): Result[B, Error]` resolves each field to a
  column index, `c.index("customer_id", Kind.Int)` (ASCII case and
  underscores ignored; E_COLUMN for a missing or ambiguous name, listing the
  columns; E_TYPE for a type that cannot be read as the kind) or
  `c.at(i, kind)` by position. Extra columns are never decoded.
- **read**, per row: `fn(&B, &RowView): Result[T, Error]` with `int decimal
  float text bytes bool date timeOfDay localDateTime offsetDateTime` by
  index and their `...OrNull` forms (`Option`). A NULL read without one is
  E_NULL naming the column and the row. Every accessor returns an owned
  value: a record copied out of the buffer can be kept; a borrow of the
  buffer cannot outlive the next `fill` (the checker refuses it).
- `Stream`: `fill(out)` (the count, 0 at the end; rows before an error come
  first, the error from the next call), `next()`, `close()` (SQL Server:
  ATTENTION; PostgreSQL: the rest of the reply is read and discarded (no cancel); Oracle: the cursor closed with the next
  request), `columns()`, `rowsRead()`. A dropped stream is cleaned up by the
  connection's next call. `oracle.Conn.streamWith`; a postgres Lease streams through `conn()`.
- Tests: `sqlserver_live_stream`, `postgres_live_stream`,
  `oracle_live_stream` (skipped without their servers), `sqlserver_fake_stream`
  (a scripted server: packet-spanning rows, ATTENTION, mutated replies), error tests
  `stream_conn_in_use` and `stream_keep_row_borrow`. Timings:
  `python3 lexell/bench/dbstream/run.py`.

### tds, sqlserver

SQL Server over its own protocol, TDS 7.4, written in Lexell from Microsoft's
MS-TDS specification (design/tds.md; stages T1 and T2 of its plan): no driver and no
helper threads. Every call that waits for the server parks only its task on
the socket, as net's calls do, so the task's cancellation and `task.within`
deadlines end it (`E_CANCELLED`, `E_TIMEOUT`). When that happens while the
reply is awaited, the client sends ATTENTION and reads the rest of the reply
in the same task, with I/O that ignores the task's cancellation and deadline,
for `tds.ABORT_MS` (5 s) at most, so the connection is idle again; it is
broken when that fails, or when the request could not be sent whole
(design/pool.md, stage 5). Imports tls, so a program is linked to OpenSSL.

- **sqlserver**: `connect(connStr)` (also `parseConnString(s): Settings`
  and `connectWith(&settings)`): ADO.NET or ODBC keywords, so the ODBC oracle's
  strings work (`Server`/`Data Source` with `tcp:`, `host,port`, `.`,
  `(local)`; `Database`; `UID`/`User Id`; `PWD`; `Encrypt` yes (default:
  TLS for everything) or no (TLS for the login at least) or strict (not
  yet); `TrustServerCertificate`; `HostNameInCertificate`; `Connect
  Timeout` (15 s, the whole connect); `Application Name`; `Packet Size`;
  `Driver` ignored). SQL authentication only; a named instance needs its
  port. Errors name an entry by position, never its text; `masked(s)`
  hides the password. `Conn`: `exec(batch)`, `query(sql, &args)` (the first
  result set with columns, every row read), `run(sql, &args)` (rows
  changed), `queryAll(sql, &args): Results` (every result set, every
  statement's row count in order, a batch's procedure return status),
  `call(sql, &args, &outs)` (queryAll with OUTPUT parameters, `Out{name,
  sqlType}`, back as one row in `Results.outputs`), `querySql(&Sql)`,
  `transaction[T](fn(mut &Conn): Result[T, Error])` (Transaction Manager
  begin; commit on Ok, rollback on Err keeping the body's messages; the
  connection stays usable; not nested), `errors()` (every ERROR of the
  last call: number, state, class, text, server, proc, line; the first is
  the Err), `diagnostics()` (its INFOs: PRINT, RAISERROR at severity 10 or
  less, "Changed database context"), `database`, `language`, `collation`,
  `encryption` ("full", "login only", "off"), `serverVersion`,
  `tdsVersion`, `packetSize`, `inTransaction`, `idle`, `setMaxReply(n)`
  (256 MiB), `close()`. Pools: `newPool(connStr, size): Result[Pool, Error]` (the string parsed then), `acquire()`, `stats()`, `Lease.conn()`: the shared `pool` module's, as postgres's (design/pool.md); a lease broken or in a transaction when dropped is closed; one given back asks for RESETCONNECTION on its next request (the server drops its temporary tables, SET options, `USE` and language; `database()` and `language()` are the login's again), and a stream it left unfinished is ended with ATTENTION when it is acquired again; `resets()` counts the resets. `Rows`: `rowCount`, `columnCount`, `affected`,
  `resultSets`, `columnName`, `columnType` (the TDS code), `columnTypeName`,
  `columnSize`, `decimalType`, and per cell `isNull int bool float text
  bytes decimal decimalOrNull date timeOfDay localDateTime offsetDateTime
  value`. A server error is `Err` with its number as `code` (208, 18456,
  ...) and state `""`; a wire failure is `E_IO` (1023) and breaks the
  connection, a malformed reply is `E_PROTOCOL` (1022).
- Parameters: with `args`, the SQL goes through sp_executesql as `@p1`,
  `@p2`, ... (the text is never interpolated; without args it is a plain
  batch). Int is bigint, Float float (exact; NaN, the infinities and
  subnormals are refused), Bool bit, Text nvarchar(4000) or nvarchar(max)
  beyond 4,000 UTF-16 units, Bytes varbinary(8000) or varbinary(max), Dec
  decimal(p, s) from the value, NULL `NULL_TYPE` (nvarchar(4000): it
  converts to every type but binary ones; write `CONVERT(varbinary(max),
  @p1)`). Dates go in as text. Through sp_executesql the server sends no
  return status for an EXEC inside: write `EXEC @r = p ...` with an Out
  `@r`, or call the procedure by name.
- Procedures by name: `callProc(proc, &args, &tables): Results` is one RPC
  naming the procedure (`dbo.p`, `[my proc]`, `#p`; a name, never SQL),
  with its return status (0 without RETURN), result sets, row counts and
  outputs. `arg(name, v)`, `outArg(name, sqlType)`, `inOutArg(name, v)`
  and `defaultArg(name)` make the `Arg`s; a name of `""` is positional and
  comes before the named ones, which go in any order (the rest take the
  procedure's defaults). An output comes back in the type sent, not the
  procedure's: give `outArg` the procedure's type (a shorter one
  truncates); `inOutArg` sends text and bytes as (max) and a decimal as
  decimal(38, s) at the value's scale.
- Table-valued parameters: `queryTables(sql, &args, &tables): Results`
  (and `callWith(sql, &args, &tables, &outs)`) bind each `Table{name,
  typeName, rows, nullTypes, defaults}` (`table(name, typeName, rows)`
  without null types or defaults) as a READONLY parameter of a user-defined table type (`Items` or
  `dbo.Items`, in the connection's database), beside `@p1`, `@p2`, ... Every
  row has a value for each column of the type, in its order. A column goes
  as the type its values go as as parameters (a decimal widened over its
  rows, Ints in it too; nvarchar(max) or varbinary(max) when one value
  needs it) and the server converts it to the column's. A column of only
  NULLs goes as its `nullTypes` entry, else nvarchar(4000), which a binary
  column refuses (error 257): give it `"varbinary(max)"`. No rows is an
  empty table. Rows of different lengths, a column with two kinds of value
  (but Int and Dec) and a type name that is not one or two regular
  identifiers are `E_INPUT` before anything is sent. `defaults` lists the
  columns (0-based) the server fills: identity and computed columns, which
  refuse a value (error 1077), or a column whose DEFAULT is wanted; their
  values in the rows are NULL and are not sent.
- Bulk copy: `bulkInsert(table, &columns, &rows, &opts): Result[int,
  Error]` loads rows with the BULK_LOAD protocol (bcp's and SqlBulkCopy's):
  `SELECT TOP 0` of the named columns for their nullability (a missing
  table or column is the server's 208 or 207), `INSERT BULK`, then the rows
  in one message, sent a packet at a time as it is encoded. Values go as a
  table parameter's do and the server converts them as an INSERT does;
  text and bytes go as (max) only for a (max) or xml column (longer ones
  for another column are `E_INPUT`), a decimal as decimal(38, s), and a
  column of only NULLs as the column's own kind. Columns left out
  get their DEFAULT, NULL or the next identity value; an identity column
  that is named takes the rows' values. `bulkOptions()` turns off
  `tablock`, `checkConstraints` (without it CHECK and FOREIGN KEY
  constraints are skipped and marked not trusted), `fireTriggers` and
  `keepNulls` (without it a NULL takes the column's DEFAULT). An error
  leaves the connection idle, and a deadline while the reply is awaited
  sends ATTENTION; a failure while the rows are sent breaks it.
- Streamed bulk copy: `bulkStream(table, &columns, &opts, next)` takes the
  rows a batch at a time from `next: fn(): Result[[][]Value, Error]` (no
  rows ends the load) and sends each batch's whole packets before asking
  for the next, so a load of any size needs memory for one batch; it is
  still one load, one message. The first batch fixes the columns' types (a
  decimal's scale is the first batch's most, or the column's scale when
  that is more). A later value its column's type cannot carry (another
  kind, more decimal places, text too long for a column that is not (max))
  or an error from `next` ends the message with IGNORE: the server loads
  none of it (INFO 3621), that error is the result and the connection is
  idle.
- Types: tinyint, smallint, int, bigint, bit, real, float (exact), decimal
  and numeric (`decimal()`, Value.Dec, straight from the wire's sign and
  magnitude), money and smallmoney (scale 4), nchar, nvarchar, ntext and
  (max) through PLP, char/varchar/text (below), binary types as bytes,
  date, time(n), datetime2(n), datetimeoffset(n) (time's `Date`,
  `TimeOfDay`, `LocalDateTime`, `OffsetDateTime`; the offset kept),
  datetime (its 1/300 s ticks rounded to milliseconds as the server's
  CONVERT does: ms = (ticks * 10 + 1) / 3, so .003, .007, .010) and
  smalldatetime, uniqueidentifier (canonical upper-case text from the
  mixed-endian bytes), xml (text). `text()` of any of them is SQL
  Server's and ODBC's text ("2026-11-05 13:45:07.1234567 +01:30", datetime
  ".fff", smalldatetime ":00"); `value()` gives Dec for exact types and
  that Text for civil types and GUIDs. sql_variant, UDTs and the CLR types
  decode to an `E_TYPE` error for that cell only, naming the type; the rest
  of the row reads normally.
- **tds** is the protocol for adapters and tests: `packets`,
  `parseHeader`, `preloginRequest`/`parsePrelogin`, `login7` and
  `scramble`, `sqlBatch`, `executeSql` (an sp_executesql RPC) with
  `Param`s (`intParam`, `floatParam`, `bitParam`, `textParam`,
  `bytesParam`, `decimalParam`, `nullParam(sqlType)`, `typeInfoOf`,
  `tableParam(typeName, &rows, &nullTypes, &defaults)`, `longTextParam`,
  `longBytesParam`, `wideDecimalParam`), `procCall` (an RPC to a procedure
  by name), `bulkColumnsQuery`, `bulkWriter` (`BulkWriter`: INSERT BULK,
  then `add` rows and `end`, onto its unsent bytes) and `bulkLoad` (the
  whole BULK_LOAD message, packet type 7),
  `tmRequest` (begin, commit, rollback), `toUtf16`/`fromUtf16` (strict),
  `guidText`/`guidBytes`, `bitsOfFloat`, `Collation` (`codePage`, `utf8`,
  `describe`), `decode(bytes, maxCells): Reply` (results, every row count,
  return statuses, RETURNVALUEs, errors, infos; every length checked
  before use: a short or hostile reply is `E_PROTOCOL`, never a trap; a
  value whose bytes are framed right but out of range is a `Cell.Failed`),
  `cellText`, `Transport` and `Session` (`open(&Config)`, `batch`,
  `executeSql`, `callProc`, `transact`, `bulkData`, and for a message sent
  in parts `sendPart`, `cancelPart` (an empty last packet with IGNORE),
  `partReply` and `bulkSend`).
  Under TLS each packet goes in its own TLS records: SQL Server drops the
  connection when a record spans two packets.
- varchar, char and text decode by the column's collation: UTF-8 as it is,
  code page 1252 (and ISO-8859-1, for Sybase later) through `codepage`; the
  five bytes cp1252 leaves undefined become U+0081, U+008D, U+008F, U+0090
  and U+009D, as the server converts them (ODBC gives `?`); other code
  pages stay an `E_TYPE` error naming the code page.
- **codepage**: `decode(cp, &bytes): Result[str, str]` (UTF-8 out),
  `encode(cp, &text): Result[str, str]` (the error names the first
  character the code page cannot represent), `supported(cp)`, and the
  constants `WINDOWS_1252` and `ISO_8859_1` (28591). ASCII passes through
  (all-ASCII input is returned as it is); a 128-entry table decodes the
  rest and a binary search encodes. Another single-byte code page is one
  line in `gen_codepages.py` (`python3 -I lexell/lib/gen_codepages.py`).
  Test: `codepage_tables`.
- Tests: `tds_codec`, `tds_codepage`, `tds_table_param`, `tds_proc_call` and `tds_malformed` (bytes only; every
  type from bytes, RPC and TM requests; truncations, mutations, random
  input, fuzzed type names and GUIDs), `sqlserver_connstr`, `sqlserver_fake`
  (a scripted server task: refusal, garbage, timeout, failed login, packet
  size 512, RPCs, transactions, a cut reply), and live
  `sqlserver_live_basic`, `sqlserver_live_tvp` (table parameters: every kind
  of column, the server's conversions and errors, 20,000 rows, a
  procedure, identity, computed and DEFAULT columns), `sqlserver_fake_bulk`
  (the bulk load's three messages byte by byte, an error, a deadline, a
  closed connection), `sqlserver_live_bulk` (every kind of column, each
  option, 50,000 rows, a transaction), `sqlserver_fake_bulk_stream` (a
  streamed load's packets: ids, sizes, EOM only on the last; IGNORE after
  a bad later value, an error from the batch function and before any
  packet), `sqlserver_live_bulk_stream` (200,000 rows in 200 batches; each
  way a load is cancelled loading nothing; the types from the first batch
  and the destination; a transaction), `sqlserver_live_bulk_types`
  (each kind of value into each SQL Server type: what converts),
  `sqlserver_live_proc` (procedures by name: positional, named, DEFAULT,
  OUTPUT and in-out parameters, the output types, a table, errors) and `sqlserver_live_diff` (the same queries,
  parameters, batches and errors through the ODBC oracle and sqlserver, cell by
  cell, and the typed values against the server's CONVERT), which take the
  DSN as the ODBC oracle's live tests do:

      python3 lib/run_tests.py tds_ sqlserver_

### crypto, tns, oracle

Oracle Database over its own protocol (TNS and TTC), a port of the thin mode
of python-oracledb (Apache-2.0 OR UPL-1.0, see NOTICE), read with
node-oracledb's lib/thin (design/oracle.md; stages O1 to O3, O5): no Oracle
client libraries, only libcrypto for the password verifiers. Oracle 12.1 and
later, plain TCP or TLS (`tcps`); every call parks only its task, like
`sqlserver`'s, and the API has the same shape: `oracle.connect(connStr)`
with ODP.NET keywords (`User Id`, `Password`, `Data Source` as Easy Connect
or a descriptor, `Encrypt`, `TrustServerCertificate`, `Server Certificate
Name`, `CA File`, `Connect Timeout`, `Fetch Size`, `Application Name`),
`exec`, `query`/`queryWith`, `run`/`runWith`, `transaction[T]`, `close`,
`logoff`, and pools: `newPool(connStr, size): Result[Pool, Error]` (the string parsed then), `acquire()`, `stats()`, `Lease.conn()`: the shared `pool` module's, as postgres's (design/pool.md); a lease that is not `idle()` when dropped is closed (broken). Outside a transaction every statement commits with its execute
(provisional), so a lease is never dropped inside one. NUMBER is exact (Decimal, or `tns.Num` beyond its range).
A round trip fetches the rows of about 256 KB at the widest row the
columns allow (`Fetch Size` or `setFetchSize(n)`: a fixed count instead),
and a stream sends its next FETCH as soon as a reply's rows arrive
(`setFetchAhead`), so the server makes the next batch while the program
reads the last; `roundTrips()` counts the requests.

`call(sql, args, outs)` (and `callWith` with `Param`s) runs PL/SQL blocks,
procedure and function calls (`begin :r := f(:1); end;`, `CALL p(:x)`) and
DML `RETURNING ... INTO` with OUT and IN OUT binds, like sqlserver's call:
each `oracle.out(name, sqlType)` or `oracle.inOut(name, sqlType, value)`
takes the placeholder of its name, and args fill the others in order.
`Results.outputs` has a column per Out (one row; a row per changed row for
RETURNING), `Results.sets` the rows of each `SYS_REFCURSOR` Out and of each
implicit result (DBMS_SQL.RETURN_RESULT), read whole with their server
cursors closed. Out types are Oracle's with a size where Oracle has one
(`VARCHAR2(100)`, `RAW(16)`, `NUMBER(12,2)`, `TIMESTAMP WITH TIME ZONE`,
`SYS_REFCURSOR`); a value longer than its size is the server's ORA-06502,
never a shortened value (provisional names and sizes: design/oracle.md).

    let r = try conn.call("begin :total := order_total(:1); end;", &[Value.Int(42)],
                          &[oracle.out("total", "NUMBER(12,2)")])
    let total = try r.outputs.decimal(0, 0)

- Tests: `tns_codec` and `oracle_connstr` (no server), and live
  `oracle_live_basic`, `oracle_live_types`, `oracle_live_out`, `oracle_live_stream`,
  `oracle_live_fetch` and `oracle_live_tls`, which read
  the connection string from `ORACLE_TEST_DSN` or `~/.obo-oracle-dsn` (and
  the TLS entries from `ORACLE_TEST_TLS` or `~/.obo-oracle-tls`) and are
  skipped without them. `lexell/tools/oracle_container.sh create` makes the
  Oracle Database Free container and those files, and grants APP the
  session views that `oracle_live_out`'s cursor leak check reads:

      python3 lib/run_tests.py tns_ oracle_

Every getter is exact or an error: no NULL becomes 0 or "" (`E_NULL`; use
`isNull`, `value` or `decimalOrNull`), no REAL becomes an int or a decimal
(`E_INEXACT`), and text is never parsed as a number it does not spell.
Handles (`Db`, `Stmt`, `Conn`, `Rows`) own their C object and free it when
dropped; `close()` consumes the handle, so there is no closed state to
check, and `openHandles()` counts what is live (the tests end at 0). Text
with a NUL byte cannot cross the C boundary and is refused with `E_INPUT`
before any call; bytes travel as a blob (SQLite) or bytea hex (PostgreSQL).

## markdown

CommonMark 0.31.2, written from the spec's own parsing strategy (appendix "A
parsing strategy") and checked against cmark 0.31.2: the HTML is cmark's, byte
for byte, in safe and unsafe mode, with smart punctuation, `data-sourcepos`
attributes, `hardbreaks` and `nobreaks`.

    import "markdown"
    let html = markdown.toHtml("# Hello\n\n*world*\n", markdown.defaults())

    var o = markdown.defaults()
    o.unsafe = true                         // raw HTML and every URL pass through
    o.smart = true                          // curly quotes, dashes, ellipses
    let doc = markdown.parse(src, o)        // the tree
    var w = doc.walker(doc.root())          // enter and exit events, like cmark's iterator
    while w.next(&doc) {
        if w.entering && doc.kind(w.node) == markdown.Kind.Heading { println(doc.level(w.node)) }
    }
    let out = doc.html(o)                   // or render a tree you walked

- **The tree** is one array of `Node` records and a node is an `int` index:
  `doc.root()` is the document, `doc.kind(id)`, `parent`, `firstChild`,
  `lastChild`, `next`, `prev`, `text` (Text, Code, HtmlInline, HtmlBlock,
  CodeBlock), `dest` and `title` (Link, Image), `info` (fenced CodeBlock),
  `level` (Heading), and `doc.at(id)` for the whole `Node` (list `ordered`,
  `start`, `tight`, `delim`; source positions `startLine`, `startCol`,
  `endLine`, `endCol`, which are cmark's, quirks included). Kinds are those of
  cmark: Document, BlockQuote, List, Item, CodeBlock, HtmlBlock, Paragraph,
  Heading, ThematicBreak, Text, SoftBreak, LineBreak, Code, HtmlInline, Emph,
  Strong, Link, Image. Another renderer (a terminal one, say) walks this tree.
- **Linear time.** Nothing recurses: nesting 100,000 deep (block quotes, lists,
  emphasis, brackets) parses and renders, and cmark's pathological inputs run
  in the same time as cmark's.
- **Data.** `markdown_entities.lxl` (the 2,125 HTML5 references that end in
  `;`) and `markdown_unicode.lxl` (Markdown's punctuation, space and full case
  folding) are generated by
  `gen_markdown_data.py` from the WHATWG `entities.json` and Python's
  `unicodedata`; do not edit them.
- **Where it follows cmark rather than the prose of the spec.** Where cmark's
  scanners differ from the spec's text, the module does what cmark does (HTML
  comments, processing instructions and CDATA are cmark's patterns; a title may
  end at a quote that follows a backslash; entities in a destination, title or
  info string are decoded before backslash escapes; `\` followed by a line
  end keeps the next line's leading white space). All of these were found by
  comparing with cmark on generated inputs (`tests/markdown.py`).
- Not in the module: the XML, man, LaTeX and CommonMark writers, and the GitHub
  extensions (tables, strikethrough, task lists, autolinks).

## What the library uses

Intrinsics: `strByte`, `strSlice`, `strFromBytes`, `strToBytes`, `intToStr`,
`i128ToStr`, `u128ToStr`, `u64ToStr`, `floatToStr`, `parseFloat`, `writeFd`,
`readFile`, `args`, `getenv`, `strFromC`, `strFindByte`, `strFindAny`,
`strFind` and `strFindPair` (the first index at or after `from` of a byte,
of any byte of a set, of a string, of a position `p` with `s[p + i1]` in one
set and `s[p + i2]` in another; 16 bytes a step with SSE2, for the regex
prefilters), `appendStr(mut &bytes, s)` (the bytes of `s` at the end of a
`[]byte` in one copy: `StrBuf.add`), and the built-ins `isNull`, `exit`,
`panic`. `task` also uses the library-only intrinsics `intoPtr` and
`fromPtr` (SPEC 15), to keep a task's argument and result and a `Shared`
or `Frozen` value in the runtime's structures.

C functions through `extern "c"`: the math functions std declares (`sqrt cbrt
pow exp exp2 expm1 log log1p log2 log10 sin cos tan asin acos atan atan2 sinh
cosh tanh floor ceil trunc round rint fabs fmod hypot copysign fma`) are the
runtime's own (compiler/lxlmath.inc), not libm's; any other libm function is
libm's, linked dynamically. libc (`strerror close opendir readdir closedir mkdir
rmdir unlink rename symlink chmod setenv unsetenv getpid chdir usleep`), and
these helpers in `compiler/rt.h` for what the language cannot express (a C struct,
errno, a static buffer):

| Helper | Does |
|---|---|
| `lxl_errno()` | `errno` |
| `lxl_dirent_name(d)`, `lxl_dirent_type(d)` | fields of a `struct dirent*` |
| `lxl_stat(path, follow)`, `lxl_stat_field(i)` | stat/lstat into a static buffer, then its fields |
| `lxl_open(path, how)` | open for read, write (truncate), append, or create-new; fd or -errno |
| `lxl_read(fd, b, n)`, `lxl_seek(fd, off, whence)` | `read` and `lseek`: a count or offset, or -errno (in the native runtime, system calls: no libc) |
| `lxl_clock_ns(which)` | `clock_gettime` realtime or monotonic, in ns |
| `lxllib_hash_key(i)` | word `i` (0 or 1) of the 16 `AT_RANDOM` bytes (`getauxval`; the native runtime reads the auxiliary vector); std derives its hash key from them |
| `lxl_getcwd()` | `getcwd` into a static buffer |
| `lxllib_readlink(path)`, `lxllib_readlink_text()` | readlink into a static buffer; length or -errno, then the text |
| `lxllib_flush_out()` | flush the runtime's stdout buffer; errno of the first failed write since the last call, or 0 |
| `lxllib_isatty(fd)`, `lxllib_term_cols(fd)` | `isatty`; `TIOCGWINSZ` columns or 0 |
| `lxllib_alloc(n)`, `lxllib_free(p)` | a zeroed C buffer from the runtime's allocator (counted by `LXL_CHECK=1`); for `ffi` |
| `lxllib_peek(p, i)`, `lxllib_poke(p, i, b)` | read or write byte `i` of C memory; for `ffi` |
| `lxllib_peek_i32`, `lxllib_poke_i32`, `lxllib_peek_ptr`, `lxllib_poke_ptr` | element `i` of a C `int32_t[]` or `void*[]`; for `ffi` |
| `lxllib_copy_in(dst, at, src, n)`, `lxllib_copy_out(dst, src, at, n)` | `memcpy` between C memory and an Lexell byte array; for `ffi` |
| `lxllib_task_scope_open()`, `lxllib_task_scope_close(s, w)` | open a scope; park until its tasks have finished; for `task` (`w`: the caller's `"file:line"`, reported by a trap, here and below) |
| `lxllib_task_start(s, run, job, resdrop)` | a task on a stack from the free list that runs `run(job)`; for `task` |
| `lxllib_task_wait(t, w)`, `lxllib_task_wait_any(ts, n, w)`, `lxllib_task_take(t)` | park until done (0), cancelled (1), abandoned (2) or past the deadline (3); the first done of n (-1 cancelled, -2 deadline); the result box |
| `lxllib_task_forget(t)`, `lxllib_task_join(t, w)`, `lxllib_task_detach(t)` | a dropped future (cancel, drop the result when there is one); cancel and park until finished; `spawn`'s future, given up without cancelling |
| `lxllib_task_yield(w)`, `lxllib_task_cancelled()`, `lxllib_task_check(w)` | yield to the run queue (also polls sockets and timers every 64 calls); whether the running task is cancelled; the checks before an operation that can park: exit 13 inside `with`, then cancelled (1) or past the deadline (3) |
| `lxllib_task_sleep(ms, w)`, `lxllib_task_within(ms)`, `lxllib_task_restore(old)` | park on a timer; set the running task's deadline (the earlier wins), giving the old one; put it back |
| `lxllib_net_listen(fam, addr, port, backlog, reuseport)`, `lxllib_net_connect(fam, addr, port, &pending)`, `lxllib_net_accept(fd)` | non-blocking sockets registered with epoll (edge-triggered, once; a listener at its first wait, with `EPOLLEXCLUSIVE` when the kernel takes it); fd or -errno (`pending`: the connect is in progress) |
| `lxllib_net_read(fd, b, n)`, `lxllib_net_write(fd, b, n)` | `read`, `send` with `MSG_NOSIGNAL`; count or -errno (`-EAGAIN`: park) |
| `lxllib_net_wait(fd, dir, w)` | park until the socket is readable (0) or writable (1): 0, or 1 cancelled, 3 past the deadline, -errno (a listener's registration failed) |
| `lxllib_sig_watch(mask)`, `lxllib_sig_wait(mask, w)` | block the signals of `mask` (bit s-1 for signal s) and read them from a `signalfd` in the epoll set: 0 or -errno; park until one arrives: its number, -1 cancelled, -3 deadline |
| `lxllib_workers_begin(w)`, `lxllib_workers_end()` | the checks before the first fork (exit 15 at `w`), then block `SIGTERM`, `SIGINT`, `SIGCHLD`; drop what is pending and restore the mask |
| `lxllib_proc_fork()`, `lxllib_proc_wait(ms, &status)`, `lxllib_proc_kill(pid, sig)` | flush and fork (the child: a new epoll set, the old mask, `PR_SET_PDEATHSIG`); the supervisor's wait: a child's pid (`status`: its wait status), `-sig` for `SIGTERM`/`SIGINT` (`status`: the sender's pid) or 0 after `ms`; `kill` |
| `lxllib_proc_spawn(blob, argc, envc, modes, &out)` | fork and exec a program (`proc`): PATH lookup, redirections, pipes (non-blocking, in the epoll set), environment, directory and the exec errno through a close-on-exec pipe all in the parent or by raw syscalls in the child; the pid or -errno; `out`: the pidfd (-1: none) and the parent's pipe ends |
| `lxllib_proc_write(fd, b, n)`, `lxllib_proc_reap(pid, block, &status)`, `lxllib_proc_nap(ms)` | a pipe write with SIGPIPE blocked and taken back (EPIPE); `wait4` (`block` 0: WNOHANG) with EINTR retried; a thread sleep (no-pidfd kernels, after a cancellation) |
| `lxllib_worker_exit(code)`, `lxllib_worker_stop()` | a worker's end (flush; under `LXL_CHECK=1` its leak check); `SIGTERM` to the supervisor, -1 when not a worker |
| `lxllib_fd_wait(fd, dir, ms, cancellable, w)` | park until a descriptor a C library reads itself (libpq's socket) is readable (0), writable (1) or either (2): armed one-shot in the epoll set each time; ends at cancellation and the deadline when `cancellable`, after `ms` when `ms >= 0`; 0, 1 cancelled, 3 deadline or `ms`, -errno |
| `lxllib_net_addr(fd, peer, out)`, `lxllib_net_nodelay(fd, on)`, `lxllib_net_soerror(fd)`, `lxllib_net_shutdown(fd, how)`, `lxllib_net_close(fd)` | the local or peer address (family, port, 16 address bytes); `TCP_NODELAY`; `SO_ERROR`; `shutdown`; close (and forget the fd's waiters) |
| `lxllib_task_promise(resdrop)`, `lxllib_task_complete(t, r)`, `lxllib_task_abandon(t)` | promises |
| `lxllib_sh_new(box, drop)`, `lxllib_sh_enter(s, w)`, `lxllib_sh_leave(s, box)` | a `Shared` block; lend its box to `with` (exit 13 when already lent; `w` is kept for the messages while the `with` is open) and take it back. A `Frozen` is such a block that is never entered: `read` lends the box directly |

The `lxllib_` helpers are not `lxl_` names because the compiler lets
externs name only the `lxl_` helpers it knows (sema's `cHelper`); any other
name defined in both runtimes works. The native backend always links the
`lxl_` and `lxllib_` names to its own runtime, also in a dynamically linked
program; any other C name comes from the program's libraries.

The self-hosted compiler's runtime needs the same helpers (or the language a
way to read C structs).

## Slices

The algorithms that do not grow or shrink an array take a slice (SPEC 4.2a),
so they also work on part of one; `&xs` / `mut &xs` still pass the whole
array:

- collections: `sort` (and its `siftDown`), `sortBy`, `sortStable`, `isSorted`, `binarySearch`,
  `lowerBound`, `upperBound`, `contains`, `find`, `findBy`, `count`, `any`, `all`, `equal`,
  `reverse`, `rotateLeft` (which reverses subslices), `copyOf` (`copyRange(xs,
  a, b)` is `copyOf(xs[a..b])`), `extend` (its `ys`), `filter`, `mapTo`,
  `setOf`.
- decimal: `sumDecimals`.
- money: `allocateBy` (weights), `sum`.
- strings: `join`, `fromRunes`.

Functions that append, pop or insert (`insert`, `removeAt`, `swapRemove`,
`retain`, `dedup`, `extend`'s `xs`) keep `mut &[]T`.

`s[a..b]` on a str shares its bytes, so taking substrings costs no copy;
`strSlice(s, a, b)` is the same operation. `Decimal.parse(text[a..b])` parses
part of a larger text without copying it. No library code relies on a str
being NUL-terminated: an extern call gets the str's bytes when a NUL follows
them and a NUL-terminated temporary copy otherwise (freed after the call).

## Gaps

- No traps carry a source position: a Decimal or Money stop prints `Lexell:
  <message>` and exits 10 from inside the library.
- `float` has no `hash` (and so cannot be a Map key).
- `fixed` and `toDecimal` work from the shortest decimal form of a float, not
  its exact binary value (deliberate, but unlike C's printf).
- `fs.list` has no error for a failure in the middle of `readdir`; `Stat` has
  no atime/ctime fields (the helper can read them, but adding the fields
  changes the compiler's seed); no `chown` or `utimes`.
- `time` has civil formatting/parsing but no zone rules; time zones are in
  `tz`. `%z` formatting is `+0000`; `strftime` takes a `%Z` label, not a zone.
- `strings` case mapping is ASCII only and named `toUpperAscii`/`toLowerAscii`/
  `equalFoldAscii`. `unicode` has the simple lower/upper mappings and simple
  fold, but not full (multi-code-point) case folding; that is exposed only to
  Markdown for link labels.
- `cli` is the eza/obo grammar, not GNU getopt: no unique long-prefix
  matching, and the caller formats the messages.
- `glob` is Unix/bash-shaped; zoxide's Rust-crate matcher is local to `cmd/`,
  and grep's GNU byte matcher stays in grep.
- No general `html`/`csv`/`sh` module: jq and cmark keep their call-site
  escaping, and `base64` is the only shared encoding module.
- `regex`: no Unicode blocks, full case folding, `RegexSet` or
  byte-oriented matching (R3).
- No `Deque`, no `BTreeMap`/ordered map; `Set` iterates in insertion order
  until a remove.
- Errors are errno ints in `os` (setEnv, setCwd) but `IoError` in `io` and
  `fs`.
- `sqlserver` (design/tds.md): no sql_variant or UDTs; table parameters
  not streamed (`stream` takes none) and built whole in memory, as a bulk
  load's rows are (one message per call; call it again for the next
  batch); parameters only of Value's variants (dates as text,
  a NULL typed nvarchar); varchar only in UTF-8 collations and code pages
  1252 and 28591 (another code page is an error for that cell); a call
  cancelled while its request is still being sent breaks the connection
  (part of a packet may have gone); no routing (Azure
  redirects), Encrypt=strict and integrated
  authentication not supported.
- the ODBC oracle (`mssql`): no MARS (one open result per connection), no output or
  table-valued parameters, no bulk copy, no streaming of a long value (it
  is read whole, up to maxValue); a NULL parameter costs a server round trip
  (SQLDescribeParam) to learn its type; date and time columns are text, not
  `time` values.
