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
