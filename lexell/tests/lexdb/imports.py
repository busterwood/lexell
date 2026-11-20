#!/usr/bin/env python3
"""Checks lexdb's module dependency rule (design/lexdb-architecture.md 4).

- Core never imports a dialect, except for the exact phase-5 edges listed in
  KNOWN_CORE_DIALECT. The comparison is exact: a new edge fails, and so does
  removing one without updating the list.
- A dialect's behavior module imports only its own family's modules (plus
  core). A protocol module (wire, TDS, TNS) composes the dialect it serves.
- A dialect's data module imports nothing but core.
- The storage stack is layered (design/lexdb-layers.md 4): lexdb_access
  (layer 2, how a relation is laid out in trees) imports only the store, the
  row codecs and the vocabulary below it; nothing below it imports it.
- The pipeline module lexdb_pipe (layer 6, design/lexdb-layers.md 6.2.3)
  sits below lexdb_exec and above the plan, the binder and access: it never
  imports exec, a dialect or a protocol module; from the store it uses the
  Store and Txn handles only, and it never reads a transaction's SQL state
  (Txn.sql). Only lexdb_exec imports it.
- The statistics module lexdb_stats (layer 5, design/lexdb-layers.md 6.2,
  slice E2) sits above the catalog, access and the store and below the
  planner's vocabulary and the executor: it never imports the binder, the
  plan, the pipeline or exec (what needs the evaluator comes in its Up
  hooks), nor reads a transaction's SQL state (Txn.sql). Only lexdb_plan
  and lexdb_exec import it.
- No cycle.

Run by lexdb.py before the tests; also usable directly.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CMD = os.path.normpath(os.path.join(HERE, "..", "..", "cmd"))
IMPORT = re.compile(r'import\s+"\./([A-Za-z0-9_]+)"')

CORE = {
    "lexdb_access", "lexdb_agg", "lexdb_base", "lexdb_bind", "lexdb_catalog", "lexdb_cols", "lexdb_dbopt", "lexdb_dialect", "lexdb_disk",
    "lexdb_exec", "lexdb_fkprobe", "lexdb_float", "lexdb_func", "lexdb_gen", "lexdb_held", "lexdb_lib", "lexdb_like",
    "lexdb_locks", "lexdb_match",
    "lexdb_memo", "lexdb_ops", "lexdb_vec",
    "lexdb_page", "lexdb_parse", "lexdb_pct", "lexdb_pipe", "lexdb_plan", "lexdb_repl", "lexdb_rows", "lexdb_routine",
    "lexdb_session", "lexdb_setop", "lexdb_sort", "lexdb_sql", "lexdb_sqlcoll", "lexdb_stats",
    "lexdb_store", "lexdb_time", "lexdb_udf", "lexdb_window",
}

PG_DATA = {"lexdb_pgdata"}
PG_BEHAVIOR = {"lexdb_pg", "lexdb_pgcat"}
SYS_DATA = {"lexdb_sysdata"}
SYS_BEHAVIOR = {"lexdb_syscat", "lexdb_tsqlfn", "lexdb_tsql", "lexdb_tsqlparse", "lexdb_tsqlfunc"}
ORA_DATA = {"lexdb_oradata"}
ORA_BEHAVIOR = {"lexdb_oracat", "lexdb_orafn", "lexdb_oraadm", "lexdb_oratext", "lexdb_plsql", "lexdb_plcall"}
PROTO = {"lexdb_wire", "lexdb_tds", "lexdb_tns", "lexdb_auth"}

DATA = PG_DATA | SYS_DATA | ORA_DATA
BEHAVIOR = PG_BEHAVIOR | SYS_BEHAVIOR | ORA_BEHAVIOR
DIALECT = DATA | BEHAVIOR | PROTO

# The dialect imports lexdb_exec still makes: the phase-5 debt (catalog
# generators and wire/auth move into the dialect modules, and exec calls them
# through the Dialect interface). Keep this list exact.
KNOWN_CORE_DIALECT = {
    ("lexdb_exec", "lexdb_pg"),
    ("lexdb_exec", "lexdb_pgcat"),
    ("lexdb_exec", "lexdb_syscat"),
    ("lexdb_exec", "lexdb_oracat"),
    ("lexdb_exec", "lexdb_orafn"),
    ("lexdb_exec", "lexdb_tsqlfn"),
    ("lexdb_exec", "lexdb_auth"),
}

# The binder (design/lexdb-layers.md 4.4, layer 4) sits above the language
# model, the catalog and the dialect facts, and below the planner and the
# executor: it imports only these (and lexell's own libraries).
BIND = "lexdb_bind"
BIND_MAY_IMPORT = {"lexdb_base", "lexdb_sql", "lexdb_catalog", "lexdb_dialect", "lexdb_time", "lexdb_float", "lexdb_ops", "lexdb_lib"}

# The access layer (design/lexdb-layers.md 4.2) sits above the store and the
# row codecs and below the catalog, the planner and the executor: what it may
# import, and the modules below it, which may not import it.
ACCESS = "lexdb_access"
ACCESS_MAY = {"lexdb_base", "lexdb_sql", "lexdb_rows", "lexdb_store", "lexdb_time", "lexdb_sqlcoll", "lexdb_like", "lexdb_vec"}
BELOW_ACCESS = {"lexdb_store", "lexdb_rows", "lexdb_page", "lexdb_cols", "lexdb_disk", "lexdb_locks", "lexdb_memo",
                "lexdb_session", "lexdb_base", "lexdb_sql", "lexdb_time", "lexdb_sqlcoll", "lexdb_like", "lexdb_dialect",
                "lexdb_vec"}

# The value operations (lexdb_ops, design/lexdb-layers.md 4.4.1) sit below
# the binder and the executor: values, types and the time and number
# libraries only.
OPS = "lexdb_ops"
OPS_MAY_IMPORT = {"lexdb_base", "lexdb_sql", "lexdb_time", "lexdb_float", "lexdb_func", "lexdb_dialect"}

# The function library (lexdb_lib, design/lexdb-layers.md 4.4.1, slice 2c
# item 3) sits beside the value operations, below the binder and the
# executor: what it may import.
LIB = "lexdb_lib"
LIB_MAY_IMPORT = OPS_MAY_IMPORT | {"lexdb_ops", "lexdb_like", "lexdb_rows", "lexdb_catalog", "lexdb_access"}

# The pipeline module (design/lexdb-layers.md 6.2.3): what it may import
# (and lexell's own libraries), the store names it may use, and who may
# import it. Session state reaches it in its context (lexdb_pipe.Ctx).
PIPE = "lexdb_pipe"
PIPE_MAY_IMPORT = {"lexdb_base", "lexdb_sql", "lexdb_time", "lexdb_float", "lexdb_rows", "lexdb_vec", "lexdb_like",
                   "lexdb_sqlcoll", "lexdb_ops", "lexdb_lib", "lexdb_catalog", "lexdb_bind", "lexdb_plan",
                   "lexdb_access", "lexdb_store", "lexdb_sort", "lexdb_agg", "lexdb_held"}
PIPE_STORE_NAMES = {"Store", "Txn"}
PIPE_USERS = {"lexdb_exec", "lexdb_setop"}

# The statistics (design/lexdb-layers.md 6.2, E2): what they may import (and
# lexell's own libraries), and who may import them. The session's settings
# come as arguments, the evaluator through lexdb_stats.Up.
STATS = "lexdb_stats"
STATS_MAY_IMPORT = {"lexdb_base", "lexdb_sql", "lexdb_time", "lexdb_float", "lexdb_ops", "lexdb_store", "lexdb_catalog",
                    "lexdb_access"}
STATS_USERS = {"lexdb_plan", "lexdb_exec"}

# How rows are put in order (lexdb_sort, design/lexdb-layers.md 6.2.3, slice
# P3): the sort keys the pipeline's Sort and the row engine share. Values and
# their encodings only; only the pipeline and exec import it.
SORT = "lexdb_sort"
SORT_MAY_IMPORT = {"lexdb_sql", "lexdb_ops", "lexdb_vec", "lexdb_access"}
SORT_USERS = {"lexdb_pipe", "lexdb_exec", "lexdb_agg", "lexdb_setop", "lexdb_window", "lexdb_pct"}

# The aggregate accumulators (lexdb_agg, design/lexdb-batch-gaps.md item 3):
# values and their orders only; the row engine and the pipeline import them.
AGG = "lexdb_agg"
AGG_MAY_IMPORT = {"lexdb_base", "lexdb_sql", "lexdb_ops", "lexdb_access", "lexdb_sort", "lexdb_pct"}
AGG_USERS = {"lexdb_pipe", "lexdb_exec", "lexdb_window"}

# How a set operation combines its parts' rows (lexdb_setop, design/
# lexdb-batch-gaps.md item 11): their keys and the streamed run, with the
# pipeline's sort. It runs a part through a hook of lexdb_exec, never
# imports it, and takes only the transaction from the store.
SETOP = "lexdb_setop"
SETOP_MAY_IMPORT = {"lexdb_base", "lexdb_sql", "lexdb_rows", "lexdb_bind", "lexdb_pipe", "lexdb_sort", "lexdb_store"}
SETOP_STORE_NAMES = {"Txn"}
SETOP_USERS = {"lexdb_exec"}

# Rows a run holds, read as the pipeline's batches (lexdb_held, design/
# lexdb-batch-gaps.md item 6): values and the batch type only; only the
# pipeline imports it.
HELD = "lexdb_held"
HELD_MAY_IMPORT = {"lexdb_sql", "lexdb_rows"}
HELD_USERS = {"lexdb_pipe"}

# The window functions' values (lexdb_window, design/lexdb-batch-gaps.md item
# 10): the sort keys and the frame code of the row engine's windows. Values,
# their orders and the aggregate spec type only (the engine evaluates what
# needs its scope, through a hook); only exec imports it.
WINDOW = "lexdb_window"
WINDOW_MAY_IMPORT = {"lexdb_base", "lexdb_sql", "lexdb_ops", "lexdb_sort", "lexdb_agg", "lexdb_access"}
WINDOW_USERS = {"lexdb_exec"}

# lexdb_dialect is the parser-facing union of the dialects' data: the one
# core module that reads it directly (the parser needs the names).
PARSER_DATA = "lexdb_dialect"


def read_modules():
    mods = {}
    for name in sorted(os.listdir(CMD)):
        if not name.startswith("lexdb_") or not name.endswith(".lxl"):
            continue
        path = os.path.join(CMD, name)
        with open(path, encoding="utf-8") as f:
            mods[name[:-4]] = IMPORT.findall(f.read())
    return mods


def family(m):
    if m in PG_DATA or m in PG_BEHAVIOR:
        return "pg"
    if m in SYS_DATA or m in SYS_BEHAVIOR:
        return "sys"
    if m in ORA_DATA or m in ORA_BEHAVIOR:
        return "ora"
    return ""


def check():
    mods = read_modules()
    bad = []
    # The store carries a transaction's SQL state (Txn.sql) and must not
    # read it: the boundary is what keeps storage and SQL session state
    # separable.
    store = os.path.join(CMD, "lexdb_store.lxl")
    with open(store, encoding="utf-8") as f:
        body = f.read()
    sql_fields = re.findall(r"\.sql\.(?:path|sess|rules|memMax|now|zone|pending|consAll|consNames|consDeferred)\b", body)
    if sql_fields:
        bad.append("lexdb_store reads Txn.sql: " + ", ".join(sorted(set(sql_fields))))
    for d in mods.get(ACCESS, []):
        if d not in ACCESS_MAY:
            bad.append(f"{ACCESS} -> {d}: the access layer imports above the store and the row codecs")
    for m in sorted(BELOW_ACCESS):
        if ACCESS in mods.get(m, []):
            bad.append(f"{m} -> {ACCESS}: a module below the access layer imports it")
    for d in mods.get(PIPE, []):
        if d not in PIPE_MAY_IMPORT:
            bad.append(f"{PIPE} -> {d}: the pipeline imports above or beside its layer")
    for m in sorted(mods):
        if PIPE in mods[m] and m not in PIPE_USERS:
            bad.append(f"{m} -> {PIPE}: only {', '.join(sorted(PIPE_USERS))} imports the pipeline")
    pipe = os.path.join(CMD, PIPE + ".lxl")
    if os.path.exists(pipe):
        with open(pipe, encoding="utf-8") as f:
            body = f.read()
        names = set(re.findall(r"\blexdb_store\.([A-Za-z_][A-Za-z0-9_]*)", body)) - PIPE_STORE_NAMES
        if names:
            bad.append(f"{PIPE} uses lexdb_store beyond Store and Txn: " + ", ".join(sorted(names)))
        if re.search(r"\.sql\.", body):
            bad.append(f"{PIPE} reads a transaction's SQL state (Txn.sql)")
    for d in mods.get(STATS, []):
        if d not in STATS_MAY_IMPORT:
            bad.append(f"{STATS} -> {d}: the statistics import above or beside their layer")
    for m in sorted(mods):
        if STATS in mods[m] and m not in STATS_USERS:
            bad.append(f"{m} -> {STATS}: only {', '.join(sorted(STATS_USERS))} import the statistics")
    for d in mods.get(SORT, []):
        if d not in SORT_MAY_IMPORT:
            bad.append(f"{SORT} -> {d}: the sort keys import above their layer")
    for m in sorted(mods):
        if SORT in mods[m] and m not in SORT_USERS:
            bad.append(f"{m} -> {SORT}: only {', '.join(sorted(SORT_USERS))} import the sort keys")
    for d in mods.get(AGG, []):
        if d not in AGG_MAY_IMPORT:
            bad.append(f"{AGG} -> {d}: the aggregate accumulators import above their layer")
    for m in sorted(mods):
        if AGG in mods[m] and m not in AGG_USERS:
            bad.append(f"{m} -> {AGG}: only {', '.join(sorted(AGG_USERS))} import the aggregate accumulators")
    for d in mods.get(WINDOW, []):
        if d not in WINDOW_MAY_IMPORT:
            bad.append(f"{WINDOW} -> {d}: the window functions import above or beside their layer")
    for m in sorted(mods):
        if WINDOW in mods[m] and m not in WINDOW_USERS:
            bad.append(f"{m} -> {WINDOW}: only {', '.join(sorted(WINDOW_USERS))} import the window functions")
    for d in mods.get(SETOP, []):
        if d not in SETOP_MAY_IMPORT:
            bad.append(f"{SETOP} -> {d}: the set operations import above or beside their layer")
    for m in sorted(mods):
        if SETOP in mods[m] and m not in SETOP_USERS:
            bad.append(f"{m} -> {SETOP}: only {', '.join(sorted(SETOP_USERS))} import the set operations")
    setop = os.path.join(CMD, SETOP + ".lxl")
    if os.path.exists(setop):
        with open(setop, encoding="utf-8") as f:
            body = f.read()
        names = set(re.findall(r"\blexdb_store\.([A-Za-z_][A-Za-z0-9_]*)", body)) - SETOP_STORE_NAMES
        if names:
            bad.append(f"{SETOP} uses lexdb_store beyond Txn: " + ", ".join(sorted(names)))
        if re.search(r"\.sql\.", body):
            bad.append(f"{SETOP} reads a transaction's SQL state (Txn.sql)")
    for d in mods.get(HELD, []):
        if d not in HELD_MAY_IMPORT:
            bad.append(f"{HELD} -> {d}: the held rows' batches import above their layer")
    for m in sorted(mods):
        if HELD in mods[m] and m not in HELD_USERS:
            bad.append(f"{m} -> {HELD}: only {', '.join(sorted(HELD_USERS))} imports the held rows' batches")
    stats = os.path.join(CMD, STATS + ".lxl")
    if os.path.exists(stats):
        with open(stats, encoding="utf-8") as f:
            if re.search(r"\.sql\.", f.read()):
                bad.append(f"{STATS} reads a transaction's SQL state (Txn.sql)")
    for m in sorted(set(mods) - CORE - DIALECT):
        bad.append(f"{m}: not in the core or dialect sets")

    for m, deps in mods.items():
        for d in deps:
            if d not in mods:
                bad.append(f"{m} -> {d}: no such module")
                continue
            if m in CORE:
                if d in DIALECT and (m, d) not in KNOWN_CORE_DIALECT:
                    if not (m == PARSER_DATA and d in DATA):
                        bad.append(f"{m} -> {d}: core imports a dialect")
                continue
            if m in PROTO:
                continue
            if m in DATA:
                if d in DIALECT:
                    bad.append(f"{m} -> {d}: a dialect data module imports a dialect")
                continue
            if d in DIALECT and family(m) != family(d):
                bad.append(f"{m} -> {d}: dialect family {family(m)} imports {family(d)}")

    for d in mods.get(OPS, []):
        if d not in OPS_MAY_IMPORT:
            bad.append(f"{OPS} -> {d}: the value operations import above their layer")
    for d in mods.get(LIB, []):
        if d not in LIB_MAY_IMPORT:
            bad.append(f"{LIB} -> {d}: the function library imports above its layer")
    for d in mods.get(BIND, []):
        if d not in BIND_MAY_IMPORT:
            bad.append(f"{BIND} -> {d}: the binder imports above or beside its layer")

    # The list of known core->dialect edges is exact in both directions.
    present = {(m, d) for m, ds in mods.items() for d in ds if m in CORE and d in DIALECT}
    for m, d in sorted(KNOWN_CORE_DIALECT - present):
        bad.append(f"{m} -> {d}: listed as known debt but no longer imported")

    # Cycles.
    color = {}
    stack = []

    def visit(m):
        color[m] = 1
        stack.append(m)
        for d in mods.get(m, []):
            if d not in mods:
                continue
            if color.get(d) == 1:
                i = stack.index(d)
                bad.append("cycle: " + " -> ".join(stack[i:] + [d]))
            elif color.get(d, 0) == 0:
                visit(d)
        stack.pop()
        color[m] = 2

    for m in sorted(mods):
        if color.get(m, 0) == 0:
            visit(m)

    return mods, bad


def main():
    mods, bad = check()
    if bad:
        for b in bad:
            print("lexdb imports: " + b, file=sys.stderr)
        print(f"lexdb imports: {len(bad)} problem(s)", file=sys.stderr)
        return 1
    edges = sum(len(ds) for ds in mods.values())
    print(f"imports: ok ({len(mods)} modules, {edges} edges)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
