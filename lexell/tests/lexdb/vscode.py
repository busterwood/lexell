#!/usr/bin/env python3
"""A live check of VS Code's SQL Server extension against lexdb: starts lexdb
with a TDS listener, loads vscode_pg_schema.sql over PostgreSQL's protocol
(psql: a schema app, as most users' tables are made) and vscode_schema.sql
over TDS, and drives Microsoft SQL Tools
Service (the extension's engine) through vscode_sts.py as the extension
does: connect, Object Explorer down to columns, keys, constraints, indexes
and statistics, IntelliSense, a query. design/lexdb-tds.md, section 13.

    STS=/path/to/MicrosoftSqlToolsServiceLayer python3 lexell/tests/lexdb/vscode.py [--compiler lexell/compiler/out/lxlc] [--lexdb BINARY]

Not part of the suite (it needs the service: github.com/microsoft/sqltoolsservice
releases, and psql). Prints the service's view, then checks it shows what SQL Server's
does for the same schema (the labels below, recorded against SQL Server 2022
but for the names lexdb gives constraints); exits 1 if not.
"""
import argparse, os, socket, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))

# What the service must show (SQL Server's, with lexdb's constraint names).
WANT = [
    "CONNECT: ok",
    "EXPAND Databases: 2 -> System Databases, lexdb",
    "EXPAND lexdb: 8 -> Tables, Views, Synonyms, Programmability, External Resources, Service Broker, Storage, Security",
    "EXPAND Columns: 4 -> id (PK, int, not null), name (nvarchar(100), not null), email (varchar(200), null), created_at (datetime2(7), not null)",
    "EXPAND Columns: 7 -> id (PK, bigint, not null), customer_id (FK, int, not null), amount (decimal(10,2), not null), placed (date, not null), "
    "note (nvarchar(max), null), ref (uniqueidentifier, null), paid (bit, not null)",
    "EXPAND Columns: 3 -> id (bigint, not null), customer_id (int, not null), amount (decimal(10,2), not null)",
    "EXPAND Keys: 2 -> customers_email_key, customers_pkey",
    "EXPAND Keys: 2 -> orders_pkey, orders_customer_id_fkey",
    "EXPAND Constraints: 2 -> orders_amount_check, DF_orders_paid",
    "EXPAND Indexes: 2 -> ix_orders_placed (Non-Unique, Non-Clustered), orders_pkey (Unique, Clustered)",
    "EXPAND Statistics: 2 -> ix_orders_placed, orders_pkey",
    "EXPAND Tables: 6 -> app.events, app.users, dbo.customers, dbo.orders, Dropped Ledger Tables, External Tables",
    "EXPAND Views: 3 -> app.recent_events, dbo.big_orders, Dropped Ledger Views",
    "EXPAND Columns: 6 -> id (PK, int, not null), user_id (FK, bigint, not null), took (nvarchar(max), null), payload (varbinary(max), null), "
    "at (time(7), null), tags (nvarchar(max), null)",
    "EXPAND Columns: 12 -> id (PK, bigint, not null), login (nvarchar(40), not null), bio (nvarchar(max), null), balance (decimal(12,2), not null), "
    "active (bit, not null), born (date, null), seen (datetime2(7), null), joined (datetimeoffset(7), not null), score (float, null), "
    "ratio (real, null), level (smallint, null), token (uniqueidentifier, not null)",
    "EXPAND Columns: 3 -> id (int, not null), user_id (bigint, not null), at (time(7), null)",
    "EXPAND Keys: 2 -> events_pkey, events_user_id_fkey",
    "EXPAND Indexes: 2 -> events_pkey (Unique, Clustered), events_user_at (Non-Unique, Non-Clustered)",
    "EXPAND Constraints: 4 -> DF_users_balance, DF_users_active, DF_users_joined, DF_users_token",
    "COLUMN_COMPLETIONS",
    "QUERY: ok [2]",
]


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--compiler', default=os.path.join(ROOT, 'compiler', 'out', 'lxlc'))
    ap.add_argument('--lexdb', help='a lexdb binary (else compiled from cmd/lexdb.lxl)')
    a = ap.parse_args()
    sts = os.environ.get('STS')
    if not sts:
        sys.exit('vscode.py: set STS to the MicrosoftSqlToolsServiceLayer binary')
    with tempfile.TemporaryDirectory() as tmp:
        exe = a.lexdb
        if not exe:
            exe = os.path.join(tmp, 'lexdb')
            r = subprocess.run([a.compiler, os.path.join(ROOT, 'cmd', 'lexdb.lxl'), '-o', exe], capture_output=True, text=True)
            if r.returncode != 0:
                sys.exit('vscode.py: compile: ' + r.stdout + r.stderr)
        data = os.path.join(tmp, 'data')
        os.mkdir(data)
        pg, tds = free_port(), free_port()
        srv = subprocess.Popen([exe, data, '127.0.0.1:%d' % pg, '--tds', '127.0.0.1:%d' % tds], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(100):
                try:
                    socket.create_connection(('127.0.0.1', tds), 0.2).close()
                    break
                except OSError:
                    time.sleep(0.1)
            # PostgreSQL's protocol first: its session, and a schema made through it
            p = subprocess.run(['psql', '-h', '127.0.0.1', '-p', str(pg), '-U', 'lexdb', '-d', 'lexdb', '-q', '-v', 'ON_ERROR_STOP=1',
                                '-f', os.path.join(HERE, 'vscode_pg_schema.sql')], capture_output=True, text=True)
            if p.returncode != 0:
                sys.exit('vscode.py: psql: ' + p.stdout + p.stderr)
            r = subprocess.run([sys.executable, '-I', os.path.join(HERE, 'vscode_sts.py'), sts, '127.0.0.1,%d' % tds, 'lexdb', 'x', 'lexdb', '6',
                                '--setup', os.path.join(HERE, 'vscode_schema.sql')], capture_output=True, text=True, timeout=600)
        finally:
            srv.kill()
    out = r.stdout
    print(out, end='')
    lines = [l.strip() for l in out.split('\n')]
    missing = []
    for w in WANT:
        if w == "COLUMN_COMPLETIONS":
            ok = any(l.startswith("COMPLETION columns: 7 items") and "'customer_id'" in l for l in lines)
        else:
            ok = w in lines
        if not ok:
            missing.append(w)
    if missing:
        print('vscode.py: not as SQL Server shows it:')
        for m in missing:
            print('  ' + m)
        sys.exit(1)
    print('vscode.py: as SQL Server shows it')


if __name__ == '__main__':
    main()
