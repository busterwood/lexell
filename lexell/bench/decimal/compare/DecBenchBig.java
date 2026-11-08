import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;

// 38-digit cases for the types that can represent them: Lexell's 128-bit
// coefficient and Java's BigDecimal.  .NET's decimal is 96-bit / 28-29
// digits and cannot.  Same construction as decbench-big.lxl: two splitmix64
// words per 38-digit coefficient.
public class DecBenchBig {
    static final int N = 4096;
    static final BigInteger TEN = BigInteger.TEN;
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

    static BigInteger coefBig(int d) {
        BigInteger lo = TEN.pow(d - 1);
        BigInteger range = lo.multiply(BigInteger.valueOf(9));
        BigInteger r = new BigInteger(Long.toUnsignedString(next())).shiftLeft(64)
                .or(new BigInteger(Long.toUnsignedString(next())));
        BigInteger c = lo.add(r.mod(range));
        if (c.mod(TEN).signum() == 0) c = c.add(BigInteger.ONE);
        return c;
    }

    static BigDecimal d(BigInteger c, int scale, boolean neg) {
        BigDecimal v = new BigDecimal(c, scale);
        return neg ? v.negate() : v;
    }

    static String pad(BigInteger c, int n) {
        String s = c.toString();
        while (s.length() < n) s = "0" + s;
        return s;
    }

    static BigDecimal[] xs38, ys38, xm, ym, fmt;
    static String[] parse;

    static void build() {
        xs38 = new BigDecimal[N]; ys38 = new BigDecimal[N];
        xm = new BigDecimal[N]; ym = new BigDecimal[N];
        fmt = new BigDecimal[N]; parse = new String[N];
        for (int i = 0; i < N; i++) {
            BigInteger a = coefBig(37);
            xs38[i] = d(a, 2, below(4) == 0);
            BigInteger b = coefBig(37);
            ys38[i] = d(b, 2, false);

            long ma = coefNZ(19);
            boolean nma = below(2) == 0;
            xm[i] = d(new BigInteger(Long.toUnsignedString(ma)), 4, nma);
            long mb = coefNZ(19);
            ym[i] = d(new BigInteger(Long.toUnsignedString(mb)), 3, false);

            String digits = pad(coefBig(38), 38);
            String t = digits.substring(0, 34) + "." + digits.substring(34);
            if (below(3) == 0) t = "-" + t;
            parse[i] = t;

            fmt[i] = d(coefBig(38), 2, below(3) == 0);
        }
    }

    interface Bench { long run(int reps); }

    static long benchAdd(int reps) {
        long a = 0;
        for (int r = 0; r < reps; r++)
            for (int i = 0; i < N; i++) {
                BigDecimal res = xs38[i].add(ys38[i]);
                SINK = res;
                a += res.unscaledValue().longValue();
            }
        return a;
    }

    static long benchMul(int reps) {
        long a = 0;
        for (int r = 0; r < reps; r++)
            for (int i = 0; i < N; i++) {
                BigDecimal res = xm[i].multiply(ym[i]);
                SINK = res;
                a += res.unscaledValue().longValue();
            }
        return a;
    }

    static long benchParse(int reps) {
        long a = 0;
        for (int r = 0; r < reps; r++)
            for (int i = 0; i < N; i++) {
                BigDecimal res = new BigDecimal(parse[i]);
                SINK = res;
                a += res.unscaledValue().longValue();
            }
        return a;
    }

    static long benchFormat(int reps) {
        long a = 0;
        for (int r = 0; r < reps; r++)
            for (int i = 0; i < N; i++) {
                String s = fmt[i].toPlainString();
                SINK = s;
                a += s.length();
            }
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
        run("add37", DecBenchBig::benchAdd, 1000);
        run("mul19", DecBenchBig::benchMul, 1000);
        run("parse38", DecBenchBig::benchParse, 500);
        run("format38", DecBenchBig::benchFormat, 250);
    }
}
