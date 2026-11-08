import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;

// Matched decimal benchmark: same inputs and operation counts as DecBench.cs
// and decbench.lxl.  Prints "<case> <ns/op> <checksum>".
//
// BigDecimal is arbitrary precision and allocates; a volatile sink every 1024
// iterations keeps a result alive so the JIT cannot scalar-replace the
// allocation away.  The cases match Lexell's 19-digit add, 6x6 mul, 12/6 div at
// scale 2, 20-digit parse, 19-digit format and 19-digit compare.
public class DecBench {
    static final int N = 4096;
    static final int REPS = 4000;

    static long seed = 0x2545f4914f6cdd1dL;
    static volatile Object SINK;

    static long next() {
        seed += 0x9e3779b97f4a7c15L;
        long z = seed;
        z = (z ^ (z >>> 30)) * 0xbf58476d1ce4e5b9L;
        z = (z ^ (z >>> 27)) * 0x94d049bb133111ebL;
        return z ^ (z >>> 31);
    }

    static int below(int n) { return (int) Long.remainderUnsigned(next(), n); }

    static long p10(int d) {
        long x = 1;
        for (int i = 0; i < d; i++) x *= 10;
        return x;
    }

    static long coefNZ(int d) {
        long lo = p10(d - 1);
        long range = 9 * lo;
        long c = lo + Long.remainderUnsigned(next(), range);
        if (Long.remainderUnsigned(c, 10) == 0) c += 1;
        return c;
    }

    static BigDecimal d(long c, int scale, boolean neg) {
        BigDecimal v = new BigDecimal(new BigInteger(Long.toUnsignedString(c)), scale);
        return neg ? v.negate() : v;
    }

    static String p19(long c) {
        String s = Long.toUnsignedString(c);
        while (s.length() < 19) s = "0" + s;
        return s;
    }

    static BigDecimal[] xs19, ys19, xs6, ys6, xs12, ys12, fmt, cmpA, cmpB;
    static String[] parse;

    static void build() {
        xs19 = new BigDecimal[N]; ys19 = new BigDecimal[N];
        xs6 = new BigDecimal[N]; ys6 = new BigDecimal[N];
        xs12 = new BigDecimal[N]; ys12 = new BigDecimal[N];
        fmt = new BigDecimal[N];
        cmpA = new BigDecimal[N]; cmpB = new BigDecimal[N];
        parse = new String[N];
        for (int i = 0; i < N; i++) {
            xs19[i] = d(coefNZ(19), 2, below(4) == 0);
            ys19[i] = d(coefNZ(19), 2, false);

            xs6[i] = d(coefNZ(6), 4, below(2) == 0);
            ys6[i] = d(coefNZ(6), 3, false);

            xs12[i] = d(coefNZ(12), 2, below(2) == 0);
            ys12[i] = d(coefNZ(6), 2, false);

            long lead = 1 + below(9);
            String digits = Long.toString(lead) + p19(coefNZ(19));
            String t = digits.substring(0, 16) + "." + digits.substring(16);
            if (below(3) == 0) t = "-" + t;
            parse[i] = t;

            fmt[i] = d(coefNZ(19), 2, below(3) == 0);

            cmpA[i] = d(coefNZ(19), 2, false);
            cmpB[i] = d(coefNZ(19), 2, false);
        }
    }

    interface Bench { long run(int reps); }

    static long benchAdd(int reps) {
        long a = 0;
        for (int r = 0; r < reps; r++)
            for (int i = 0; i < N; i++) {
                BigDecimal res = xs19[i].add(ys19[i]);
                if ((i & 1023) == 0) SINK = res;
                a += res.unscaledValue().longValue();
            }
        return a;
    }

    static long benchMul(int reps) {
        long a = 0;
        for (int r = 0; r < reps; r++)
            for (int i = 0; i < N; i++) {
                BigDecimal res = xs6[i].multiply(ys6[i]);
                if ((i & 1023) == 0) SINK = res;
                a += res.unscaledValue().longValue();
            }
        return a;
    }

    static long benchDiv(int reps) {
        long a = 0;
        for (int r = 0; r < reps; r++)
            for (int i = 0; i < N; i++) {
                BigDecimal res = xs12[i].divide(ys12[i], 2, RoundingMode.HALF_EVEN);
                if ((i & 1023) == 0) SINK = res;
                a += res.unscaledValue().longValue();
            }
        return a;
    }

    static long benchParse(int reps) {
        long a = 0;
        for (int r = 0; r < reps; r++)
            for (int i = 0; i < N; i++) {
                BigDecimal res = new BigDecimal(parse[i]);
                if ((i & 1023) == 0) SINK = res;
                a += res.unscaledValue().longValue();
            }
        return a;
    }

    static long benchFormat(int reps) {
        long a = 0;
        for (int r = 0; r < reps; r++)
            for (int i = 0; i < N; i++) {
                String s = fmt[i].toPlainString();
                if ((i & 1023) == 0) SINK = s;
                a += s.length();
            }
        return a;
    }

    static long benchCmp(int reps) {
        long a = 0;
        for (int r = 0; r < reps; r++)
            for (int i = 0; i < N; i++)
                a += cmpA[i].compareTo(cmpB[i]);
        return a;
    }

    static void run(String name, Bench f, int reps) {
        for (int k = 0; k < 5; k++) f.run(reps);
        long best = Long.MAX_VALUE;
        long acc = 0;
        for (int k = 0; k < 7; k++) {
            long t0 = System.nanoTime();
            acc = f.run(reps);
            long dt = System.nanoTime() - t0;
            if (dt < best) best = dt;
        }
        double ns = (double) best / ((double) reps * N);
        System.out.printf("%s %.2f %d%n", name, ns, acc);
    }

    public static void main(String[] args) {
        build();
        run("add", DecBench::benchAdd, REPS);
        run("mul", DecBench::benchMul, REPS);
        run("div", DecBench::benchDiv, REPS / 2);
        run("parse", DecBench::benchParse, REPS);
        run("format", DecBench::benchFormat, REPS / 4);
        run("cmp", DecBench::benchCmp, REPS * 2);
    }
}
