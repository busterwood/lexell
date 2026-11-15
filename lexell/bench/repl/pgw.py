# pgw.py: a minimal PostgreSQL wire client (simple query, trust auth, Unix socket) for the lag probe
import socket, struct
class Conn:
    def __init__(self, sockdir, port, user='test', db='test'):
        self.s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.s.connect('%s/.s.PGSQL.%d' % (sockdir, port))
        body = struct.pack('!I', 196608) + b'user\0' + user.encode() + b'\0database\0' + db.encode() + b'\0\0'
        self.s.sendall(struct.pack('!I', len(body) + 4) + body)
        self.buf = b''
        while True:
            t, m = self._msg()
            if t == b'E': raise RuntimeError(m)
            if t == b'Z': break
    def _read(self, n):
        while len(self.buf) < n:
            d = self.s.recv(65536)
            if not d: raise EOFError
            self.buf += d
        r, self.buf = self.buf[:n], self.buf[n:]; return r
    def _msg(self):
        h = self._read(5); n = struct.unpack('!I', h[1:5])[0]
        return h[:1], self._read(n - 4)
    def query(self, sql):
        b = sql.encode() + b'\0'
        self.s.sendall(b'Q' + struct.pack('!I', len(b) + 4) + b)
        rows, err = [], None
        while True:
            t, m = self._msg()
            if t == b'D':
                nf = struct.unpack('!H', m[:2])[0]; at = 2; row = []
                for _ in range(nf):
                    l = struct.unpack('!i', m[at:at+4])[0]; at += 4
                    if l < 0: row.append(None)
                    else: row.append(m[at:at+l].decode()); at += l
                rows.append(row)
            elif t == b'E': err = m
            elif t == b'Z':
                if err: raise RuntimeError(err)
                return rows
