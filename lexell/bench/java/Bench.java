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
