#!/usr/bin/env python3
"""Checks lexdb's module dependency rule (design/lexdb-architecture.md 4).

- Core never imports a dialect, except for the exact phase-5 edges listed in
  KNOWN_CORE_DIALECT. The comparison is exact: a new edge fails, and so does
  removing one without updating the list.
- A dialect's behavior module imports only its own family's modules (plus
  core). A protocol module (wire, TDS, TNS) composes the dialect it serves.
- A dialect's data module imports nothing but core.
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
    "lexdb_base", "lexdb_catalog", "lexdb_cols", "lexdb_dialect", "lexdb_disk",
    "lexdb_exec", "lexdb_float", "lexdb_func", "lexdb_like", "lexdb_match",
    "lexdb_memo",
    "lexdb_page", "lexdb_parse", "lexdb_plan", "lexdb_repl", "lexdb_rows", "lexdb_sql", "lexdb_sqlcoll",
    "lexdb_store", "lexdb_time",
}

PG_DATA = {"lexdb_pgdata"}
PG_BEHAVIOR = {"lexdb_pg", "lexdb_pgcat"}
SYS_DATA = {"lexdb_sysdata"}
SYS_BEHAVIOR = {"lexdb_syscat", "lexdb_tsqlfn", "lexdb_tsql", "lexdb_tsqlparse"}
ORA_DATA = {"lexdb_oradata"}
ORA_BEHAVIOR = {"lexdb_oracat", "lexdb_orafn", "lexdb_oraadm", "lexdb_oratext", "lexdb_plsql"}
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
