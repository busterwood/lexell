# YAML for Lexell

Status: design & implementation, 2026-11-26 (branch `feat/yaml`). The library
is `lib/yaml.lxl`, tested by `lib/tests/run/yaml_*.lxl` and
`tests/yamlsuite.py`. No language change is needed.

## 0. Goal

`import "yaml"` reads, decodes, edits and writes YAML 1.2 (Core Schema), with
comment and style preservation for round-trip formatting, multi-document
streams, anchors/aliases and opt-out merge keys (`<<`).

Unlike `lib/json.lxl` — which was co-designed for `cmd/jq` (single-document
forgiving `.field()` chains with no source positions) — YAML in Lexell is
primarily used for **hand-edited configuration files, manifests and structured
tooling** in a language with no reflection or derive macros. The API therefore
centers on:

1. **A comment- and span-preserving `Node` tree** with copy-on-write `rc`
   containers (so cloning and aliases are O(1), and editing one key preserves
   key order, styles and comments).
2. **Borrow-class typed decoders (`MapDecoder` / `SeqDecoder`)** returning
   `Result[T, Error]` with YAML path and `line:col`, including `finish()` to
   reject unknown/misspelled keys.
3. **Exact `Decimal` and `time` integration**, a pull-based `Event` stream,
   streaming `Sink` writing, and a `json.Json` bridge (`toJson` / `fromJson`).

```lxl
import "yaml"

type Server = record { host: str; port: int; rate: Decimal; tags: []str }

fn decodeServer(n: &yaml.Node): Result[Server, yaml.Error] {
    var m = try n.map()
    let host = try m.reqStr("host")
    let port = try m.optInt("port", 8080)
    let rate = try m.optDecimal("rate", 1.00m)
    let tags = try m.optSeq("tags", yaml.decodeStr)
    try m.finish()
    return Ok(Server{host: host, port: port, rate: rate, tags: tags})
}

// Round-trip edit preserving comments and formatting:
var doc = try yaml.parse(src)
doc.set("port", yaml.integer(9090))         // keeps key order and inline comment
let out = yaml.write(&doc, &yaml.writeDefaults())
```

## 1. Data model: `Node`, `Value`, `Comments`, `Span`

```lxl
pub type Span = value record { pub line: int; pub col: int; pub offset: int }

pub type Style = value closed {
    Any; Plain; Single; Double; Literal; Folded; Block; Flow
}

pub type Comments = value record {
    pub head: str         // comment lines before the node (with leading '#')
    pub line: str         // inline comment on the same line (with leading '#')
    pub foot: str         // trailing comment lines after the node / container
    pub blankBefore: bool // a blank line preceded this node or its head comment
}

pub type Number = value record {
    pub isFloat: bool     // false for !!int, true for !!float
    pub i: int            // exact int64 when !isFloat && hasInt
    pub hasInt: bool
    pub f: float          // nearest IEEE 754 double (or inf/nan)
    pub text: str         // original literal text ("0x10", "12.50", ".inf", or "")
}

pub type Entry = value record { pub key: Node; pub value: Node }

pub type Value = value closed {
    Null
    Bool(bool)
    Num(Number)
    Str(str)
    Seq(rc SeqBox)
    Map(rc MapBox)
}

pub type Node = value record {
    pub value: Value
    pub span: Span
    pub tag: str
    pub anchor: str
    pub style: Style
    pub comments: Comments
}
```

- **Shared copy-on-write containers.** `SeqBox` and `MapBox` live behind `rc`,
  as in `json.lxl`. `clone()` shares them in O(1); mutations (`set`, `remove`,
  `push`, `setAt`, `pop`) call `unshare()`.
- **Arbitrary YAML keys, fast string lookup.** `MapBox` stores `entries: []Entry`
  in insertion order. Small mappings (`<= 16` entries) scan linearly; larger
  mappings maintain an open-addressing hash index keyed by `Node.hash()`
  (SipHash for strings, semantic hashing for all other values).
- **Semantic equality.** `Node.eq(&other)` and `Node.hash()` compare values
  semantically, ignoring `span`, `style`, `anchor` and `comments`.
- **Comment-preserving updates.** `n.set(key, val)` keeps the existing key's
  position, style and comments; if the new `val` has no `line` comment of its
  own, the old value's `line` comment is preserved (`port: 8080 # HTTP` updated
  to `9090` stays `port: 9090 # HTTP`).

## 2. YAML 1.2 Core Schema, numbers and types

Only **plain, untagged scalars** undergo implicit tag resolution, following the
YAML 1.2 Core Schema (section 10.3.2):

| Kind | Plain forms |
|---|---|
| `Null` | empty, `null`, `Null`, `NULL`, `~` |
| `Bool` | `true`, `True`, `TRUE`, `false`, `False`, `FALSE` |
| `Int` | `[-+]?[0-9]+`, `0o[0-7]+`, `0x[0-9a-fA-F]+` |
| `Float` | `[-+]?(\.[0-9]+ \| [0-9]+(\.[0-9]*)?)([eE][-+]?[0-9]+)?`, `[-+]?(\.inf \| \.Inf \| \.INF)`, `(\.nan \| \.NaN \| \.NAN)` |
| `Str` | everything else |

- YAML 1.1 legacy booleans (`yes`/`no`/`on`/`off`), legacy octals (`010`), and
  sexagesimals (`1:30`) remain strings.
- Quoted (`"123"`, `'true'`) and block (`|`, `>`) scalars are always `Str`
  unless explicitly tagged (`!!int "42"`, `!!bool "true"`, `!!float "1.5"`,
  `!!null ""`).
- `Number` preserves the original literal text, so `0xFF`, `0o755`, `12.50` and
  `.inf` round-trip verbatim, `asInt()` is exact for `!!int`, `asFloat()`
  widens `!!int` and `!!float`, and `asDecimal()` reads exact base-10 decimals
  for financial configs.
- Dates and binary data are decoded on demand (`asDate()`, `asLocalDateTime()`,
  `asOffsetDateTime()`, `asBinary()`) using `time.lxl` and `base64.lxl`, rather
  than silently converting strings at parse time.

## 3. Anchors, aliases, merge keys and limits

- **Anchors & aliases (`&name`, `*name`):** Resolved per document. Resolving an
  alias shares its `rc` box (or copies scalars). Cyclic aliases (referencing an
  anchor whose container is still open) are rejected with `ErrorKind.CyclicAlias`.
- **Billion-laughs protection:** `ParseOptions` bounds `maxDepth` (default 128),
  `maxAliases` (default 1000) and `maxAliasNodes` (default 100000), counting
  nodes expanded across aliases.
- **Merge keys (`<<`):** Enabled by default (`ParseOptions.mergeKeys = true`).
  Applies only to an unquoted plain `<<` key (not `"<<"` or `!!str <<`). Accepts
  either a single mapping (`<<: *base`) or a sequence of mappings
  (`<<: [*first, *second]`). Explicit keys in the target mapping always win;
  earlier merged mappings win over later ones.
- **Duplicate keys:** Rejected by default (`ErrorKind.DuplicateKey`), matching
  YAML 1.2. `ParseOptions.allowDuplicateKeys = true` allows last-write-wins.

## 4. Parsing API and pull `Event` stream

- `parse(s: &str): Result[Node, Error]` — parses a single document (errors if
  there are multiple documents; empty/comment-only input yields `Null` with its
  comments preserved).
- `parseWith(s: &str, opts: &ParseOptions): Result[Node, Error]`
- `parseAll(s: &str): Result[[]Node, Error]` / `parseAllWith` — parses a
  multi-document stream (`---` / `...`).
- `parseDoc(s: &str): Result[Doc, Error]` / `parseDocs(s: &str): Result[[]Doc, Error]`
  — preserves document-level markers (`hasStart`, `hasEnd`, `headComment`).
- `decoder(s: &str)` / `decoderWith(s: &str, opts: &ParseOptions)` — incremental
  document decoder (`next(): Result[Option[Doc], Error]`).
- `events(s: &str)` / `eventsWith(s: &str, opts: &ParseOptions)` — pull-based
  event stream (`StreamStart`, `DocStart`, `MapStart`, `SeqStart`, `Scalar`,
  `Alias`, `Comment`, `SeqEnd`, `MapEnd`, `DocEnd`, `StreamEnd`), returning
  `Result[Option[Event], Error]`.

`Error` is a `value record` with `kind: ErrorKind`, `message: str`, `path: str`,
`span: Span`. `toStr()` formats as `yaml: <message> at line L, column C` (with
path when present during decoding).

## 5. Typed decoding (`MapDecoder` & `SeqDecoder`)

`MapDecoder` is a borrow-class `value record` holding `node: &Node`, `path: str`
and `seen: []bool`:

- `n.map(): Result[MapDecoder, Error]` (and `n.mapAt(path)`).
- Required fields: `reqStr`, `reqInt`, `reqFloat`, `reqDecimal`, `reqBool`,
  `reqDate`, `reqNode`, `reqWith[T]`, `reqSeq[T]`, `reqMap[V]`.
- Optional with default: `optStr`, `optInt`, `optFloat`, `optDecimal`, `optBool`.
- Optional returning `Option[T]` (missing or `null` -> `None`, wrong type -> `Err`):
  `optStrOpt`, `optIntOpt`, `optFloatOpt`, `optDecimalOpt`, `optBoolOpt`,
  `optDateOpt`, `optNode`, `optWith[T]`, `optSeq[T]`.
- `finish(): Result[Unit, Error]` — returns `ErrorKind.UnknownKey` pointing at
  the first unread key's `Span`. `unknownKeys(): []str` lists all unread keys.

Every decoding error records the dotted YAML path (e.g. `server.tls.port`) and
the offending node's `Span`.

## 6. Writing and JSON bridge

- `write(n: &Node, opts: &WriteOptions): str`
- `writeDoc(d: &Doc, opts: &WriteOptions): str`
- `writeAll(docs: &[Node], opts: &WriteOptions): str`
- `writeTo[W: Sink](w: mut &W, n: &Node, opts: &WriteOptions)`
- `Sink` interface (`write(&str)`, `writeByte(byte)`) — satisfied by `io.Writer`
  and `yaml.Buf`.
- `WriteOptions`: `indent` (default 2), `sortKeys`, `comments` (default true),
  `preserveStyle` (default true), `literalMultiline` (default true), `flowLevel`
  (-1), `docStart`, `docEnd`, `indentSeq`.
- Safe quoting guarantees that any `Str` that could be misread as a YAML 1.2
  keyword, number, indicator or comment is quoted when written in `Any`/`Plain`
  style, ensuring semantic round-trip equality.
- `toJson(n: &Node): Result[json.Json, Error]` and `fromJson(j: &json.Json): Node`.

## 7. Tests

- `lib/tests/run/yaml_parse.lxl`: YAML 1.2 Core Schema scalars (including
  non-boolean `yes`/`no`/`on`/`off`, `010` vs `0o755`, `0xFF`, `.inf`, `.nan`,
  exact `Decimal`), block scalars (`|`, `|-`, `|+`, `>`, explicit indent),
  double/single-quoted escapes and folding, indentless/compact/flow collections,
  non-string keys, anchors/aliases, merge keys (`<<`), multi-document streams,
  duplicate keys, cyclic aliases and alias-bomb protection.
- `lib/tests/run/yaml_decode.lxl`: `MapDecoder` into typed Lexell records,
  unknown-key rejection (`finish()`) with dotted paths and `line:col`, nested
  decoders, sequence index paths, `Decimal`, `time.Date`/`OffsetDateTime` and
  `!!binary`.
- `lib/tests/run/yaml_roundtrip.lxl`: comment preservation (`head`, `line`,
  `foot`, `blankBefore`), round-trip editing (`set` preserving key order and
  inline comments), style preservation, safe plain-scalar quoting, copy-on-write
  independence, large indexed mappings, `sortKeys`, `writeAll`, `toJson` /
  `fromJson`, and the pull `events()` parser.
- `tests/yamlsuite.py` runs the official
  [YAML 1.2 Test Suite](https://github.com/yaml/yaml-test-suite) (`data-2022-01-17`):
  - **Result, native and C:** **402/402 passed** (0 failed, 0 crashed, leak-checked
    under `LXL_CHECK=1`), including JSON comparison against `in.json` and
    write -> re-parse round-trip equality on every valid case.

