#!/usr/bin/env python3
"""A TDS capture proxy: listens on LISTEN, forwards each connection to
TARGET, and prints the packets each way, decoded as far as is useful for
seeing what a client sends and how a server answers (design/lexdb-tds.md):
packet types, PRELOGIN options, SQLBatch text, RPC procedure names, and the
reply's tokens (COLMETADATA's columns and types, ERROR/INFO text, ENVCHANGE,
LOGINACK, DONE counts). TLS records (inside PRELOGIN packets, or straight on
the socket after the handshake) are shown by length only. LOGIN7 is
encrypted under TLS, so it is not seen unless the client sends it plain.

    python3 tds_proxy.py 127.0.0.1:14331 127.0.0.1:14330 [--hex]
"""
import socket
import struct
import sys
import threading

PT = {1: 'SQLBatch', 2: 'PreTDS7Login', 3: 'RPC', 4: 'Reply', 6: 'Attention', 7: 'BulkLoad',
      8: 'FedAuthToken', 14: 'TransMgr', 16: 'Login7', 17: 'SSPI', 18: 'Prelogin'}
TOK = {0x81: 'COLMETADATA', 0xD1: 'ROW', 0xD2: 'NBCROW', 0xFD: 'DONE', 0xFE: 'DONEPROC', 0xFF: 'DONEINPROC',
       0xAA: 'ERROR', 0xAB: 'INFO', 0xAD: 'LOGINACK', 0xE3: 'ENVCHANGE', 0xAE: 'FEATUREEXTACK', 0x79: 'RETURNSTATUS',
       0xAC: 'RETURNVALUE', 0xA9: 'ORDER', 0xA4: 'TABNAME', 0xA5: 'COLINFO', 0xE4: 'SESSIONSTATE'}
HEX = '--hex' in sys.argv
lock = threading.Lock()


def out(cid, d, s):
    with lock:
        print(f'[{cid}] {d} {s}', flush=True)


def u16(b, i): return struct.unpack_from('<H', b, i)[0]
def u32(b, i): return struct.unpack_from('<I', b, i)[0]


def utf16(b): return b.decode('utf-16-le', 'replace')


def bvarchar(b, i):
    n = b[i]
    return utf16(b[i + 1:i + 1 + 2 * n]), i + 1 + 2 * n


def usvarchar(b, i):
    n = u16(b, i)
    return utf16(b[i + 2:i + 2 + 2 * n]), i + 2 + 2 * n


def prelogin(b):
    opts = []
    i = 0
    while i < len(b) and b[i] != 0xFF:
        t, off, n = b[i], struct.unpack_from('>H', b, i + 1)[0], struct.unpack_from('>H', b, i + 3)[0]
        opts.append((t, b[off:off + n].hex()))
        i += 5
    return ' '.join(f'{t}={v}' for t, v in opts)


def typeinfo(b, i):
    """(description, next index) for a TYPE_INFO at i; raises when unknown."""
    t = b[i]
    i += 1
    fixed = {0x30: 'tinyint', 0x32: 'bit', 0x34: 'smallint', 0x38: 'int', 0x3A: 'smalldatetime', 0x3B: 'real',
             0x3C: 'money', 0x3D: 'datetime', 0x3E: 'float', 0x7A: 'smallmoney', 0x7F: 'bigint', 0x1F: 'null'}
    if t in fixed: return fixed[t], i
    if t in (0x26, 0x68, 0x6D, 0x6E, 0x6F, 0x24):
        names = {0x26: 'intn', 0x68: 'bitn', 0x6D: 'fltn', 0x6E: 'moneyn', 0x6F: 'datetimn', 0x24: 'guid'}
        return f'{names[t]}({b[i]})', i + 1
    if t in (0x6A, 0x6C):
        return f'{"decimaln" if t == 0x6A else "numericn"}(len {b[i]}, p {b[i+1]}, s {b[i+2]})', i + 3
    if t == 0x28: return 'date', i
    if t in (0x29, 0x2A, 0x2B):
        return f'{ {0x29: "time", 0x2A: "datetime2", 0x2B: "datetimeoffset"}[t]}({b[i]})', i + 1
    if t in (0xA7, 0xAF, 0xE7, 0xEF):
        n = u16(b, i)
        coll = b[i + 2:i + 7].hex()
        nm = {0xA7: 'varchar', 0xAF: 'char', 0xE7: 'nvarchar', 0xEF: 'nchar'}[t]
        return f'{nm}({"max" if n == 0xFFFF else n}, coll {coll})', i + 7
    if t in (0xA5, 0xAD):
        n = u16(b, i)
        return f'{"varbinary" if t == 0xA5 else "binary"}({"max" if n == 0xFFFF else n})', i + 2
    if t == 0xF1:
        has = b[i]
        return 'xml', i + 1 + (0 if not has else 0)
    raise ValueError(f'type 0x{t:02x}')


def tokens(b, cid, d):
    i = 0
    ncols = 0
    while i < len(b):
        t = b[i]
        name = TOK.get(t, f'0x{t:02x}')
        try:
            if t == 0x81:
                n = u16(b, i + 1)
                i += 3
                cols = []
                if n == 0xFFFF: n = 0
                for _ in range(n):
                    ut, fl = u32(b, i), u16(b, i + 4)
                    ti, i = typeinfo(b, i + 6)
                    nm, i = bvarchar(b, i)
                    cols.append(f'{nm or "(none)"}:{ti}{" null" if fl & 1 else ""}' + (f' ut={ut}' if ut else ''))
                ncols = n
                out(cid, d, f'  COLMETADATA {n}: ' + ', '.join(cols))
                continue
            if t in (0xD1, 0xD2):
                out(cid, d, f'  {name} ... (rest {len(b) - i} bytes not decoded)')
                return
            if t in (0xFD, 0xFE, 0xFF):
                st, cmd, cnt = u16(b, i + 1), u16(b, i + 3), struct.unpack_from('<Q', b, i + 5)[0]
                out(cid, d, f'  {name} status=0x{st:x} curcmd=0x{cmd:x} count={cnt}')
                i += 13
                continue
            if t == 0x79:
                out(cid, d, f'  RETURNSTATUS {struct.unpack_from("<i", b, i + 1)[0]}')
                i += 5
                continue
            if t in (0xAA, 0xAB):
                n = u16(b, i + 1)
                j = i + 3
                num, st, cl = u32(b, j), b[j + 4], b[j + 5]
                msg, k = usvarchar(b, j + 6)
                srv, k = bvarchar(b, k)
                proc, k = bvarchar(b, k)
                line = u32(b, k)
                out(cid, d, f'  {name} {num} state {st} class {cl} line {line} srv {srv!r} proc {proc!r}: {msg}')
                i += 3 + n
                continue
            if t == 0xAD:
                n = u16(b, i + 1)
                j = i + 3
                iface, ver = b[j], struct.unpack_from('>I', b, j + 1)[0]
                prog, k = bvarchar(b, j + 5)
                out(cid, d, f'  LOGINACK iface {iface} tds 0x{ver:08x} prog {prog!r} version {b[k]}.{b[k+1]}.{b[k+2]*256+b[k+3]}')
                i += 3 + n
                continue
            if t == 0xE3:
                n = u16(b, i + 1)
                body = b[i + 3:i + 3 + n]
                typ = body[0]
                if typ in (7,):
                    nl = body[1]
                    out(cid, d, f'  ENVCHANGE {typ} new {body[2:2+nl].hex()} old {body[3+nl:].hex()}')
                elif typ in (8, 9, 10, 17):
                    out(cid, d, f'  ENVCHANGE {typ} {body[1:].hex()}')
                else:
                    nv, k = bvarchar(body, 1)
                    ov, k = bvarchar(body, k)
                    out(cid, d, f'  ENVCHANGE {typ} {ov!r} -> {nv!r}')
                i += 3 + n
                continue
            if t == 0xAE:
                j = i + 1
                feats = []
                while b[j] != 0xFF:
                    fid, ln = b[j], u32(b, j + 1)
                    feats.append(f'{fid}:{b[j+5:j+5+ln].hex()}')
                    j += 5 + ln
                out(cid, d, f'  FEATUREEXTACK {" ".join(feats)}')
                i = j + 1
                continue
            if t in (0xA9, 0xA4, 0xA5, 0xE4, 0xAC):
                n = u32(b, i + 1) if t == 0xE4 else u16(b, i + 1)
                out(cid, d, f'  {name} ({n} bytes)')
                i += (5 if t == 0xE4 else 3) + n
                continue
            out(cid, d, f'  token 0x{t:02x}: stop ({len(b) - i} bytes left)')
            return
        except Exception as e:
            out(cid, d, f'  {name}: undecoded ({e}); {len(b) - i} bytes left')
            return


def message(cid, d, ptype, status, data):
    nm = PT.get(ptype, str(ptype))
    head = f'{nm} status=0x{status:x} {len(data)} bytes'
    if ptype == 18:
        if data[:1] and 20 <= data[0] <= 23:
            out(cid, d, head + ' (TLS handshake records)')
        else:
            out(cid, d, head + ' ' + prelogin(data))
        return
    if ptype == 1:
        hl = u32(data, 0)
        out(cid, d, head + ' SQL: ' + utf16(data[hl:]))
        return
    if ptype == 3:
        hl = u32(data, 0)
        j = hl
        n = u16(data, j)
        if n == 0xFFFF:
            pid = u16(data, j + 2)
            out(cid, d, head + f' RPC proc id {pid}' + (f' params {data[j+6:j+200].hex()}' if HEX else ''))
        else:
            out(cid, d, head + f' RPC proc {utf16(data[j+2:j+2+2*n])!r}')
        return
    if ptype == 4 and data[:1] == b'\x00':
        out(cid, d, head + ' PRELOGIN answer ' + prelogin(data))
        return
    if ptype == 4:
        out(cid, d, head)
        tokens(data, cid, d)
        return
    out(cid, d, head + (' ' + data[:256].hex() if HEX else ''))


def pump(cid, d, src, dst):
    buf = b''
    msg = b''
    mtype = None
    try:
        while True:
            chunk = src.recv(65536)
            if not chunk: break
            dst.sendall(chunk)
            buf += chunk
            while True:
                if len(buf) >= 5 and 20 <= buf[0] <= 23:
                    n = struct.unpack_from('>H', buf, 3)[0]
                    if len(buf) < 5 + n: break
                    out(cid, d, f'TLS record type {buf[0]} {n} bytes')
                    buf = buf[5 + n:]
                    continue
                if len(buf) < 8: break
                n = struct.unpack_from('>H', buf, 2)[0]
                if n < 8:
                    out(cid, d, f'garbage: {buf[:16].hex()}')
                    buf = b''
                    break
                if len(buf) < n: break
                ptype, status = buf[0], buf[1]
                msg += buf[8:n]
                mtype = ptype
                buf = buf[n:]
                if status & 1:
                    message(cid, d, mtype, status, msg)
                    msg = b''
    except OSError:
        pass
    finally:
        try: dst.shutdown(socket.SHUT_WR)
        except OSError: pass


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    lh, lp = args[0].rsplit(':', 1)
    th, tp = args[1].rsplit(':', 1)
    ls = socket.socket()
    ls.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    ls.bind((lh, int(lp)))
    ls.listen(16)
    print(f'proxy {args[0]} -> {args[1]}', flush=True)
    cid = 0
    while True:
        c, _ = ls.accept()
        cid += 1
        s = socket.create_connection((th, int(tp)))
        threading.Thread(target=pump, args=(cid, 'C>', c, s), daemon=True).start()
        threading.Thread(target=pump, args=(cid, '<S', s, c), daemon=True).start()


if __name__ == '__main__':
    main()
