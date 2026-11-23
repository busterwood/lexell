#!/usr/bin/env python3
"""Checks the SQL examples of lexdb's documentation against a lexdb (tools/README.md).

    check_examples.py [--lexdb PATH] [--jars DIR] [--update] [-v] PAGE_OR_DIR ...

For each page it starts a new lexdb (a scratch data directory, free ports on 127.0.0.1 for the
PostgreSQL, SQL Server and Oracle doors), runs the page's examples in order through their doors,
one session per door, compares each example's output with the block under it, and stops the
server. --update writes lexdb's output into the pages instead. Exit 0 when every example matches.
"""
import argparse
import difflib
import os
import re
import queue
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
END = "--@@END@@"
DOORS = ("postgresql", "tsql", "oracle")

# <!-- example: DOOR -->, then a ```sql block, then a ```text block (the output)
EXAMPLE = re.compile(r"<!--\s*example:\s*(\w+)\s*-->\n```sql\n(.*?)```\n\s*```text\n(.*?)```\n", re.S)
# <!-- setup: DOOR\nSQL\n--> : run, not shown, output not compared
SETUP = re.compile(r"<!--\s*setup:\s*(\w+)\s*\n(.*?)-->", re.S)


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_port(port, proc, secs=30):
    end = time.time() + secs
    while time.time() < end:
        if proc.poll() is not None:
            return False
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.05)
    return False


class Server:
    """A lexdb of its own for one page."""

    def __init__(self, lexdb):
        self.dir = tempfile.mkdtemp(prefix="lexdb-docs-")
        self.pg, self.tds, self.tns = free_port(), free_port(), free_port()
        self.log = open(os.path.join(self.dir, "server.log"), "w")
        self.proc = subprocess.Popen(
            [lexdb, os.path.join(self.dir, "data"), "127.0.0.1:%d" % self.pg,
             "--tds", "127.0.0.1:%d" % self.tds, "--tns", "127.0.0.1:%d" % self.tns,
             "--unsafe-no-sync", "--cache-mb", "64"],
            stdout=self.log, stderr=subprocess.STDOUT, start_new_session=True)
        for p in (self.pg, self.tds, self.tns):
            if not wait_port(p, self.proc):
                self.stop()
                raise RuntimeError("lexdb did not start; see " + self.log.name)

    def stop(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        self.log.close()
        shutil.rmtree(self.dir, ignore_errors=True)


def find_jar(jars, *names):
    for n in os.listdir(jars):
        if any(n.startswith(x) and n.endswith(".jar") for x in names):
            return os.path.join(jars, n)
    sys.exit("check_examples: no %s jar in %s" % (" or ".join(names), jars))


class Session:
    """One client session of a door, fed one block at a time."""

    def __init__(self, cmd, env, psql):
        self.psql = psql
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     env=env, text=True, encoding="utf-8", bufsize=1)
        self.lines = queue.Queue()
        threading.Thread(target=self.read, daemon=True).start()

    def read(self):
        for line in self.proc.stdout:
            self.lines.put(line)
        self.lines.put(None)

    def run(self, block, timeout=120):
        """The block's output, and None; or None and why, when the session ended or did not answer in time."""
        block = block if block.endswith("\n") else block + "\n"
        self.proc.stdin.write(block + ("\\echo " + END if self.psql else END) + "\n")
        self.proc.stdin.flush()
        out = []
        while True:
            try:
                line = self.lines.get(timeout=timeout)
            except queue.Empty:
                return None, "".join(out) + "\n(no answer in %d s)" % timeout
            if line is None:
                return None, "".join(out)
            if line.rstrip("\n") == END:
                return "".join(out), None
            out.append(line)

    def close(self):
        try:
            self.proc.stdin.close()
            self.proc.wait(30)
        except (OSError, subprocess.TimeoutExpired):
            self.proc.kill()
            self.proc.wait()


class Runner:
    def __init__(self, jars):
        self.mssql = find_jar(jars, "mssql-jdbc")
        self.ojdbc = find_jar(jars, "ojdbc11", "ojdbc17")
        self.classes = os.path.join(tempfile.gettempdir(), "lexdb-docrun-%d" % os.getuid())
        src = os.path.join(HERE, "DocRun.java")
        stamp = os.path.join(self.classes, "DocRun.class")
        if not os.path.exists(stamp) or os.path.getmtime(stamp) < os.path.getmtime(src):
            os.makedirs(self.classes, exist_ok=True)
            subprocess.run(["javac", "-d", self.classes, src], check=True)

    def session(self, door, srv):
        env = dict(os.environ, PGTZ="UTC", PGCLIENTENCODING="UTF8", TZ="UTC")
        if door == "postgresql":
            cmd = ["psql", "-X", "-P", "pager=off", "-h", "127.0.0.1", "-p", str(srv.pg), "-U", "postgres", "lexdb"]
        elif door == "tsql":
            cmd = ["java", "-cp", self.classes + ":" + self.mssql, "DocRun", "tsql",
                   "jdbc:sqlserver://127.0.0.1:%d;databaseName=lexdb;encrypt=false;user=sa;password=x" % srv.tds]
        else:
            cmd = ["java", "-Duser.timezone=UTC", "-cp", self.classes + ":" + self.ojdbc, "DocRun", "oracle",
                   "jdbc:oracle:thin:@//127.0.0.1:%d/lexdb" % srv.tns, "sa", "SA"]
        return Session(cmd, env, door == "postgresql")


def tidy(s):
    lines = [l.rstrip() for l in s.split("\n")]
    while lines and lines[-1] == "":
        lines.pop()
    while lines and lines[0] == "":
        lines.pop(0)
    return "\n".join(lines)


def check_page(path, runner, lexdb, update, verbose):
    text = open(path, encoding="utf-8").read()
    items = []      # (start, end of the output block's text, door, sql, expected, shown)
    for m in SETUP.finditer(text):
        items.append((m.start(), None, m.group(1), m.group(2), None))
    for m in EXAMPLE.finditer(text):
        items.append((m.start(), m.span(3), m.group(1), m.group(2), m.group(3)))
    if not items:
        return 0, 0
    items.sort(key=lambda x: x[0])
    for it in items:
        if it[2] not in DOORS:
            print("%s: unknown door %r" % (path, it[2]))
            return 1, 0
    srv = Server(lexdb)
    sessions = {}
    outputs = {}
    try:
        # one session per door, opened at its first block; the blocks run in page order, so an example
        # may make a table in one door and read it in another
        for i, it in enumerate(items):
            door = it[2]
            if door not in sessions:
                sessions[door] = runner.session(door, srv)
            got, why = sessions[door].run(it[3])
            if got is None:
                line = text.count("\n", 0, it[0]) + 1
                print("%s:%d: the %s session ended:\n%s" % (path, line, door, why))
                return 1, len([x for x in items if x[4] is not None])
            outputs[i] = got
    finally:
        for s in sessions.values():
            s.close()
        srv.stop()
    bad = 0
    count = 0
    edits = []
    for i, it in enumerate(items):
        if it[4] is None:
            continue
        count += 1
        want, have = tidy(it[4]), tidy(outputs[i])
        if want != have:
            if update:
                edits.append((it[1], have + "\n"))
            else:
                bad += 1
                line = text.count("\n", 0, it[0]) + 1
                print("%s:%d: %s example differs" % (path, line, it[2]))
                for d in difflib.unified_diff(want.split("\n"), have.split("\n"), "page", "lexdb", lineterm="", n=2):
                    print("    " + d)
        elif verbose:
            print("%s: ok %s" % (path, it[2]))
    if edits:
        for (a, b), new in sorted(edits, reverse=True):
            text = text[:a] + new + text[b:]
        open(path, "w", encoding="utf-8").write(text)
        print("%s: %d example output(s) written" % (path, len(edits)))
    return bad, count


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--lexdb", default=os.environ.get("LEXDB", "lexdb"), help="the lexdb binary (env LEXDB)")
    ap.add_argument("--jars", default=os.environ.get("LEXDB_DOC_JARS", os.path.join(HERE, "jars")),
                    help="a directory with mssql-jdbc and ojdbc11 jars (env LEXDB_DOC_JARS)")
    ap.add_argument("--update", action="store_true", help="write lexdb's output into the pages")
    ap.add_argument("-v", action="store_true", help="name every example that matches")
    a = ap.parse_args()
    pages = []
    for p in a.paths:
        if os.path.isdir(p):
            for root, _, files in os.walk(p):
                pages += [os.path.join(root, f) for f in files if f.endswith(".md")]
        else:
            pages.append(p)
    runner = Runner(a.jars)
    bad = total = 0
    for page in sorted(pages):
        b, n = check_page(page, runner, a.lexdb, a.update, a.v)
        bad += b
        total += n
    print("%d examples, %d differ" % (total, bad))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
