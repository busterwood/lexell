#!/usr/bin/env python3
"""Drive Microsoft SQL Tools Service (the engine of VS Code's SQL Server
extension) as the extension does: connect, Object Explorer expanded down,
IntelliSense completions, a query. Prints a log of what worked and what
failed. Usage: vscode_sts.py STS_BINARY HOST,PORT USER PASSWORD DB [maxdepth] [--setup FILE]

From ~/Work/lexdb-bench/saved/mssql-vscode/sts.py (the trace's recording);
--setup runs FILE's batches (GO between them) first, through the service's
query/executeString, as a query window would.
tests/lexdb/vscode.py runs it against lexdb (design/lexdb-tds.md, section 13)."""
import json, subprocess, sys, threading, queue, time, os

argv = sys.argv[1:]
setup = None
if '--setup' in argv:
    i = argv.index('--setup')
    setup = argv[i + 1]
    del argv[i:i + 2]
exe, server, user, pw, db = argv[0:5]
maxdepth = int(argv[5]) if len(argv) > 5 else 4
p = subprocess.Popen([exe], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                     stderr=subprocess.DEVNULL, cwd=os.path.dirname(exe))
msgs = queue.Queue()
def reader():
    f = p.stdout
    while True:
        hdr = b""
        while not hdr.endswith(b"\r\n\r\n"):
            c = f.read(1)
            if not c: return
            hdr += c
        n = int([l for l in hdr.decode().split("\r\n") if l.lower().startswith("content-length")][0].split(":")[1])
        msgs.put(json.loads(f.read(n)))
threading.Thread(target=reader, daemon=True).start()
nid = [0]
def send(method, params, notify=False):
    m = {"jsonrpc": "2.0", "method": method, "params": params}
    if not notify:
        nid[0] += 1; m["id"] = nid[0]
    b = json.dumps(m).encode()
    p.stdin.write(b"Content-Length: %d\r\n\r\n" % len(b) + b); p.stdin.flush()
    return m.get("id")
pending = []
def wait(pred, t=60):
    end = time.time() + t
    while time.time() < end:
        for m in pending:
            if pred(m): pending.remove(m); return m
        try: m = msgs.get(timeout=0.5)
        except queue.Empty: continue
        if m.get("method") in ("window/logMessage", "telemetry/event"): continue
        if "id" in m and "method" in m:   # a request from the service: answer empty
            r = json.dumps({"jsonrpc": "2.0", "id": m["id"], "result": None}).encode()
            p.stdin.write(b"Content-Length: %d\r\n\r\n" % len(r) + r); p.stdin.flush(); continue
        if pred(m): return m
        pending.append(m)
    return None
def call(method, params, t=60):
    i = send(method, params)
    return wait(lambda m: m.get("id") == i, t)

opts = {"server": server, "database": db, "user": user, "password": pw, "authenticationType": "SqlLogin",
        "encrypt": "Optional", "trustServerCertificate": True, "applicationName": "vscode-mssql",
        "connectTimeout": 15}
call("initialize", {"processId": os.getpid(), "capabilities": {}, "rootUri": None})
uri = "untitled:q1"
r = call("connection/connect", {"ownerUri": uri, "connection": {"options": opts}})
c = wait(lambda m: m.get("method") == "connection/complete")
print("CONNECT:", "ok" if c and c["params"].get("connectionId") else c and (c["params"].get("errorMessage") or c["params"].get("messages")))
if c and c["params"].get("serverInfo"): print("  serverInfo:", {k: c["params"]["serverInfo"].get(k) for k in ("serverVersion", "engineEditionId", "isCloud")})

if setup:
    batches, cur = [], []
    for line in open(setup, encoding='utf-8'):
        if line.strip().upper() == 'GO':
            batches.append(''.join(cur)); cur = []
        else:
            cur.append(line)
    for b in batches:
        if not b.strip(): continue
        call("query/executeString", {"ownerUri": uri, "query": b})
        q = wait(lambda m: m.get("method") == "query/complete", 60)
        bs = (q or {}).get("params", {}).get("batchSummaries") or [{}]
        if not q or bs[0].get("hasError"):
            print("SETUP: error in", b.strip().split('\n')[0][:80])
    pending[:] = [m for m in pending if m.get("method") != "query/message"]

r = call("objectexplorer/createsession", {"options": opts})
sid = r and (r.get("result") or {}).get("sessionId")
s = wait(lambda m: m.get("method") == "objectexplorer/sessioncreated")
if not s or not s["params"].get("success"):
    print("OE SESSION: FAILED", s and s["params"].get("errorMessage"))
else:
    root = s["params"]["rootNode"]
    print("OE SESSION: ok, root", root.get("label"))
    todo = [(root["nodePath"], 0, root.get("label"))]
    while todo:
        path, d, label = todo.pop(0)
        if d >= maxdepth: continue
        send("objectexplorer/expand", {"sessionId": sid, "nodePath": path})
        e = wait(lambda m: m.get("method") == "objectexplorer/expandCompleted" and m["params"].get("nodePath") == path, 90)
        if not e: print("  " * d + f"EXPAND {label}: TIMEOUT"); continue
        if e["params"].get("errorMessage"): print("  " * d + f"EXPAND {label}: ERROR {e['params']['errorMessage'][:300]}"); continue
        kids = e["params"].get("nodes") or []
        print("  " * d + f"EXPAND {label}: {len(kids)} -> " + ", ".join(k.get("label", "?") for k in kids[:12]))
        for k in kids:
            if k.get("isLeaf"): continue
            lab = k.get("label", "")
            if d == 0 and lab != "Databases": continue
            if d == 1 and (k.get("nodeType") != "Database" or lab != db): continue
            if d == 2 and lab not in ("Tables", "Views"): continue
            if d == 3 and (lab.startswith("Dropped") or lab.startswith("External")): continue
            if d == 4 and lab not in ("Columns", "Keys", "Constraints", "Indexes", "Triggers", "Statistics"): continue
            todo.append((k["nodePath"], d + 1, lab))

send("textDocument/didOpen", {"textDocument": {"uri": uri, "languageId": "sql", "version": 1,
     "text": "select * from orders o join customers c on o."}}, notify=True)
time.sleep(2)
for ch, what in ((14, "tables"), (46, "columns")):
    r = call("textDocument/completion", {"textDocument": {"uri": uri}, "position": {"line": 0, "character": ch}}, 60)
    items = (r or {}).get("result") or []
    if isinstance(items, dict): items = items.get("items", [])
    print(f"COMPLETION {what}: {len(items)} items", [i.get("label") for i in items[:10]])

r = call("query/executeString", {"ownerUri": uri, "query": "select top 5 * from orders"})
q = wait(lambda m: m.get("method") == "query/complete", 60)
if q:
    bs = q["params"].get("batchSummaries") or [{}]
    print("QUERY:", "error" if bs[0].get("hasError") else "ok", [rs.get("rowCount") for rs in bs[0].get("resultSetSummaries") or []])
for m in [m for m in pending if m.get("method") == "query/message"][:5]:
    print("  message:", m["params"]["message"].get("message", "")[:200])
p.kill()
