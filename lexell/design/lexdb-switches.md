# lexdb: switches, old paths, and how they are removed

Status: 2026-11-15, branch `arch/deep-modules`, based on `04fa4b80`
(lexdb.md 9.136). Companion to
[lexdb-architecture.md](lexdb-architecture.md).

## 1. The rule

> **Delete what is dead. Seam what we still measure. Measure. Delete the
> loser.**

An old path is an asset only while it is the measurement control. Once it
is behind a seam and has been measured, it is a liability.

- **Dead compatibility** (no users, no A/B value) is deleted now. lexdb is
  unreleased; the design already says no old file need stay readable.
- **A/B performance** uses the old **binary/commit** as the control, not a
  runtime flag in the serving build. An in-process A/B is allowed only in a
  test build, behind one seam.
- **Correctness oracles** are PostgreSQL and the old binary, not a second
  engine in production.
- **Configuration** (cache, I/O mode, feature settings) stays, but is read
  once at one seam, never per row.
- **Test hooks** live in a test build or a clearly named test mode.

No new runtime flag without a named seam and a deletion phase.

## 2. Classification

| Item | What it is | Class | Target | Phase |
|---|---|---|---|---|
| `T_LEAF` reader/writer | pre-9.109 page format | delete | — | 1 |
| tagged row (general) | pre-9.50 row format; long/odd values | seam | `Rows`: fixed + `C_ANY`/`C_STUB` overflow | 2 |
| `LEXDB_ROWFMT` | tagged vs fixed A/B | old binary | fixed only; delete the flag | 1 |
| `LEXDB_COLUMNS` / `setColumns` | row vs column leaf A/B | seam | `LeafCodec` in Rows/Store; old binary for A/B | 2 |
| `LEXDB_COLCHECK` | codec self-check | test-only | `Rows` test hook | test build |
| `olderKinds`, `upgradeLayouts`, `setLegacyKinds` | pre-9.113 layouts | delete | — | 1 |
| `legacyTimeRows`, `timeTagged` | pre-9.115 tagged-time rows | delete | — | 1 |
| flat free list in the meta page | pre-runs free encoding | delete | runs only | 1 |
| `Db.owner` | dead bookkeeping | delete | — | 1 |
| `st.fo` | live vs follower read view | seam | `ReadView` (batch-level) | 3 |
| `scanLeaves` returning false on a follower | leaf representation leaking to exec | seam | `ReadView.nextBatch` | 3 |
| `rs.batch` / `Run.batch` | master switch for batches, compiled expressions, outputs, typed sort | seam | `ExecStrategy`; compiled/typed always on | split 1, seam 6 |
| `lexdb_planner` / `Session.rules` | rules vs cost planner | seam | `CostModel`; rules as no-stats fallback/test | 9 |
| `ckptLocked` / `CUT_TRIES` | checkpoint cut vs whole-under-`with` fallback | fallback | cut-only, with a retry; delete locked | 4 |
| `CUT_POOL` / `LEXDB_CKPT_POOL` / `setCutChunk` | parallel encode experiment; test chunk size | config/test | behind the checkpoint encoder; delete if no win | 4 |
| `pushed` vs `poll` | follower input modes | internal | one `applyFrame` seam; hide epochs | 3 |
| `PUSH_KEEP` / `Outbox` | replication buffer | internal/config | follower/repl internal | 3 |
| `Epoch`, `PushFrame` | follower delta structure | internal | hidden by `ReadView` | 3 |
| `LEXDB_LOG_DSYNC` | log flush mode | config | log I/O seam | — |
| `LXL_URING` | I/O backend | config | disk I/O seam | — |
| `--cache-mb` | cache size | config | options | — |
| `--unsafe-no-sync` | test/disk mode | test-only | test harness | test build |
| `setFrameMax`, `setDropReads`, `setCountHook` | fault injection / tests | test-only | test build hooks | test build |
| `setUpgradeBudget` | 9.114 upgrade queue test hook | test-only | goes with the upgrade queue | 2 |
| `lexdb_autoanalyze` | automatic statistics | config | stats task seam | — |
| `lexdb_range_delete` | range delete policy | config | delete planner seam | — |
| `SQL CHECKPOINT` | feature | not a switch | — | — |

## 3. Blast radius

The target is **one selection point and zero hot-loop branches**.

| Flag / path | Current blast radius | Target seam |
|---|---|---|
| `st.fo` | ~22 read-path sites | `ReadView` |
| `rs.batch` | 4 subsystems + 5 drivers | `ExecStrategy` |
| `LEXDB_ROWFMT` | encoder, decoder, executor, tests | `Rows` |
| `LEXDB_COLUMNS` | leaf writer, leaf reader, store options | `LeafCodec` |
| `lexdb_planner` | ~22 planner branches, two cost models | `CostModel` |
| `ckptLocked` | one fallback branch in the checkpoint | delete after cut is total |
| `pushed` / `poll` | two follower apply paths | one `applyFrame` |
| `CUT_POOL` | one encoder branch | checkpoint encoder config |

`st.fo` and `rs.batch` are the largest, and they are not really flags:
they are the same design decision known in many places. `LEXDB_ROWFMT`
and `lexdb_planner` are next.

## 4. How A/B is done without the in-process switch

- **End-to-end:** build the base commit and the new commit; run
  interleaved on the same data and machine; compare wall time, CPU time,
  medians. This is the method already used in the design record.
- **Microbenchmark:** a test-only harness that calls both implementations
  directly, or a test build with both behind the seam. Not a production
  flag.
- **Correctness:** run the same SQL against the old binary and the new one;
  compare outputs, errors included. This tests the real artifact.
- **Portability of the comparison:** git and the old binary preserve it;
  the serving build does not need the alternate path.

## 5. Deletion schedule

| Phase | Delete | Gate |
|---|---|---|
| 1 | `T_LEAF`, old layouts, dead hooks, flat free list, `Db.owner`, `LEXDB_ROWFMT`; keep the tagged writer as the overflow form for now | suite subset, targeted store/format tests |
| 2 | tagged row as a general format (replaced by `C_ANY`/`C_STUB`), mixed-layout leaves, row-leaf table fallback, `LEXDB_COLUMNS` production switch, `setUpgradeBudget` / upgrade queue | `cols_codec`, `exec_cols`, `exec_upgrade`, `exec_rowfmt`, byte-exact checks |
| 3 | `st.fo` branches, `scanLeaves` false-on-follower, push/poll duplication | `follow_basic`, `follow_covers`, `exec_replica`, `replica.py` |
| 4 | `ckptLocked` / `CUT_TRIES` fallback; decide `CUT_POOL` | `store_ckptcut` (including cancelled snapshot, real disk, pool) |
| 6 | `rs.batch` master switch, old row SELECT operators or test-only | `exec_batch*`, EXPLAIN counts |
| 9 | `lexdb_planner` production mode if cost covers no-stats | `exec_joincost`, `exec_joinorder`, `exec_switch` |

## 6. New-flag policy

- A flag must name its seam and its deletion phase in this file.
- A flag that selects an implementation must be read once at connection,
  plan or leaf granularity; it must not be read in a row loop.
- A flag that selects a dialect, format or read view must not leak into a
  core module's hot path.
- A flag that only exists to compare two implementations belongs in the
  test harness or an old binary, not in the serving build.
