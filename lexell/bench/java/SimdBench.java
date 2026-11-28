// Explicit-SIMD Java ports of lexell/bench/simd/*_vec.lxl using OpenJDK 21's
// jdk.incubator.vector API (256-bit AVX2 species).
// Compile: javac --add-modules jdk.incubator.vector SimdBench.java
// Run:     java --add-modules jdk.incubator.vector -Dbench.runs=5 SimdBench NAME
import java.util.*;
import jdk.incubator.vector.*;

public class SimdBench {
    static final VectorSpecies<Long> LONG_256 = LongVector.SPECIES_256;
    static final VectorSpecies<Byte> BYTE_256 = ByteVector.SPECIES_256;
    static final VectorSpecies<Double> DOUBLE_256 = DoubleVector.SPECIES_256;
    static final VectorSpecies<Integer> INT_256 = IntVector.SPECIES_256;

    // array_vec: 4-wide i64 AVX2 add + sum (1M x 800 rounds)
    static long arrayVecRound(long[] a, int len, long r) {
        int step = LONG_256.length();
        int bound = LONG_256.loopBound(len);
        LongVector vr = LongVector.broadcast(LONG_256, r);
        LongVector acc = LongVector.zero(LONG_256);
        int i = 0;
        for (; i < bound; i += step) {
            LongVector v = LongVector.fromArray(LONG_256, a, i).add(vr);
            v.intoArray(a, i);
            acc = acc.add(v);
        }
        long sum = acc.reduceLanes(VectorOperators.ADD);
        for (; i < len; i++) {
            a[i] += r;
            sum += a[i];
        }
        return sum;
    }

    static String arrayVecMain() {
        int n = 1000000;
        long[] a = new long[0];
        int len = 0;
        for (int i = 0; i < n; i++) {
            if (len == a.length) a = Arrays.copyOf(a, Math.max(4, a.length * 2));
            a[len++] = i;
        }
        long total = 0;
        for (long r = 0; r < 800; r++) {
            total += arrayVecRound(a, len, r);
        }
        return Long.toString(total);
    }

    // sieve_vec: sieve up to 10M x 30 rounds with 32-wide AVX2 byte-mask counting
    static long sieveVecCount(byte[] prime, int m) {
        int step = BYTE_256.length();
        int bound = BYTE_256.loopBound(m);
        ByteVector vZero = ByteVector.zero(BYTE_256);
        long count = 0;
        int k = 0;
        for (; k < bound; k += step) {
            ByteVector v = ByteVector.fromArray(BYTE_256, prime, k);
            count += v.compare(VectorOperators.NE, vZero).trueCount();
        }
        for (; k < m; k++) {
            if (prime[k] != 0) count++;
        }
        return count;
    }

    static String sieveVecMain() {
        int n = 10000000;
        int m = n + 1;
        long count = 0;
        for (int round = 0; round < 30; round++) {
            byte[] prime = new byte[m];
            Arrays.fill(prime, (byte) 1);
            prime[0] = 0;
            prime[1] = 0;
            for (int i = 2; (long) i * i <= n; i++) {
                if (prime[i] != 0) {
                    for (int j = i * i; j <= n; j += i) prime[j] = 0;
                }
            }
            count = sieveVecCount(prime, m);
        }
        return Long.toString(count);
    }

    // matmul_vec: 400 x 400 f64 matrix product x 5 rounds with 2x4-wide AVX2 FMA axpy
    static double[][] matmulMatrix(int n, int seed) {
        double[][] m = new double[n][n];
        for (int i = 0; i < n; i++) {
            for (int j = 0; j < n; j++) m[i][j] = (i * seed + j * 7) % 11 - 5;
        }
        return m;
    }

    static void axpy(double[] dst, double[] src, double a) {
        DoubleVector va = DoubleVector.broadcast(DOUBLE_256, a);
        int l1 = DOUBLE_256.length();
        int step = l1 * 2;
        int n = Math.min(dst.length, src.length);
        int j = 0;
        for (; j + step <= n; j += step) {
            DoubleVector s0 = DoubleVector.fromArray(DOUBLE_256, src, j);
            DoubleVector s1 = DoubleVector.fromArray(DOUBLE_256, src, j + l1);
            DoubleVector d0 = DoubleVector.fromArray(DOUBLE_256, dst, j);
            DoubleVector d1 = DoubleVector.fromArray(DOUBLE_256, dst, j + l1);
            va.fma(s0, d0).intoArray(dst, j);
            va.fma(s1, d1).intoArray(dst, j + l1);
        }
        for (; j + l1 <= n; j += l1) {
            DoubleVector s0 = DoubleVector.fromArray(DOUBLE_256, src, j);
            DoubleVector d0 = DoubleVector.fromArray(DOUBLE_256, dst, j);
            va.fma(s0, d0).intoArray(dst, j);
        }
        for (; j < n; j++) dst[j] = Math.fma(a, src[j], dst[j]);
    }

    static String matmulVecMain() {
        int n = 400;
        double[][] a = matmulMatrix(n, 3);
        double[][] b = matmulMatrix(n, 5);
        long total = 0;
        for (int r = 0; r < 5; r++) {
            double[][] c = new double[n][];
            for (int i = 0; i < n; i++) {
                double[] row = new double[n];
                for (int k = 0; k < n; k++) axpy(row, b[k], a[i][k]);
                c[i] = row;
            }
            double s = 0;
            for (int i = 0; i < n; i++) {
                for (int j = 0; j < n; j++) s += c[i][j] * ((i * n + j) % 13 + r);
            }
            total += (long) s;
        }
        return Long.toString(total);
    }

    // bitpack_vec: bit-packed decode + 8-wide i32 AVX2 filter & masked multiply-sum
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

    static void unpackBatchI32(byte[] buf, int startIdx, int count, int bits, int baseVal, int[] dst) {
        int mask = (1 << bits) - 1;
        int bitPos = startIdx * bits;
        for (int i = 0; i < count; i++) {
            int byteIdx = bitPos >> 3;
            int bitOff = bitPos & 7;
            int w = (buf[byteIdx] & 0xFF)
                | ((buf[byteIdx + 1] & 0xFF) << 8)
                | ((buf[byteIdx + 2] & 0xFF) << 16)
                | ((buf[byteIdx + 3] & 0xFF) << 24);
            dst[i] = baseVal + ((w >>> bitOff) & mask);
            bitPos += bits;
        }
    }

    static long bitpackVecBatch(int[] disc, int[] qty, int[] price, int cnt, int loDisc, int hiDisc, int maxQty, int[] lanes) {
        IntVector vLo = IntVector.broadcast(INT_256, loDisc);
        IntVector vHi = IntVector.broadcast(INT_256, hiDisc);
        IntVector vMaxQ = IntVector.broadcast(INT_256, maxQty);
        IntVector vZero = IntVector.zero(INT_256);
        IntVector vAcc = IntVector.zero(INT_256);
        int step = INT_256.length();
        int bound = INT_256.loopBound(cnt);
        int i = 0;
        for (; i < bound; i += step) {
            IntVector vd = IntVector.fromArray(INT_256, disc, i);
            IntVector vq = IntVector.fromArray(INT_256, qty, i);
            IntVector vp = IntVector.fromArray(INT_256, price, i);
            VectorMask<Integer> m = vd.compare(VectorOperators.GE, vLo)
                .and(vd.compare(VectorOperators.LE, vHi))
                .and(vq.compare(VectorOperators.LT, vMaxQ));
            vAcc = vAcc.add(vZero.blend(vp.mul(vd), m));
        }
        vAcc.intoArray(lanes, 0);
        long sum = 0;
        for (int lane : lanes) sum += lane;
        for (; i < cnt; i++) {
            int d = disc[i];
            if (d >= loDisc && d <= hiDisc && qty[i] < maxQty) sum += (long) (price[i] * d);
        }
        return sum;
    }

    static String bitpackVecMain() {
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
        int[] qty = new int[batch], disc = new int[batch], price = new int[batch];
        int[] lanes = new int[INT_256.length()];
        long total = 0;
        for (int round = 0; round < 60; round++) {
            int loDisc = 4 + (round & 3);
            int hiDisc = loDisc + 4;
            int maxQty = 30 + (round & 7);
            int pos = 0;
            while (pos < n) {
                int cnt = Math.min(batch, n - pos);
                unpackBatchI32(pQty, pos, cnt, 6, 1, qty);
                unpackBatchI32(pDisc, pos, cnt, 4, 0, disc);
                unpackBatchI32(pPrice, pos, cnt, 17, 90000, price);
                total += bitpackVecBatch(disc, qty, price, cnt, loDisc, hiDisc, maxQty, lanes);
                pos += cnt;
            }
        }
        return Long.toString(total);
    }

    // dot_vec: float64 dot product (n=65536, 4000 rounds), 4 accumulators of 4-wide AVX2 FMA
    static double dotVecRound(double[] a, double[] b, int n) {
        int l1 = DOUBLE_256.length();
        int l2 = l1 * 2;
        int l3 = l1 * 3;
        int step = l1 * 4;
        DoubleVector s0 = DoubleVector.zero(DOUBLE_256);
        DoubleVector s1 = DoubleVector.zero(DOUBLE_256);
        DoubleVector s2 = DoubleVector.zero(DOUBLE_256);
        DoubleVector s3 = DoubleVector.zero(DOUBLE_256);
        int i = 0;
        for (; i + step <= n; i += step) {
            s0 = DoubleVector.fromArray(DOUBLE_256, a, i).fma(DoubleVector.fromArray(DOUBLE_256, b, i), s0);
            s1 = DoubleVector.fromArray(DOUBLE_256, a, i + l1).fma(DoubleVector.fromArray(DOUBLE_256, b, i + l1), s1);
            s2 = DoubleVector.fromArray(DOUBLE_256, a, i + l2).fma(DoubleVector.fromArray(DOUBLE_256, b, i + l2), s2);
            s3 = DoubleVector.fromArray(DOUBLE_256, a, i + l3).fma(DoubleVector.fromArray(DOUBLE_256, b, i + l3), s3);
        }
        for (; i + l1 <= n; i += l1) {
            s0 = DoubleVector.fromArray(DOUBLE_256, a, i).fma(DoubleVector.fromArray(DOUBLE_256, b, i), s0);
        }
        double acc = s0.add(s1).add(s2.add(s3)).reduceLanes(VectorOperators.ADD);
        for (; i < n; i++) acc = Math.fma(a[i], b[i], acc);
        return acc;
    }

    static String dotVecMain() {
        int n = 65536;
        int rounds = 4000;
        double[] a = new double[n];
        double[] b = new double[n];
        for (int i = 0; i < n; i++) {
            a[i] = i * 0.5;
            b[i] = i * 0.25 + 1.0;
        }
        double total = 0.0;
        for (int r = 0; r < rounds; r++) {
            total += dotVecRound(a, b, n);
        }
        return String.format(Locale.US, "%.12e", total).replace("e+", "e");
    }

    static String run(String name) {
        switch (name) {
            case "array_vec": return arrayVecMain();
            case "sieve_vec": return sieveVecMain();
            case "matmul_vec": return matmulVecMain();
            case "bitpack_vec": return bitpackVecMain();
            case "dot_vec": return dotVecMain();
        }
        throw new IllegalArgumentException(name);
    }

    public static void main(String[] a) {
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
