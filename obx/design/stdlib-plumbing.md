# stdlib plumbing: CLI, paths, formatting and the small missing modules

Status: planned 2026-11-08. This note is the contract for the work that
follows the audit of `obx/cmd` and `obx/lib/examples`. The goal is to move
the helpers that several example programs now carry inline into the library,
and to fill the small gaps those programs expose. The heavy modules (regex,
json, markdown, http, the database stack) are out of scope.

The predecessor, `archive/obo/`, already had most of this layer:
`lib/cli.obx`, `lib/fmt.obx`, `lib/paths.obx`, `lib/env.obx`,
`lib/html.obx` and `lib/errors.obx`, with tests in
`archive/obo/tests/stdlib/`. That code is a reference and a test corpus,
not a source to copy: obo uses `ref record`, `Result[T]`, `?T`, `module`
and `string`, and obx uses value records, `Result[T, E]`, `Option`, `pub`
and `str`. Every port is reworked for the obx ownership and borrow rules.

## Non-goals

- No compiler, runtime or seed changes. Every module is ordinary obx code.
- No new C dependency. Base64 moves out of `crypto`; it does not add one.
- No example changes until the library is integrated and frozen.
- No general `printf`: the language has no variadic heterogeneous
  arguments. Formatting is a builder API.
- No HTML template engine. Only escaping and URL validation.

## Module contracts

The exact signatures may move a little during implementation, but the
semantics below are fixed. A module may not print, exit or write to a file
unless the contract says so.

### fmt

Port `archive/obo/lib/fmt.obx` (122 lines). Non-negative decimals and
eza's permission form.

- `digits(n: int): int` - decimal width, `digits(0) == 1`.
- `appendPadded(mut buf: &[]byte, n: int, width: int)` - right-aligned.
- `writePadded(w: mut &io.Writer, n: int, width: int)` - through a Writer.
- `modeString(mode: int): str` - eza's 10-character permission form.
- `intWidth(n: int): int` is allowed if `eza`/`wc` need it; otherwise omit.

`strings.padLeft` remains the string primitive; `fmt` is the number and
writer layer. The two must not grow duplicate width logic.

### paths

Port `archive/obo/lib/paths.obx` (133 lines). Lexical only: no filesystem,
no `~`, no glob, no shell.

- `isAbsolute(p: str): bool`
- `hasTrailingSlash(p: str): bool`
- `isDotName(p: str): bool`
- `lastComponent(p: str): str`
- `parentOf(p: str): str`
- `join(a: str, b: str): str`
- `ext(p: str): str` - the extension without its dot, as Rust
  `Path::extension`; `fs.extension` keeps its dot and keeps its name.

The component semantics are Rust's `Path::components`, as obo verified
against rustc 1.87. `realpath`, `clean` and `abs` are **not** here:
`realpath` belongs in `fs` (it needs the filesystem), and `clean`/`abs` are
a later lexical addition. `fs.join` may delegate to `paths.join`.

### cli

Port the grammar of `archive/obo/lib/cli.obx` (411 lines), not its eza
message text.

- `Spec { short: byte; long: str; arity: Arity; consume: []str; accept: []str; choices: []str; default: str }`.
  `short` is 0 for no short form. `consume` lists the next-token values an
  `Optional` may consume; `accept` is the allowed value set (empty = any);
  `choices` is help/error text only; `default` is the value of a bare
  `Optional`.
- `Arity` = `Flag`, `Value`, `Optional` (closed variant or equivalent).
- `Command { opts: []Opt; operands: []str }`
- `Opt { short: byte; long: str; value: str; hasValue: bool }`. `value` is
  the effective value; `hasValue` is true when a value is effective
  (including a non-empty default).
- `parse(args: &[str], from: int, specs: &[Spec]): Result[Command, Error]`
- `Error` carries structured fields (kind, token, option, value) and a
  generic `code` if useful; it never prints. A caller formats the message
  and chooses the exit code. Value validation runs after the whole token
  walk, as eza does: a later syntax error wins over an earlier bad value.

Grammar requirements, from obo's design 5.6:

- options and operands may interleave; `--` ends option parsing; a lone
  `-` and `""` are operands;
- `--name`, `--name=value`; split at the first `=` only when the name is
  non-empty and at least one byte follows;
- short clusters, attached values, optional values only when in the
  `consume` set; a `Flag` with a split value is an error;
- `Value` consumes the next token; `Optional` uses the `default` when no
  value is consumed;
- no printing, no `exit`, no eza-specific wording.

### unicode

New module. Reuse the generated data in `regex_unicode.obx` and
`markdown_unicode.obx`; do not add a third table.

Priority is what the examples actually call:
- `lower(r: int): int` / `fold(r: int): int` for simple case folding.
- `isLetter`, `isDigit`, `isSpace`, `isUpper`, `isLower`, `isPunct`.
- `category(r: int): str` or a closed `Category` type if the caller needs
  more than the predicates.
- `upper(r: int): int` only if a non-ASCII caller appears. eza's current
  `strings.toUpper` use is ASCII; do not build a full uppercase table
  without a caller.

`regex_unicode.inClass`/`simpleFold` and `markdown_unicode.SPACE`/`PUNCT`/
`FOLD_*` already carry the data. Importing both large modules is a binary
size risk; prefer the smaller dependency or one shared generated module if
the integration review agrees. `strings.toLower` stays ASCII: no example needs full Unicode lowercasing,
and importing `unicode` into `strings` would pull the fold tables (about
135 KB) into every program that only lowercases an extension. Callers that
need full lowercasing use `unicode.lower` directly. `strings.naturalCompare`
may keep eza's documented partial folding if that is what the eza goldens
pin; the difference must be explicit.

### strings

Extend `lib/strings.obx`; port from `archive/obo/lib/strings.obx`.

- `naturalCompare(a: str, b: str): int` and `naturalCompareFold`
- `quoteName(name: str, quoteSpaces: bool): str`
- `parentPrefix(parent: str, quoteSpaces: bool): str`
- `isPrint`, `isBlank`, `isWordByte`
- `utf8Error(s: str): Option[str]` (Rust's message for the first invalid
  sequence, with its byte index) if zoxide still needs it after the port.

`quoteName`/`parentPrefix` are byte-wise; they do not validate UTF-8.
`naturalCompare` must preserve the obo test vectors and the documented
Unicode limitation unless we deliberately change eza output.

### errors

New small module; do not duplicate `io.errorText`.

- `debugPath(p: str): str` - Rust `Path`/`OsStr` debug quoting.
- `osError(errno: int): str` - `io.errorText(errno)` plus
  `" (os error N)"`.

`io.errorText` remains the one errno-text source. If a tool needs pinned
English text, that is a separate decision; do not create a second errno
table by accident.

### io

Extend `lib/io.obx`; obo's `fill`/`takeChunk`/`pump`/`count` are the
reference, but the obx buffer model stays.

- `ChunkReader { src: Reader; buf: []byte; n: int; pos: int }` or the
  smallest equivalent that lets a caller see `buf[0..n]`.
  - `fill(): int` - bytes read, 0 at EOF, negative errno.
- `copy(dst: mut &Writer, src: mut &Reader): Result[int, IoError]`
- `count(src: mut &Reader): Result[int, IoError]`
- `readAll(src: mut &Reader): Result[str, IoError]`

Avoid per-byte allocation. One chunk-sized `strFromBytes` conversion per
chunk is acceptable; the goal is that five programs can drop their private
`Reader` wrappers without a performance regression.

### fs

Extend `lib/fs.obx`.

- `walk(root: str, followLinks: bool, visit: &fn(path: str, e: Entry): bool): Result[Unit, io.IoError]`
  or a small `WalkOptions` record if the callback needs skip-dir and
  on-error. No symlink loops; a cycle is an error or a skip, documented.
- `createTemp(dir: str, prefix: str): Result[io.Writer, io.IoError]` -
  `O_EXCL`, 0600 (the runtime opens 0666 & umask, so chmod after open),
  random suffix.
- `writeAtomic(path: str, data: str): Result[Unit, io.IoError]` - temp in
  the same directory, write, rename; remove the temp on failure.
- `realpath(path: str): Result[str, io.IoError>` - symlink resolution with
  a loop limit (ELOOP = 40).
- `Stat` gains `atime` and `ctime` (seconds; the runtime helper exposes
  those two but not their nanoseconds). Keep the existing fields; add the
  new ones at the end of the record.

### os

Extend `lib/os.obx`.

- `Env { name: str; value: str }`; `environ(): []Env` in process order.
- `uid(): int`, `gid(): int` for the real ids; `effectiveUid`,
  `effectiveGid` if a caller needs them. Name the functions so the caller
  chooses.
- `User { uid: int; gid: int; name: str; home: str; shell: str }`
- `userById(uid: int): Option[User]`, `userByName(name: str): Option[User]`,
  `users(): []User`
- `tempDir(): str` - `$TMPDIR` when absolute, else `/tmp`.
- `dataDir(app: str)`, `configDir(app: str)`, `cacheDir(app: str)` only if
  a caller needs them; zoxide is the likely first.

### time

Extend `lib/time.obx`. The engine already exists in `cmd/jq_lib.obx`
(gmtime, timegm, strftime, strptime, ISO week); move the generic part.

The design review is right that the engine is `Tm`-shaped, not
`LocalDateTime`-shaped: jq needs 0-based `mon`, `wday`, `yday`, `fsec`,
sentinel values for unset fields, and an unconsumed suffix from `strptime`.
So the library interface is:

- `Tm { year (since 1900), mon (0..11), mday, hour, min, sec, wday, yday,
  fsec }`
- `gmtimeOf(sec: int): Tm`, `timegm(t: &Tm): int`, `isoWeek(t: &Tm): ...`
- `strftime(t: &Tm, fmt: str, zoneName: str): str`
- `strptime(s: str, fmt: str): Result[Strptime, str>` with
  `Strptime { tm: Tm; rest: int }` (or a documented equivalent)
- `tmOf(l: LocalDateTime): Tm`, `localDateTimeOf(t: &Tm):
  Result[LocalDateTime, str]` as adapters
- `httpDate(sec: int): str` - RFC 7231 IMF-fixdate, GMT
- `strftimeOffset(t: OffsetDateTime, fmt: str, zoneName: str): str` only
  if a caller needs a real `%z`; `tz.Zone` cannot be imported by `time`
  (tz imports time).

Keep jq's JSON-array conversion and jq's exact error text in `jq_lib`.
The token set must cover what jq, eza and the access log use. Unknown
tokens pass through as `%X`, as jq does, unless we choose to reject them.
`zoneName` is a `%Z` label; `%z` must be documented as `+0000` unless an
offset-taking variant is used.

### binary and math bits

New `binary` module; extend `math`.

The design review found the unsigned-only contract too narrow. The codecs
need signed reads, `&str` sources, in-place setters, and `StrBuf` writers.

- Reads: `readU16/32/64LE/BE` and signed `readI16/32/64LE/BE`; signed
  values are sign-extended, `readI64` may return the raw int bit pattern.
  Bounds are documented (callers validate wire lengths; an out-of-range
  index traps).
- `&str` variants for the hot wire paths (`readU32BEStr`, `readU16LEStr`,
  `readU64LEStr`, ...).
- Append: `appendU16/32/64LE/BE(mut b: &[]byte, v: int)`.
- In-place: `setU16/32LE/BE(mut b: &[]byte, at: int, v: int)`.
- StrBuf: `addU16/32/64LE/BE(mut b: &StrBuf, v: int)` using `addByte`.
- `math.bitsOf(x: float): int` and `math.fromBits(b: int): float` - the
  exact double bit pattern as a 64-bit signed int; `u64` is not usable
  because `u64(-1)` traps and the DB codecs already carry signed bits.
  32-bit `bitsOf32`/`fromBits32` for the `real`/`float` codecs.

The existing `mssql`, `pgwire`, `tds`, `tns` and `tz` helpers migrate one
codec at a time under their differential wire tests; do not keep two endian
implementations after the migration.

### glob

New module for zoxide's Rust-glob syntax. The design review is right that
grep's GNU matcher is a different language: byte-wise, C-locale, `* ? [] \`,
and matching a suffix after `/`. Keep grep's 60-line matcher in grep unless
a second GNU-style caller appears.

- `compile(pattern: str): Result[Pattern, Error]`
- `Pattern.matches(name: &str): bool`
- Rust-glob rules: `*` does not cross `/`, `**` as a whole component does,
  `?`, `[abc]`, `[!abc]`, escapes; decode to code points.
- No exponential backtracking: an iterative/DP matcher or a compiled token
  list. `zoxide`'s `_ZO_EXCLUDE_DIRS` and the `glob` test corpus are the
  oracle.

### html and base64

New small modules. The design review narrowed these to the real callers.

- `html.escapeText(s: str): str` - `& < > \" '` and ASCII controls, as
  obo/jq do.
- `html.escapeAttr(s: str): str` - the same plus tab/LF/CR as numeric
  references, both quote characters escaped.
- Do **not** add `html.validateUrl` as a general HTML primitive: jq does
  not use it, and cmark's `safeHref` allows relative/mailto/ftp and image
  data URLs, which is a markdown policy, not an HTML one. If a scheme
  check is needed, put it in `markdown` or use `url.parse` plus a caller
  policy.
- `base64.encode(s: str): str` shared.
- Two decoders, because the callers differ: `base64.decodeStrict` (padded,
  whole groups of four, as `crypto.unbase64`/pgwire) and
  `base64.decodeLenient` (jq's `@base64d`: stops at `=`, accepts unpadded,
  rejects a single trailing byte). Keep `crypto.base64` as the strict
  codec or delegate to `base64`.

`csv` and `sh` quoting stay in `jq_lib` until a second caller appears.

## Workstreams and file ownership

| Workstream | Files | Reference |
|---|---|---|
| fmt | `lib/fmt.obx`, `lib/tests/run/fmt_*.obx` | obo fmt |
| paths | `lib/paths.obx`, `lib/tests/run/paths_*.obx` | obo paths |
| cli | `lib/cli.obx`, `lib/tests/run/cli_*.obx` | obo cli |
| unicode | `lib/unicode.obx`, `lib/tests/run/unicode_*.obx` | generated tables |
| strings | `lib/strings.obx`, `lib/tests/run/strings_*.obx` | obo strings |
| errors | `lib/errors.obx`, `lib/tests/run/errors_*.obx` | obo errors |
| io | `lib/io.obx`, `lib/tests/run/io_*.obx` | obo io design |
| fs | `lib/fs.obx`, `lib/tests/run/fs_*.obx` | new |
| os | `lib/os.obx`, `lib/tests/run/os_*.obx` | new |
| time | `lib/time.obx`, `lib/tests/run/time_*.obx` | jq_lib |
| binary | `lib/binary.obx`, `lib/math.obx`, tests | zoxide/DB |
| glob | `lib/glob.obx`, tests | grep/zoxide |
| html/base64 | `lib/html.obx`, `lib/base64.obx`, tests | obo html/crypto |

No agent edits another workstream's file. `lib/README.md`, `cmd/README.md`
and `HISTORY.md` are updated by the integrator after the freeze.

## Dependency order

1. fmt, paths, io, unicode (independent; io before fs).
2. strings (needs unicode), cli, os, time.
3. fs (needs paths/io), binary (needs math), glob (needs strings/unicode),
   html/base64 (needs strings).
4. Integration and freeze.
5. Examples.

## Tests

- Module unit tests: `lib/tests/run/<module>_*.obx`, in the conformance
  format (`// expect:`), run with `OBX_CHECK=1`.
- Ported vectors: `archive/obo/tests/stdlib/{cli_parse,cli_errors,
  cli_helpers,paths_table,fmt_basic,strings_natcmp,strings_quote,
  errors_basic}.obx`.
- Example oracles:
  - `python3 obx/cmd/tools_gate.py -j 8` and `--memory` (coreutils, grep)
  - `python3 obx/cmd/eza_gate.py -j 8`
  - `python3 obx/tests/jq.py --ref <jq> -j 8` and `--jqtest`
  - `python3 obx/tests/zoxide.py --ref <zoxide> -j 8`
  - `python3 obx/tests/markdown.py -j 8 --ref <cmark>`
  - `python3 obx/cmd/http_gate.py`, `python3 obx/cmd/tls_bench.py`
  - `python3 obx/lib/run_tests.py -j 8`
  - `bash obx/tools/gate.sh quick` and `full`
- A module is not done until its tests pass, the library suite passes, and
  a scratch example using it builds and runs.

## Example migration map

| Example | Modules |
|---|---|
| cat, wc, head, tail, sort | `fmt`, `io` |
| grep | `io`, `glob`, `strings` |
| eza | `cli`, `paths`, `fmt`, `strings`, `errors`, `os`, `fs` |
| zoxide | `paths`, `glob`, `binary`, `os`, `fs`, `strings` |
| jq | `time`, `html`, `base64`, `url.encode`, `math` |
| httpd, httpload, tlsbench | `http`, `time`, `os`, `fs` |
| cmark, DB examples | `cli`/`os` only where it removes code |

Coreutils and grep are the canary. If `io` regresses throughput or memory,
stop and fix it before eza/jq.
