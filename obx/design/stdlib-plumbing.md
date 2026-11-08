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
- `extension(p: str): str`

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

- `lower(r: int): int`, `upper(r: int): int` (simple mappings; document
  multi-character expansions if they are not handled)
- `isLetter`, `isDigit`, `isSpace`, `isUpper`, `isLower`, `isPunct`
- `category(r: int): str` or a closed `Category` type if the caller needs
  more than the predicates.

`strings.toLower`/`toUpper` delegate to `unicode`. `strings.naturalCompare`
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
  `O_EXCL`, mode 0600, random suffix.
- `writeAtomic(path: str, data: str): Result[Unit, io.IoError]` - temp in
  the same directory, write, rename; remove the temp on failure.
- `realpath(path: str): Result[str, io.IoError>` - symlink resolution with
  a loop limit (ELOOP = 40).
- `Stat` gains `atime`, `atimeNs`, `ctime`, `ctimeNs` (the runtime helper
  already has them); keep the existing fields and ABI.

### os

Extend `lib/os.obx`.

- `environ(): []Env` or `[]str` of `NAME=VALUE`, in process order.
- `uid(): int`, `gid(): int` (real and effective if they differ; name the
  fields so the caller chooses).
- `User { uid, gid, name, home, shell }`
- `userById(uid: int): Option[User]`, `userByName(name: str): Option[User]`,
  `users(): []User`
- `tempDir(): str` - `$TMPDIR` when absolute, else `/tmp`.
- `dataDir(app: str)`, `configDir(app: str)`, `cacheDir(app: str)` only if
  a caller needs them; zoxide is the likely first.

### time

Extend `lib/time.obx`. The engine already exists in `cmd/jq_lib.obx`
(gmtime, timegm, strftime, strptime, ISO week); move the generic part.

- `strftime(t: LocalDateTime, fmt: str, zone: str): str`
- `strptime(s: str, fmt: str): Result[LocalDateTime, str]`
- `httpDate(sec: int): str` - RFC 7231 IMF-fixdate, GMT.
- A `Tm` view is allowed if jq needs the C `struct tm` fields; keep it in
  `time`, not in `jq_lib`.

The token set must cover what jq, eza and the access log use: `%Y %m %d %e
%H %k %I %l %M %S %j %a %A %b %B %p %P %Z %z %u %w %y %C %D %F %T %R %r %c
%x %X %s %n %t %G %g %V %U %W %%`. Unknown tokens pass through as `%X`, as
jq does, unless we choose to reject them.

### binary and math bits

New `binary` module; extend `math`.

- `readU16LE/BE`, `readU32LE/BE`, `readU64LE/BE` (index into `&[byte]`,
  bounds-checked or documented).
- `appendU16LE/BE`, `appendU32LE/BE`, `appendU64LE/BE` (into `[]byte` or
  `StrBuf`).
- `math.bitsOf(x: float): u64`, `math.fromBits(b: u64): float`; 32-bit
  variants if the DB codecs need them.

The existing `mssql`, `pgwire`, `tds`, `tns` and `tz` helpers migrate to
these; do not keep two endian implementations.

### glob

New module. `grep`'s GNU matcher and `zoxide`'s Rust glob are the sources.

- `compile(pattern: str): Result[Pattern, Error]`
- `Pattern.matches(name: &str): bool`
- Options for pathname separators and `**`; default to the caller's syntax.

No exponential backtracking: an iterative/DP matcher or a compiled token
list. `grep` needs `* ? [] \`; `zoxide` needs `**` and path components.
One module, two modes, one test corpus.

### html and base64

New small modules.

- `html.escapeText(s: str): str`, `html.escapeAttr(s: str): str`,
  `html.validateUrl(s: str): Result[str, str]` (http/https only, no
  `javascript:`/`data:`).
- `base64.encode(s: str): str`, `base64.decode(s: str): Option[str]` or
  `Result`. Move the pure functions out of `crypto`; update `pgwire` and
  keep `crypto.base64` as a thin wrapper for compatibility if needed.

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
