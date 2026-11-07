import java.math.BigDecimal;
import java.math.BigInteger;

// One BigDecimal operation at a given digit count, to see the compact-value
// threshold.  usage: Scale mul|add DIGITS REPS
public class Scale {
    static final int N = 4096;
    static long seed = 0x2545f4914f6cdd1dL;
    static volatile Object SINK;

    static long next() {
        seed += 0x9e3779b97f4a7c15L;
        long z = seed;
        z = (z ^ (z >>> 30)) * 0xbf58476d1ce4e5b9L;
        z = (z ^ (z >>> 27)) * 0x94d049bb133111ebL;
        return z ^ (z >>> 31);
    }

    static String digits(int d) {
        StringBuilder sb = new StringBuilder(d);
        sb.append((char) ('1' + (int) Long.remainderUnsigned(next(), 9)));
        for (int i = 1; i < d; i++) sb.append((char) ('0' + (int) Long.remainderUnsigned(next(), 10)));
        return sb.toString();
    }

    public static void main(String[] args) {
        String op = args[0];
        int d = Integer.parseInt(args[1]);
        int reps = Integer.parseInt(args[2]);
        BigDecimal[] xs = new BigDecimal[N];
        BigDecimal[] ys = new BigDecimal[N];
        for (int i = 0; i < N; i++) {
            xs[i] = new BigDecimal(new BigInteger(digits(d)), 0);
            ys[i] = new BigDecimal(new BigInteger(digits(d)), 0);
        }
        for (int k = 0; k < 3; k++) run(op, xs, ys, reps);
        long best = Long.MAX_VALUE;
        for (int k = 0; k < 5; k++) {
            long t0 = System.nanoTime();
            run(op, xs, ys, reps);
            long dt = System.nanoTime() - t0;
            if (dt < best) best = dt;
        }
        double ns = (double) best / ((double) reps * N);
        System.out.printf("%s d=%d %.2f%n", op, d, ns);
    }

    static long run(String op, BigDecimal[] xs, BigDecimal[] ys, int reps) {
        long a = 0;
        if (op.equals("mul")) {
            for (int r = 0; r < reps; r++)
                for (int i = 0; i < N; i++) {
                    BigDecimal v = xs[i].multiply(ys[i]);
                    SINK = v;
                    a += v.unscaledValue().longValue();
                }
        } else {
            for (int r = 0; r < reps; r++)
                for (int i = 0; i < N; i++) {
                    BigDecimal v = xs[i].add(ys[i]);
                    SINK = v;
                    a += v.unscaledValue().longValue();
                }
        }
        return a;
    }
}
