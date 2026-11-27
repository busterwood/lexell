#!/usr/bin/env python3
"""Generate lexell/lib/hpack_data.lxl from RFC 7541 Appendix A & B."""
import os

STATIC_TABLE = [
    ("", ""),  # 0: unused (1-based indexing)
    (":authority", ""),
    (":method", "GET"),
    (":method", "POST"),
    (":path", "/"),
    (":path", "/index.html"),
    (":scheme", "http"),
    (":scheme", "https"),
    (":status", "200"),
    (":status", "204"),
    (":status", "206"),
    (":status", "304"),
    (":status", "400"),
    (":status", "404"),
    (":status", "500"),
    ("accept-charset", ""),
    ("accept-encoding", "gzip, deflate"),
    ("accept-language", ""),
    ("accept-ranges", ""),
    ("accept", ""),
    ("access-control-allow-origin", ""),
    ("age", ""),
    ("allow", ""),
    ("authorization", ""),
    ("cache-control", ""),
    ("content-disposition", ""),
    ("content-encoding", ""),
    ("content-language", ""),
    ("content-length", ""),
    ("content-location", ""),
    ("content-range", ""),
    ("content-type", ""),
    ("cookie", ""),
    ("date", ""),
    ("etag", ""),
    ("expect", ""),
    ("expires", ""),
    ("from", ""),
    ("host", ""),
    ("if-match", ""),
    ("if-modified-since", ""),
    ("if-none-match", ""),
    ("if-range", ""),
    ("if-unmodified-since", ""),
    ("last-modified", ""),
    ("link", ""),
    ("location", ""),
    ("max-forwards", ""),
    ("proxy-authenticate", ""),
    ("proxy-authorization", ""),
    ("range", ""),
    ("referer", ""),
    ("refresh", ""),
    ("retry-after", ""),
    ("server", ""),
    ("set-cookie", ""),
    ("strict-transport-security", ""),
    ("transfer-encoding", ""),
    ("user-agent", ""),
    ("vary", ""),
    ("via", ""),
    ("www-authenticate", ""),
]

HUFFMAN_CODES = [
    0x1ff8, 0x7fffd8, 0xfffffe2, 0xfffffe3, 0xfffffe4, 0xfffffe5, 0xfffffe6, 0xfffffe7,
    0xfffffe8, 0xffffea, 0x3ffffffc, 0xfffffe9, 0xfffffea, 0x3ffffffd, 0xfffffeb, 0xfffffec,
    0xfffffed, 0xfffffee, 0xfffffef, 0xffffff0, 0xffffff1, 0xffffff2, 0x3ffffffe, 0xffffff3,
    0xffffff4, 0xffffff5, 0xffffff6, 0xffffff7, 0xffffff8, 0xffffff9, 0xffffffa, 0xffffffb,
    0x14, 0x3f8, 0x3f9, 0xffa, 0x1ff9, 0x15, 0xf8, 0x7fa,
    0x3fa, 0x3fb, 0xf9, 0x7fb, 0xfa, 0x16, 0x17, 0x18,
    0x0, 0x1, 0x2, 0x19, 0x1a, 0x1b, 0x1c, 0x1d,
    0x1e, 0x1f, 0x5c, 0xfb, 0x7ffc, 0x20, 0xffb, 0x3fc,
    0x1ffa, 0x21, 0x5d, 0x5e, 0x5f, 0x60, 0x61, 0x62,
    0x63, 0x64, 0x65, 0x66, 0x67, 0x68, 0x69, 0x6a,
    0x6b, 0x6c, 0x6d, 0x6e, 0x6f, 0x70, 0x71, 0x72,
    0xfc, 0x73, 0xfd, 0x1ffb, 0x7fff0, 0x1ffc, 0x3ffc, 0x22,
    0x7ffd, 0x3, 0x23, 0x4, 0x24, 0x5, 0x25, 0x26,
    0x27, 0x6, 0x74, 0x75, 0x28, 0x29, 0x2a, 0x7,
    0x2b, 0x76, 0x2c, 0x8, 0x9, 0x2d, 0x77, 0x78,
    0x79, 0x7a, 0x7b, 0x7ffe, 0x7fc, 0x3ffd, 0x1ffd, 0xffffffc,
    0xfffe6, 0x3fffd2, 0xfffe7, 0xfffe8, 0x3fffd3, 0x3fffd4, 0x3fffd5, 0x7fffd9,
    0x3fffd6, 0x7fffda, 0x7fffdb, 0x7fffdc, 0x7fffdd, 0x7fffde, 0xffffeb, 0x7fffdf,
    0xffffec, 0xffffed, 0x3fffd7, 0x7fffe0, 0xffffee, 0x7fffe1, 0x7fffe2, 0x7fffe3,
    0x7fffe4, 0x1fffdc, 0x3fffd8, 0x7fffe5, 0x3fffd9, 0x7fffe6, 0x7fffe7, 0xffffef,
    0x3fffda, 0x1fffdd, 0xfffe9, 0x3fffdb, 0x3fffdc, 0x7fffe8, 0x7fffe9, 0x1fffde,
    0x7fffea, 0x3fffdd, 0x3fffde, 0xfffff0, 0x1fffdf, 0x3fffdf, 0x7fffeb, 0x7fffec,
    0x1fffe0, 0x1fffe1, 0x3fffe0, 0x1fffe2, 0x7fffed, 0x3fffe1, 0x7fffee, 0x7fffef,
    0xfffea, 0x3fffe2, 0x3fffe3, 0x3fffe4, 0x7ffff0, 0x3fffe5, 0x3fffe6, 0x7ffff1,
    0x3ffffe0, 0x3ffffe1, 0xfffeb, 0x7fff1, 0x3fffe7, 0x7ffff2, 0x3fffe8, 0x1ffffec,
    0x3ffffe2, 0x3ffffe3, 0x3ffffe4, 0x7ffffde, 0x7ffffdf, 0x3ffffe5, 0xfffff1, 0x1ffffed,
    0x7fff2, 0x1fffe3, 0x3ffffe6, 0x7ffffe0, 0x7ffffe1, 0x3ffffe7, 0x7ffffe2, 0xfffff2,
    0x1fffe4, 0x1fffe5, 0x3ffffe8, 0x3ffffe9, 0xffffffd, 0x7ffffe3, 0x7ffffe4, 0x7ffffe5,
    0xfffec, 0xfffff3, 0xfffed, 0x1fffe6, 0x3fffe9, 0x1fffe7, 0x1fffe8, 0x7ffff3,
    0x3fffea, 0x3fffeb, 0x1ffffee, 0x1ffffef, 0xfffff4, 0xfffff5, 0x3ffffea, 0x7ffff4,
    0x3ffffeb, 0x7ffffe6, 0x3ffffec, 0x3ffffed, 0x7ffffe7, 0x7ffffe8, 0x7ffffe9, 0x7ffffea,
    0x7ffffeb, 0xffffffe, 0x7ffffec, 0x7ffffed, 0x7ffffee, 0x7ffffef, 0x7fffff0, 0x3ffffee,
]

HUFFMAN_LENS = [
    13, 23, 28, 28, 28, 28, 28, 28, 28, 24, 30, 28, 28, 30, 28, 28,
    28, 28, 28, 28, 28, 28, 30, 28, 28, 28, 28, 28, 28, 28, 28, 28,
    6, 10, 10, 12, 13, 6, 8, 11, 10, 10, 8, 11, 8, 6, 6, 6,
    5, 5, 5, 6, 6, 6, 6, 6, 6, 6, 7, 8, 15, 6, 12, 10,
    13, 6, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7, 7,
    7, 7, 7, 7, 7, 7, 7, 7, 8, 7, 8, 13, 19, 13, 14, 6,
    15, 5, 6, 5, 6, 5, 6, 6, 6, 5, 7, 7, 6, 6, 6, 5,
    6, 7, 6, 5, 5, 6, 7, 7, 7, 7, 7, 15, 11, 14, 13, 28,
    20, 22, 20, 20, 22, 22, 22, 23, 22, 23, 23, 23, 23, 23, 24, 23,
    24, 24, 22, 23, 24, 23, 23, 23, 23, 21, 22, 23, 22, 23, 23, 24,
    22, 21, 20, 22, 22, 23, 23, 21, 23, 22, 22, 24, 21, 22, 23, 23,
    21, 21, 22, 21, 23, 22, 23, 23, 20, 22, 22, 22, 23, 22, 22, 23,
    26, 26, 20, 19, 22, 23, 22, 25, 26, 26, 26, 27, 27, 26, 24, 25,
    19, 21, 26, 27, 27, 26, 27, 24, 21, 21, 26, 26, 28, 27, 27, 27,
    20, 24, 20, 21, 22, 21, 21, 23, 22, 22, 25, 25, 24, 24, 26, 23,
    26, 27, 26, 26, 27, 27, 27, 27, 27, 28, 27, 27, 27, 27, 27, 26,
]

assert len(STATIC_TABLE) == 62
assert len(HUFFMAN_CODES) == 256
assert len(HUFFMAN_LENS) == 256
assert min(HUFFMAN_LENS) == 5

class Node:
    def __init__(self, depth=0, all_ones=True):
        self.children = [None, None]
        self.sym = -1
        self.id = -1
        self.depth = depth
        self.all_ones = all_ones

root = Node(0, True)

def insert(code, nbits, sym):
    cur = root
    for i in range(nbits - 1, -1, -1):
        b = (code >> i) & 1
        if cur.children[b] is None:
            cur.children[b] = Node(cur.depth + 1, cur.all_ones and (b == 1))
        cur = cur.children[b]
    assert cur.sym == -1
    cur.sym = sym

for sym in range(256):
    insert(HUFFMAN_CODES[sym], HUFFMAN_LENS[sym], sym)
insert(0x3fffffff, 30, 256)  # EOS

# Collect all internal nodes in BFS order (root = 0)
internals = []
queue = [root]
while queue:
    n = queue.pop(0)
    if n.sym != -1:
        continue
    n.id = len(internals)
    internals.append(n)
    assert n.children[0] is not None and n.children[1] is not None
    queue.append(n.children[0])
    queue.append(n.children[1])

assert len(internals) == 256  # 257 leaves -> 256 internal nodes

# Build 4-bit nibble DFA: state * 16 + nib -> packed i32:
#   bits 0..7:  next_state (0..255)
#   bits 8..15: sym (0..255)
#   bit 16:     EMIT (0x10000)
#   bit 17:     FAIL (0x20000) - hit EOS
EMIT = 0x10000
FAIL = 0x20000

dfa = []
accept = []
for n in internals:
    # Valid end state iff depth <= 7 and path from root is all 1-bits (RFC 7541 5.2)
    accept.append(1 if (n.all_ones and n.depth <= 7) else 0)
    for nib in range(16):
        cur = n
        emitted = -1
        failed = False
        for shift in (3, 2, 1, 0):
            b = (nib >> shift) & 1
            cur = cur.children[b]
            if cur.sym != -1:
                if cur.sym == 256:
                    failed = True
                    break
                assert emitted == -1
                emitted = cur.sym
                cur = root
        if failed:
            dfa.append(FAIL)
        else:
            val = cur.id
            if emitted >= 0:
                val |= EMIT | (emitted << 8)
            dfa.append(val)

assert len(dfa) == 256 * 16
assert sum(accept) == 8  # depths 0..7 along all-1s spine

out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hpack_data.lxl")

def fmt_list(vals, per_line, fmt=str):
    lines = []
    for i in range(0, len(vals), per_line):
        lines.append("    " + ", ".join(fmt(v) for v in vals[i:i+per_line]) + ",")
    return "\n".join(lines)

def esc(s):
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'

with open(out_path, "w") as f:
    f.write("// hpack_data: RFC 7541 Appendix A static table and Appendix B Huffman tables\n")
    f.write("// (generated by lexell/lib/gen_hpack_data.py; do not edit).\n\n")
    f.write("pub const STATIC_COUNT = 61\n")
    f.write("pub const STATIC_NAME: []str = [\n")
    f.write(fmt_list([k for k, _ in STATIC_TABLE], 4, esc) + "\n]\n\n")
    f.write("pub const STATIC_VAL: []str = [\n")
    f.write(fmt_list([v for _, v in STATIC_TABLE], 4, esc) + "\n]\n\n")
    f.write("pub const HUFF_CODE: []u32 = [\n")
    f.write(fmt_list(HUFFMAN_CODES, 8, lambda v: f"0x{v:x}") + "\n]\n\n")
    f.write("pub const HUFF_LEN: []byte = [\n")
    f.write(fmt_list(HUFFMAN_LENS, 16, str) + "\n]\n\n")
    f.write("// 4-bit nibble Huffman decode DFA (256 states x 16 nibbles = 4096 entries).\n")
    f.write("// Entry bits: 0..7 next state, 8..15 emitted byte, bit 16 EMIT, bit 17 FAIL (EOS).\n")
    f.write("pub const HUFF_EMIT = 0x10000\n")
    f.write("pub const HUFF_FAIL = 0x20000\n")
    f.write("pub const HUFF_DFA: []i32 = [\n")
    f.write(fmt_list(dfa, 12, lambda v: f"0x{v:x}") + "\n]\n\n")
    f.write("// 1 when the DFA state is a valid end-of-string padding state (0..7 trailing 1-bits).\n")
    f.write("pub const HUFF_ACCEPT: []byte = [\n")
    f.write(fmt_list(accept, 32, str) + "\n]\n")

print(f"wrote {out_path} ({len(dfa)} DFA entries, {sum(accept)} accept states)")
