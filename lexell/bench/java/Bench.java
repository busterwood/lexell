// Java ports of lexell/bench/*.lxl, the same work and checksums (bench.py's Java column). Int
// arithmetic that Lexell checks uses Math.addExact / multiplyExact, so overflow traps alike.
// Usage: java Bench NAME [tokens-input]. Prints the checksum line, then "cold <ms>" (the first
// run in this JVM, startup excluded) and "warm <ms>": the best of -Dbench.runs (default 5) runs
// after one more warm-up run, so the JIT has compiled the hot code (C2, default tiered).
import java.nio.file.*;
import java.util.*;

public class Bench {
    static String tokensInput;

    // fib
    static long fib(long n) { return n < 2 ? n : Math.addExact(fib(n - 1), fib(n - 2)); }
    static String fibMain() { return Long.toString(fib(42)); }

    // loop
    static String loopMain() {
        long n = 2000000000L, s = 0, i = 0;
        while (i < n) { s = Math.addExact(s, Math.multiplyExact(i, 2L)); i = Math.addExact(i, 1L); }
        return Long.toString(s);
    }

    // array
    static String arrayMain() {
        int n = 1000000;
        long[] a = new long[0];
        int len = 0;
        for (int i = 0; i < n; i++) {               // append with doubling, as []int does
            if (len == a.length) a = Arrays.copyOf(a, Math.max(4, a.length * 2));
            a[len++] = i;
        }
        long total = 0;
        for (long r = 0; r < 800; r++) {
            for (int i = 0; i < n; i++) {
                if (i >= len) throw new IndexOutOfBoundsException();
                a[i] = Math.addExact(a[i], r);
                total = Math.addExact(total, a[i]);
            }
        }
        return Long.toString(total);
    }

    // alloc
    static final class Cell { final long v, w; Cell(long v, long w) { this.v = v; this.w = w; } }
    static String allocMain() {
        long n = 80000000L, total = 0;
        for (long i = 0; i < n; i++) {
            Cell c = new Cell(i, 2);
            total = Math.addExact(Math.addExact(total, c.v), c.w);
        }
        return Long.toString(total);
    }

    // lists
    static final class Node { final long value; final Node next; Node(long v, Node n) { value = v; next = n; } }
    static long sum(Node l) { return l == null ? 0 : Math.addExact(l.value, sum(l.next)); }
    static String listsMain() {
        Node keep = null;
        for (long i = 0; i < 1000; i++) keep = new Node(i, keep);
        long total = 0;
        for (int round = 0; round < 2000; round++) {
            Node l = null;
            for (long i = 0; i < 10000; i++) l = new Node(i, l);
            total = Math.addExact(total, sum(l) % 7);
        }
        return Long.toString(Math.addExact(total, sum(keep)));
    }

    // strings
    static String stringsMain() {
        ArrayList<String> keep = new ArrayList<>();
        for (long i = 0; i < 1000; i++) keep.add("k" + i);
        long total = 0;
        for (long round = 0; round < 1000; round++) {
            ArrayList<String> words = new ArrayList<>();
            for (long i = 0; i < 5000; i++) words.add("word" + i + "-" + round);
            for (String w : words) total = Math.addExact(total, (long) w.length());
        }
        return Long.toString(total);
    }

    // trees
    static final class Tree { final Tree left, right; Tree(Tree l, Tree r) { left = l; right = r; } }
    static Tree build(int d) { return d == 0 ? new Tree(null, null) : new Tree(build(d - 1), build(d - 1)); }
    static long check(Tree t) {
        long n = 1;
        if (t.left != null) n = Math.addExact(n, check(t.left));
        if (t.right != null) n = Math.addExact(n, check(t.right));
        return n;
    }
    static String treesMain() {
        Tree lng = build(16);
        long total = 0;
        for (int i = 0; i < 400; i++) { Tree t = build(14); total = Math.addExact(total, check(t)); }
        return Long.toString(Math.addExact(total, check(lng)));
    }

    // tokens
    record Token(int kind, String text, long line) {}
    static boolean isLetter(int c) { return c >= 'a' && c <= 'z' || c >= 'A' && c <= 'Z' || c == '_'; }
    static boolean isDigit(int c) { return c >= '0' && c <= '9'; }
    static ArrayList<Token> scan(byte[] src) {
        ArrayList<Token> toks = new ArrayList<>();
        int i = 0; long line = 1; int n = src.length;
        while (i < n) {
            int c = src[i] & 0xff;
            if (c == '\n') { line++; i++; }
            else if (isLetter(c)) {
                int start = i;
                while (i < n && (isLetter(src[i] & 0xff) || isDigit(src[i] & 0xff))) i++;
                toks.add(new Token(1, new String(src, start, i - start, java.nio.charset.StandardCharsets.ISO_8859_1), line));
            } else if (isDigit(c)) {
                while (i < n && isDigit(src[i] & 0xff)) i++;
                toks.add(new Token(2, "", line));
            } else if (c == ' ' || c == '\t') i++;
            else { toks.add(new Token(3, "", line)); i++; }
        }
        return toks;
    }
    static int hash(String s) {
        int h = 5381;
        for (int i = 0; i < s.length(); i++) h = (h * 33 + s.charAt(i)) & 0xFFFFFF;
        return h;
    }
    static byte[] tokData;
    static String tokensMain() {
        long tokens = 0, unique = 0;
        for (int round = 0; round < 200; round++) {
            ArrayList<Token> toks = scan(tokData);
            ArrayList<ArrayList<String>> table = new ArrayList<>();
            ArrayList<String> b0 = new ArrayList<>(); b0.add(""); table.add(b0);
            for (int i = 1; i < 1024; i++) table.add(new ArrayList<>());
            for (Token t : toks) {
                if (t.kind() == 1) {
                    int k = hash(t.text()) % table.size();
                    boolean found = false;
                    for (String name : table.get(k)) if (name.equals(t.text())) { found = true; break; }
                    if (!found) { table.get(k).add(t.text()); unique++; }
                }
            }
            tokens += toks.size();
        }
        return tokens + " " + unique;
    }

    // sieve
    static String sieveMain() {
        int n = 10000000;
        long count = 0;
        for (int round = 0; round < 30; round++) {
            boolean[] prime = new boolean[n + 1];
            Arrays.fill(prime, true);
            prime[0] = false; prime[1] = false;
            for (long i = 2; Math.multiplyExact(i, i) <= n; i = Math.addExact(i, 1)) {
                if (prime[(int) i]) {
                    for (long j = i * i; j <= n; j = Math.addExact(j, i)) prime[(int) j] = false;
                }
            }
            count = 0;
            for (int k = 0; k < n + 1; k++) if (prime[k]) count++;
        }
        return Long.toString(count);
    }

    // maps
    static final int N = 400000;
    static final String PAD = "a fairly long common prefix for every key of the table: ";
    static long strRound(ArrayList<String> keys, ArrayList<String> miss) {
        HashMap<String, Long> m = new HashMap<>();
        for (int i = 0; i < keys.size(); i++) m.put(new String(keys.get(i)), (long) i);
        long sum = 0;
        for (int r = 0; r < 4; r++) for (String k : keys) sum = Math.addExact(sum, m.getOrDefault(k, -1L));
        for (String k : miss) if (m.containsKey(k)) sum++;
        return sum + m.size();
    }
    static long intRound(int n) {
        HashMap<Long, Long> m = new HashMap<>();
        for (long i = 0; i < n; i++) m.put(i * 4096, i);
        long sum = 0;
        for (int r = 0; r < 4; r++) for (long i = 0; i < n; i++) sum = Math.addExact(sum, m.getOrDefault(i * 4096, -1L));
        for (long i = 0; i < n; i++) if (m.containsKey(i * 4096 + 1)) sum++;
        return sum + m.size();
    }
    static String mapsMain() {
        ArrayList<String> sh = new ArrayList<>(), lg = new ArrayList<>(), shm = new ArrayList<>(), lgm = new ArrayList<>();
        for (long i = 0; i < N; i++) {
            sh.add("k" + (i * 7919)); lg.add(PAD + i); shm.add("m" + i); lgm.add(PAD + "x" + i);
        }
        return strRound(sh, shm) + " " + strRound(lg, lgm) + " " + intRound(N);
    }

    // nbody
    static final class Body { double x, y, z, vx, vy, vz, mass;
        Body(double x, double y, double z, double vx, double vy, double vz, double mass) {
            this.x = x; this.y = y; this.z = z; this.vx = vx; this.vy = vy; this.vz = vz; this.mass = mass; } }
    static final double SOLAR = 39.47841760435743, DPY = 365.24;
    static Body[] nbodyBodies() {
        Body[] bs = {
            new Body(0, 0, 0, 0, 0, 0, SOLAR),
            new Body(4.84143144246472090e+00, -1.16032004402742839e+00, -1.03622044471123109e-01,
                1.66007664274403694e-03 * DPY, 7.69901118419740425e-03 * DPY, -6.90460016972063023e-05 * DPY, 9.54791938424326609e-04 * SOLAR),
            new Body(8.34336671824457987e+00, 4.12479856412430479e+00, -4.03523417114321381e-01,
                -2.76742510726862411e-03 * DPY, 4.99852801234917238e-03 * DPY, 2.30417297573763929e-05 * DPY, 2.85885980666130812e-04 * SOLAR),
            new Body(1.28943695621391310e+01, -1.51111514016986312e+01, -2.23307578892655734e-01,
                2.96460137564761618e-03 * DPY, 2.37847173959480950e-03 * DPY, -2.96589568540237556e-05 * DPY, 4.36624404335156298e-05 * SOLAR),
            new Body(1.53796971148509165e+01, -2.59193146099879641e+01, 1.79258772950371181e-01,
                2.68067772490389322e-03 * DPY, 1.62824170038242295e-03 * DPY, -9.51592254519715870e-05 * DPY, 5.15138902046611451e-05 * SOLAR)};
        double px = 0, py = 0, pz = 0;
        for (Body b : bs) { px += b.vx * b.mass; py += b.vy * b.mass; pz += b.vz * b.mass; }
        bs[0].vx = -px / SOLAR; bs[0].vy = -py / SOLAR; bs[0].vz = -pz / SOLAR;
        return bs;
    }
    static void nbodyAdvance(Body[] bs, double dt) {
        int n = bs.length;
        for (int i = 0; i < n; i++) {
            for (int j = i + 1; j < n; j++) {
                double dx = bs[i].x - bs[j].x, dy = bs[i].y - bs[j].y, dz = bs[i].z - bs[j].z;
                double d2 = dx * dx + dy * dy + dz * dz;
                double mag = dt / (d2 * Math.sqrt(d2));
                double mj = bs[j].mass * mag;
                bs[i].vx -= dx * mj; bs[i].vy -= dy * mj; bs[i].vz -= dz * mj;
                double mi = bs[i].mass * mag;
                bs[j].vx += dx * mi; bs[j].vy += dy * mi; bs[j].vz += dz * mi;
            }
        }
        for (Body b : bs) { b.x += dt * b.vx; b.y += dt * b.vy; b.z += dt * b.vz; }
    }
    static double nbodyEnergy(Body[] bs) {
        double e = 0;
        int n = bs.length;
        for (int i = 0; i < n; i++) {
            Body b = bs[i];
            e += 0.5 * b.mass * (b.vx * b.vx + b.vy * b.vy + b.vz * b.vz);
            for (int j = i + 1; j < n; j++) {
                double dx = b.x - bs[j].x, dy = b.y - bs[j].y, dz = b.z - bs[j].z;
                e -= b.mass * bs[j].mass / Math.sqrt(dx * dx + dy * dy + dz * dz);
            }
        }
        return e;
    }
    static String nbodyMain() {
        Body[] bs = nbodyBodies();
        long before = (long) (nbodyEnergy(bs) * 1e9);
        for (int s = 0; s < 5000000; s++) nbodyAdvance(bs, 0.01);
        return before + " " + (long) (nbodyEnergy(bs) * 1e9);
    }

    // interp
    sealed interface Op permits Push, Load, Store, Add, Mul, Mod, Lt, Jz, Jmp, Halt {}
    record Push(long v) implements Op {}
    record Load(int k) implements Op {}
    record Store(int k) implements Op {}
    record Add() implements Op {}
    record Mul() implements Op {}
    record Mod() implements Op {}
    record Lt() implements Op {}
    record Jz(int t) implements Op {}
    record Jmp(int t) implements Op {}
    record Halt() implements Op {}
    static long interpRun(Op[] code, long n) {
        long[] stack = new long[16];
        int sp = 0;
        long[] locals = {0, 0, n};
        int pc = 0;
        while (true) {
            switch (code[pc]) {
                case Push p -> { stack[sp++] = p.v(); pc++; }
                case Load l -> { stack[sp++] = locals[l.k()]; pc++; }
                case Store st -> { locals[st.k()] = stack[--sp]; pc++; }
                case Add a -> { sp--; stack[sp - 1] = Math.addExact(stack[sp - 1], stack[sp]); pc++; }
                case Mul m -> { sp--; stack[sp - 1] = Math.multiplyExact(stack[sp - 1], stack[sp]); pc++; }
                case Mod m -> { sp--; stack[sp - 1] = stack[sp - 1] % stack[sp]; pc++; }
                case Lt l -> { sp--; stack[sp - 1] = stack[sp - 1] < stack[sp] ? 1 : 0; pc++; }
                case Jz z -> { sp--; pc = stack[sp] == 0 ? z.t() : pc + 1; }
                case Jmp j -> pc = j.t();
                case Halt h -> { return locals[1]; }
            }
        }
    }
    static String interpMain() {
        Op[] code = { new Load(0), new Load(2), new Lt(), new Jz(17),
            new Load(1), new Load(0), new Load(0), new Mul(), new Push(7), new Mod(),
            new Add(), new Store(1),
            new Load(0), new Push(1), new Add(), new Store(0),
            new Jmp(0), new Halt() };
        return Long.toString(interpRun(code, 10000000));
    }

    // closures
    record Rec(long key, String name) {}
    static long closuresDigest(List<Rec> rs) {
        long h = 0;
        for (Rec r : rs) h = Math.addExact(Math.multiplyExact(h, 31L), r.key()) % 1000000007L;
        return h;
    }
    static String closuresMain() {
        int n = 200000;
        ArrayList<Rec> rs = new ArrayList<>();
        long x = 12345;
        for (int i = 0; i < n; i++) {
            x = Math.addExact(Math.multiplyExact(x, 1103515245L), 12345L) % 2147483648L;
            rs.add(new Rec(x % 1000000, "n" + (x / 1000 % 50000)));
        }
        rs.sort((a, b) -> Long.compare(a.key(), b.key()));
        long h1 = closuresDigest(rs);
        rs.sort((a, b) -> { int c = a.name().compareTo(b.name()); return c != 0 ? Integer.signum(c) : Long.compare(a.key(), b.key()); });
        long h2 = closuresDigest(rs);
        int dir = -1;
        rs.sort((a, b) -> dir * Long.compare(a.key(), b.key()));
        long h3 = closuresDigest(rs);
        java.util.function.LongUnaryOperator[] fs = { v -> Math.addExact(v, 1L), v -> Math.multiplyExact(v, 3L), v -> v % 1000, v -> v / 7 };
        long t = 0;
        for (int round = 0; round < 20; round++)
            for (int i = 0; i < n; i++) t = Math.addExact(t, fs[(i + round) % 4].applyAsLong(rs.get(i).key()));
        return h1 + " " + h2 + " " + h3 + " " + t;
    }

    // matmul
    static double[][] matmulMatrix(int n, int seed) {
        double[][] m = new double[n][n];
        for (int i = 0; i < n; i++) for (int j = 0; j < n; j++) m[i][j] = (i * seed + j * 7) % 11 - 5;
        return m;
    }
    static double[][] matmulMul(double[][] a, double[][] b, int n) {
        double[][] c = new double[n][];
        for (int i = 0; i < n; i++) {
            double[] row = new double[n];
            for (int k = 0; k < n; k++) {
                double aik = a[i][k];
                double[] bk = b[k];
                for (int j = 0; j < n; j++) row[j] += aik * bk[j];
            }
            c[i] = row;
        }
        return c;
    }
    static String matmulMain() {
        int n = 400;
        double[][] a = matmulMatrix(n, 3), b = matmulMatrix(n, 5);
        long total = 0;
        for (int r = 0; r < 5; r++) {
            double[][] c = matmulMul(a, b, n);
            double s = 0;
            for (int i = 0; i < n; i++) for (int j = 0; j < n; j++) s += c[i][j] * ((i * n + j) % 13 + r);
            total += (long) s;
        }
        return Long.toString(total);
    }

    // pingpong: two virtual threads hand a counter back and forth through SynchronousQueues
    static String pingpongMain() {
        int n = 2000000;
        java.util.concurrent.SynchronousQueue<Long> toPong = new java.util.concurrent.SynchronousQueue<>();
        java.util.concurrent.SynchronousQueue<Long> toPing = new java.util.concurrent.SynchronousQueue<>();
        long[] count = {0};
        Thread pong = Thread.ofVirtual().start(() -> {
            try {
                while (true) {
                    long m = toPong.take();
                    if (m < 0) return;
                    toPing.put(m + 1);
                    count[0]++;
                }
            } catch (InterruptedException e) { throw new RuntimeException(e); }
        });
        long total = 0;
        try {
            for (long i = 0; i < n; i++) {
                toPong.put(i * 2);
                total = Math.addExact(total, toPing.take());
            }
            toPong.put(-1L);
            pong.join();
        } catch (InterruptedException e) { throw new RuntimeException(e); }
        return total + " " + count[0];
    }

    // bitpack
    static byte[] packCol(long[] vals, int bits) {
        int n = vals.length;
        byte[] out = new byte[(n * bits + 7) / 8 + 8];
        int bitPos = 0;
        for (int i = 0; i < n; i++) {
            long v = vals[i];
            int b = 0;
            while (b < bits) {
                int byteIdx = (bitPos + b) >> 3;
                int bitOff = (bitPos + b) & 7;
                int take = 8 - bitOff;
                int rem = bits - b;
                int k = Math.min(take, rem);
                long mask = (1L << k) - 1;
                long chunk = (v >> b) & mask;
                out[byteIdx] = (byte) ((out[byteIdx] & 0xFFL) | (chunk << bitOff));
                b += k;
            }
            bitPos += bits;
        }
        return out;
    }
    static void unpackBatch(byte[] buf, int startIdx, int count, int bits, long baseVal, long[] dst) {
        long mask = (1L << bits) - 1;
        int bitPos = startIdx * bits;
        for (int i = 0; i < count; i++) {
            int byteIdx = bitPos >> 3;
            int bitOff = bitPos & 7;
            long w = (buf[byteIdx] & 0xFFL)
                | ((buf[byteIdx + 1] & 0xFFL) << 8)
                | ((buf[byteIdx + 2] & 0xFFL) << 16)
                | ((buf[byteIdx + 3] & 0xFFL) << 24);
            dst[i] = Math.addExact(baseVal, (w >> bitOff) & mask);
            bitPos += bits;
        }
    }
    static String bitpackMain() {
        int n = 1000000, batch = 1024;
        long[] rawQty = new long[n], rawDisc = new long[n], rawPrice = new long[n];
        long s = 123456789L;
        for (int i = 0; i < n; i++) {
            s = (s * 6364136223846793005L + 1442695040888963407L) & 4611686018427387903L;
            rawQty[i] = (s >> 16) & 63;
            rawDisc[i] = (s >> 24) & 15;
            rawPrice[i] = (s >> 30) & 131071;
        }
        byte[] pQty = packCol(rawQty, 6), pDisc = packCol(rawDisc, 4), pPrice = packCol(rawPrice, 17);
        long[] qty = new long[batch], disc = new long[batch], price = new long[batch];
        int[] sel = new int[batch];
        long total = 0;
        for (long round = 0; round < 60; round++) {
            long loDisc = 4 + (round & 3), hiDisc = loDisc + 4, maxQty = 30 + (round & 7);
            int pos = 0;
            while (pos < n) {
                int cnt = Math.min(batch, n - pos);
                unpackBatch(pQty, pos, cnt, 6, 1, qty);
                unpackBatch(pDisc, pos, cnt, 4, 0, disc);
                unpackBatch(pPrice, pos, cnt, 17, 90000, price);
                int nsel = 0;
                for (int i = 0; i < cnt; i++) {
                    long d = disc[i];
                    if (d >= loDisc && d <= hiDisc && qty[i] < maxQty) sel[nsel++] = i;
                }
                long acc = 0;
                for (int j = 0; j < nsel; j++) {
                    int idx = sel[j];
                    acc = Math.addExact(acc, Math.multiplyExact(price[idx], disc[idx]));
                }
                total = Math.addExact(total, acc);
                pos += cnt;
            }
        }
        return Long.toString(total);
    }

    // btree
    static final int BT_MAX_KEYS = 31, BT_MID = 15;
    static final class BtNode {
        boolean leaf;
        long[] keys = new long[4]; int nkeys = 0;
        long[] vals = new long[4]; int nvals = 0;
        BtNode[] kids = new BtNode[0]; int nkids = 0;
        BtNode(boolean leaf) { this.leaf = leaf; }
        void insertKey(int pos, long k) {
            if (nkeys == keys.length) keys = Arrays.copyOf(keys, Math.max(4, keys.length * 2));
            System.arraycopy(keys, pos, keys, pos + 1, nkeys - pos);
            keys[pos] = k; nkeys++;
        }
        void insertVal(int pos, long v) {
            if (nvals == vals.length) vals = Arrays.copyOf(vals, Math.max(4, vals.length * 2));
            System.arraycopy(vals, pos, vals, pos + 1, nvals - pos);
            vals[pos] = v; nvals++;
        }
        void insertKid(int pos, BtNode c) {
            if (nkids == kids.length) kids = Arrays.copyOf(kids, Math.max(4, kids.length * 2));
            System.arraycopy(kids, pos, kids, pos + 1, nkids - pos);
            kids[pos] = c; nkids++;
        }
    }
    static final class BtSplit {
        final boolean promoted; final long key; final BtNode right;
        BtSplit(boolean p, long k, BtNode r) { promoted = p; key = k; right = r; }
    }
    static final BtSplit NO_SPLIT = new BtSplit(false, 0, null);
    static int btLowerBound(long[] keys, int n, long key) {
        int lo = 0, hi = n;
        while (lo < hi) {
            int mid = (lo + hi) >> 1;
            if (keys[mid] < key) lo = mid + 1; else hi = mid;
        }
        return lo;
    }
    static long btSearch(BtNode cur, long key) {
        while (true) {
            int i = btLowerBound(cur.keys, cur.nkeys, key);
            if (cur.leaf) return (i < cur.nkeys && cur.keys[i] == key) ? cur.vals[i] : -1;
            cur = (i < cur.nkeys && cur.keys[i] == key) ? cur.kids[i + 1] : cur.kids[i];
        }
    }
    static long btRangeSum(BtNode node, long lo, long hi) {
        int i = btLowerBound(node.keys, node.nkeys, lo);
        long sum = 0;
        if (node.leaf) {
            for (int j = i; j < node.nkeys && node.keys[j] <= hi; j++) sum = Math.addExact(sum, node.vals[j]);
            return sum;
        }
        for (int j = i; j < node.nkeys; j++) {
            sum = Math.addExact(sum, btRangeSum(node.kids[j], lo, hi));
            if (node.keys[j] > hi) return sum;
        }
        return Math.addExact(sum, btRangeSum(node.kids[node.nkeys], lo, hi));
    }
    static BtSplit btInsertRec(BtNode node, long key, long val) {
        int pos = btLowerBound(node.keys, node.nkeys, key);
        if (node.leaf) {
            if (pos < node.nkeys && node.keys[pos] == key) { node.vals[pos] = val; return NO_SPLIT; }
            node.insertKey(pos, key);
            node.insertVal(pos, val);
            if (node.nkeys <= BT_MAX_KEYS) return NO_SPLIT;
            BtNode rn = new BtNode(true);
            int rc = node.nkeys - BT_MID;
            rn.keys = Arrays.copyOfRange(node.keys, BT_MID, node.nkeys); rn.nkeys = rc;
            rn.vals = Arrays.copyOfRange(node.vals, BT_MID, node.nvals); rn.nvals = rc;
            node.nkeys = BT_MID; node.nvals = BT_MID;
            return new BtSplit(true, rn.keys[0], rn);
        }
        int ci = (pos < node.nkeys && node.keys[pos] == key) ? pos + 1 : pos;
        BtSplit sp = btInsertRec(node.kids[ci], key, val);
        if (!sp.promoted) return sp;
        node.insertKey(ci, sp.key);
        node.insertKid(ci + 1, sp.right);
        if (node.nkeys <= BT_MAX_KEYS) return NO_SPLIT;
        long pkey = node.keys[BT_MID];
        BtNode rn = new BtNode(false);
        rn.keys = Arrays.copyOfRange(node.keys, BT_MID + 1, node.nkeys); rn.nkeys = rn.keys.length;
        rn.kids = Arrays.copyOfRange(node.kids, BT_MID + 1, node.nkids); rn.nkids = rn.kids.length;
        node.nkeys = BT_MID; node.nkids = BT_MID + 1;
        return new BtSplit(true, pkey, rn);
    }
    static String btreeMain() {
        int n = 100000;
        BtNode root = new BtNode(true);
        long s = 987654321L;
        for (long i = 0; i < n; i++) {
            s = (s * 6364136223846793005L + 1442695040888963407L) & 4611686018427387903L;
            long k = (s >> 12) & 1048575;
            BtSplit sp = btInsertRec(root, k, i + 1);
            if (sp.promoted) {
                BtNode nr = new BtNode(false);
                nr.insertKey(0, sp.key);
                nr.insertKid(0, root);
                nr.insertKid(1, sp.right);
                root = nr;
            }
        }
        long total = 0;
        s = 987654321L;
        for (int round = 0; round < 10; round++) {
            for (int i = 0; i < n; i++) {
                s = (s * 6364136223846793005L + 1442695040888963407L) & 4611686018427387903L;
                long v = btSearch(root, (s >> 12) & 1048575);
                if (v >= 0) total = Math.addExact(total, v);
            }
        }
        for (long i = 0; i < 30000; i++) {
            long lo = (i * 31) & 1048575;
            total = Math.addExact(total, btRangeSum(root, lo, lo + 200));
        }
        return Long.toString(total);
    }

    // hashagg
    static long hashaggHash2(long k1, long k2) {
        long h = (k1 * 2654435761L) ^ (k2 * 2246822519L);
        h = (h ^ (h >> 16)) * 2246822519L;
        h = h ^ (h >> 13);
        return h & 4611686018427387903L;
    }
    static String hashaggMain() {
        int n = 1000000, cap = 32768, mask = cap - 1;
        long[] colK1 = new long[n], colK2 = new long[n], colVal = new long[n];
        long s = 42424242L;
        for (int i = 0; i < n; i++) {
            s = (s * 6364136223846793005L + 1442695040888963407L) & 4611686018427387903L;
            colK1[i] = (s >> 16) & 255;
            colK2[i] = (s >> 24) & 63;
            colVal[i] = ((s >> 32) & 65535) - 32768;
        }
        int[] slots = new int[cap];
        long[] gK1 = new long[cap], gK2 = new long[cap], gCnt = new long[cap], gSum = new long[cap], gMin = new long[cap], gMax = new long[cap];
        long checksum = 0;
        for (long round = 0; round < 10; round++) {
            Arrays.fill(slots, -1);
            int ng = 0;
            for (int i = 0; i < n; i++) {
                long k1 = colK1[i], k2 = colK2[i], v = Math.addExact(colVal[i], round);
                int h = (int) (hashaggHash2(k1, k2) & mask);
                while (true) {
                    int g = slots[h];
                    if (g < 0) {
                        slots[h] = ng;
                        gK1[ng] = k1; gK2[ng] = k2; gCnt[ng] = 1; gSum[ng] = v; gMin[ng] = v; gMax[ng] = v;
                        ng++;
                        break;
                    }
                    if (gK1[g] == k1 && gK2[g] == k2) {
                        gCnt[g] = Math.addExact(gCnt[g], 1L);
                        gSum[g] = Math.addExact(gSum[g], v);
                        if (v < gMin[g]) gMin[g] = v;
                        if (v > gMax[g]) gMax[g] = v;
                        break;
                    }
                    h = (h + 1) & mask;
                }
            }
            for (int g = 0; g < ng; g++) {
                checksum = Math.addExact(checksum, Math.addExact(Math.addExact(gCnt[g], gSum[g]), Math.addExact(gMin[g], gMax[g])));
            }
        }
        return Long.toString(checksum);
    }

    // varint_csv
    static final class ByteBuf {
        byte[] a = new byte[16]; int len = 0;
        void push(byte b) {
            if (len == a.length) a = Arrays.copyOf(a, a.length * 2);
            a[len++] = b;
        }
    }
    static void putVarint(ByteBuf out, long v) {
        while (v >= 128) { out.push((byte) ((v & 127) | 128)); v >>= 7; }
        out.push((byte) v);
    }
    static long parseCsvInt(byte[] buf, int start, int end) {
        int i = start; boolean neg = false;
        if (i < end && buf[i] == '-') { neg = true; i++; }
        long acc = 0;
        while (i < end) { acc = Math.addExact(Math.multiplyExact(acc, 10L), (buf[i++] - '0')); }
        return neg ? -acc : acc;
    }
    static void appendCsvInt(ByteBuf out, long v) {
        if (v < 0) { out.push((byte) '-'); v = -v; }
        if (v == 0) { out.push((byte) '0'); return; }
        byte[] tmp = new byte[24]; int k = 0;
        while (v > 0) { tmp[k++] = (byte) ('0' + (v % 10)); v /= 10; }
        while (k > 0) out.push(tmp[--k]);
    }
    static byte[] buildCsv(int rows) {
        ByteBuf buf = new ByteBuf();
        byte[] codes = "ABCDEFGHIJKLMNOP".getBytes();
        long s = 7777777L;
        for (int i = 0; i < rows; i++) {
            s = (s * 6364136223846793005L + 1442695040888963407L) & 4611686018427387903L;
            appendCsvInt(buf, i + 1); buf.push((byte) '|');
            appendCsvInt(buf, ((s >> 16) & 63) + 1); buf.push((byte) '|');
            appendCsvInt(buf, ((s >> 24) & 65535) + 1000); buf.push((byte) '|');
            int c1 = (int) ((s >> 40) & 15), c2 = (int) ((s >> 44) & 15);
            buf.push(codes[c1]); buf.push(codes[c2]); buf.push(codes[(c1 + c2) & 15]);
            buf.push((byte) '\n');
        }
        return Arrays.copyOf(buf.a, buf.len);
    }
    static String varintCsvMain() {
        byte[] csv = buildCsv(120000);
        int n = csv.length;
        long total = 0;
        for (long round = 0; round < 25; round++) {
            ByteBuf out = new ByteBuf();
            int pos = 0; long rowHash = 0;
            while (pos < n) {
                int f0 = pos; while (csv[pos] != '|') pos++;
                long id = parseCsvInt(csv, f0, pos++);
                int f1 = pos; while (csv[pos] != '|') pos++;
                long qty = parseCsvInt(csv, f1, pos++);
                int f2 = pos; while (csv[pos] != '|') pos++;
                long price = parseCsvInt(csv, f2, pos++);
                long codeH = 0;
                while (csv[pos] != '\n') { codeH = Math.addExact(Math.multiplyExact(codeH, 31L), csv[pos++] & 0xFFL); }
                pos++;
                putVarint(out, id); putVarint(out, qty); putVarint(out, price);
                rowHash = Math.addExact(rowHash, codeH);
            }
            long sumB = 0;
            for (int i = 0; i < out.len; i++) sumB = Math.addExact(sumB, out.a[i] & 0xFFL);
            total = Math.addExact(total, Math.addExact(Math.addExact(out.len, sumB), Math.addExact(rowHash, round)));
        }
        return Long.toString(total);
    }

    // enum_eval
    static final int E_COL = 0, E_LIT = 1, E_ADD = 2, E_SUB = 3, E_MUL = 4, E_LT = 5, E_AND = 6, E_IF = 7;
    static final class Expr {
        final int tag; final long v; final Expr a, b, c;
        Expr(int tag, long v, Expr a, Expr b, Expr c) { this.tag = tag; this.v = v; this.a = a; this.b = b; this.c = c; }
    }
    static long evalRow(Expr e, long[] c0, long[] c1, long[] c2, long[] c3, int row) {
        switch (e.tag) {
            case E_COL: return e.v == 0 ? c0[row] : e.v == 1 ? c1[row] : e.v == 2 ? c2[row] : c3[row];
            case E_LIT: return e.v;
            case E_ADD: return Math.addExact(evalRow(e.a, c0, c1, c2, c3, row), evalRow(e.b, c0, c1, c2, c3, row));
            case E_SUB: return Math.subtractExact(evalRow(e.a, c0, c1, c2, c3, row), evalRow(e.b, c0, c1, c2, c3, row));
            case E_MUL: return Math.multiplyExact(evalRow(e.a, c0, c1, c2, c3, row), evalRow(e.b, c0, c1, c2, c3, row));
            case E_LT: return evalRow(e.a, c0, c1, c2, c3, row) < evalRow(e.b, c0, c1, c2, c3, row) ? 1 : 0;
            case E_AND: return evalRow(e.a, c0, c1, c2, c3, row) == 0 ? 0 : (evalRow(e.b, c0, c1, c2, c3, row) != 0 ? 1 : 0);
            case E_IF: return evalRow(e.a, c0, c1, c2, c3, row) != 0 ? evalRow(e.b, c0, c1, c2, c3, row) : evalRow(e.c, c0, c1, c2, c3, row);
            default: throw new AssertionError();
        }
    }
    static String enumEvalMain() {
        Expr expr = new Expr(E_IF, 0,
            new Expr(E_AND, 0,
                new Expr(E_LT, 0, new Expr(E_COL, 0, null, null, null), new Expr(E_LIT, 25, null, null, null), null),
                new Expr(E_LT, 0, new Expr(E_COL, 1, null, null, null), new Expr(E_LIT, 8, null, null, null), null), null),
            new Expr(E_MUL, 0, new Expr(E_COL, 2, null, null, null),
                new Expr(E_SUB, 0, new Expr(E_LIT, 100, null, null, null), new Expr(E_COL, 1, null, null, null), null), null),
            new Expr(E_ADD, 0,
                new Expr(E_MUL, 0, new Expr(E_COL, 2, null, null, null),
                    new Expr(E_SUB, 0, new Expr(E_LIT, 100, null, null, null), new Expr(E_COL, 3, null, null, null), null), null),
                new Expr(E_COL, 0, null, null, null), null));
        int n = 500000;
        long[] c0 = new long[n], c1 = new long[n], c2 = new long[n], c3 = new long[n];
        long s = 135792468L;
        for (int i = 0; i < n; i++) {
            s = (s * 6364136223846793005L + 1442695040888963407L) & 4611686018427387903L;
            c0[i] = (s >> 16) & 63; c1[i] = (s >> 22) & 15; c2[i] = ((s >> 26) & 4095) + 100; c3[i] = (s >> 38) & 15;
        }
        long total = 0;
        for (long round = 0; round < 8; round++) {
            long acc = 0;
            for (int i = 0; i < n; i++) acc = Math.addExact(acc, evalRow(expr, c0, c1, c2, c3, i));
            total = Math.addExact(total, Math.addExact(acc, round));
        }
        return Long.toString(total);
    }

    static String run(String name) {
        switch (name) {
            case "fib": return fibMain();
            case "loop": return loopMain();
            case "array": return arrayMain();
            case "alloc": return allocMain();
            case "lists": return listsMain();
            case "strings": return stringsMain();
            case "trees": return treesMain();
            case "tokens": return tokensMain();
            case "sieve": return sieveMain();
            case "maps": return mapsMain();
            case "nbody": return nbodyMain();
            case "interp": return interpMain();
            case "closures": return closuresMain();
            case "matmul": return matmulMain();
            case "pingpong": return pingpongMain();
            case "bitpack": return bitpackMain();
            case "btree": return btreeMain();
            case "hashagg": return hashaggMain();
            case "varint_csv": return varintCsvMain();
            case "enum_eval": return enumEvalMain();
        }
        throw new IllegalArgumentException(name);
    }

    public static void main(String[] a) throws Exception {
        if (a.length > 1) tokData = Files.readAllBytes(Path.of(a[1]));
        long t0 = System.nanoTime();
        String out = run(a[0]);
        long cold = System.nanoTime() - t0;
        System.out.println(out);
        run(a[0]);
        long best = Long.MAX_VALUE;
        int runs = Integer.getInteger("bench.runs", 5);
        for (int r = 0; r < runs; r++) {
            t0 = System.nanoTime();
            String o = run(a[0]);
            best = Math.min(best, System.nanoTime() - t0);
            if (!o.equals(out)) throw new AssertionError("checksum changed");
        }
        System.out.printf("cold %.0f%nwarm %.0f%n", cold / 1e6, best / 1e6);
    }
}
