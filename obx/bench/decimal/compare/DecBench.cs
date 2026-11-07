using System;
using System.Diagnostics;
using System.Globalization;

// Matched decimal benchmark: same inputs and operation counts as DecBench.java
// and decbench.obx.  Prints "<case> <ns/op> <checksum>".  .NET's decimal is
// 96-bit / 28-29 digits, so the cases are the ones it can represent: 19-digit
// add, 6x6 mul, 12/6 div at scale 2, 20-digit parse, 19-digit format,
// 19-digit compare.  Run with DOTNET_TieredCompilation=0 so the first timed
// run is already optimised.
class DecBench
{
    const int N = 4096;
    const int REPS = 4000;

    static ulong seed = 0x2545f4914f6cdd1dUL;
    static decimal SinkD;
    static string SinkS;

    static ulong Next()
    {
        seed += 0x9e3779b97f4a7c15UL;
        ulong z = seed;
        z = (z ^ (z >> 30)) * 0xbf58476d1ce4e5b9UL;
        z = (z ^ (z >> 27)) * 0x94d049bb133111ebUL;
        return z ^ (z >> 31);
    }

    static int Below(int n) { return (int)(Next() % (ulong)n); }

    static ulong P10(int d)
    {
        ulong x = 1;
        for (int i = 0; i < d; i++) x *= 10;
        return x;
    }

    static ulong CoefNZ(int d)
    {
        ulong lo = P10(d - 1);
        ulong range = 9 * lo;
        ulong c = lo + Next() % range;
        if (c % 10 == 0) c += 1;
        return c;
    }

    static decimal D(ulong c, int scale, bool neg)
    {
        decimal v = (decimal)c;
        for (int i = 0; i < scale; i++) v /= 10m;
        return neg ? -v : v;
    }

    static string P19(ulong c)
    {
        return c.ToString("D19", CultureInfo.InvariantCulture);
    }

    static decimal[] xs19, ys19, xs6, ys6, xs12, ys12, fmt, cmpA, cmpB;
    static string[] parse;

    static void Build()
    {
        xs19 = new decimal[N]; ys19 = new decimal[N];
        xs6 = new decimal[N]; ys6 = new decimal[N];
        xs12 = new decimal[N]; ys12 = new decimal[N];
        fmt = new decimal[N];
        cmpA = new decimal[N]; cmpB = new decimal[N];
        parse = new string[N];
        for (int i = 0; i < N; i++)
        {
            xs19[i] = D(CoefNZ(19), 2, Below(4) == 0);
            ys19[i] = D(CoefNZ(19), 2, false);

            xs6[i] = D(CoefNZ(6), 4, Below(2) == 0);
            ys6[i] = D(CoefNZ(6), 3, false);

            xs12[i] = D(CoefNZ(12), 2, Below(2) == 0);
            ys12[i] = D(CoefNZ(6), 2, false);

            ulong lead = (ulong)(1 + Below(9));
            string digits = lead.ToString(CultureInfo.InvariantCulture) + P19(CoefNZ(19));
            string t = digits.Substring(0, 16) + "." + digits.Substring(16);
            if (Below(3) == 0) t = "-" + t;
            parse[i] = t;

            fmt[i] = D(CoefNZ(19), 2, Below(3) == 0);

            cmpA[i] = D(CoefNZ(19), 2, false);
            cmpB[i] = D(CoefNZ(19), 2, false);
        }
    }

    static long BenchAdd(int reps)
    {
        long a = 0;
        for (int r = 0; r < reps; r++)
            for (int i = 0; i < N; i++)
            {
                decimal res = xs19[i] + ys19[i];
                if ((i & 1023) == 0) SinkD = res;
                a += res.GetHashCode();
            }
        return a;
    }

    static long BenchMul(int reps)
    {
        long a = 0;
        for (int r = 0; r < reps; r++)
            for (int i = 0; i < N; i++)
            {
                decimal res = xs6[i] * ys6[i];
                if ((i & 1023) == 0) SinkD = res;
                a += res.GetHashCode();
            }
        return a;
    }

    static long BenchDiv(int reps)
    {
        long a = 0;
        for (int r = 0; r < reps; r++)
            for (int i = 0; i < N; i++)
            {
                decimal res = Math.Round(xs12[i] / ys12[i], 2, MidpointRounding.ToEven);
                if ((i & 1023) == 0) SinkD = res;
                a += res.GetHashCode();
            }
        return a;
    }

    static long BenchParse(int reps)
    {
        long a = 0;
        for (int r = 0; r < reps; r++)
            for (int i = 0; i < N; i++)
            {
                decimal res = decimal.Parse(parse[i], CultureInfo.InvariantCulture);
                if ((i & 1023) == 0) SinkD = res;
                a += res.GetHashCode();
            }
        return a;
    }

    static long BenchFormat(int reps)
    {
        long a = 0;
        for (int r = 0; r < reps; r++)
            for (int i = 0; i < N; i++)
            {
                string s = fmt[i].ToString("F2", CultureInfo.InvariantCulture);
                if ((i & 1023) == 0) SinkS = s;
                a += s.Length;
            }
        return a;
    }

    static long BenchCmp(int reps)
    {
        long a = 0;
        for (int r = 0; r < reps; r++)
            for (int i = 0; i < N; i++)
                a += cmpA[i].CompareTo(cmpB[i]);
        return a;
    }

    static void Run(string name, Func<int, long> f, int reps)
    {
        for (int k = 0; k < 5; k++) f(reps);
        long best = long.MaxValue;
        long acc = 0;
        for (int k = 0; k < 7; k++)
        {
            long t0 = Stopwatch.GetTimestamp();
            acc = f(reps);
            long dt = Stopwatch.GetTimestamp() - t0;
            if (dt < best) best = dt;
        }
        double ns = (double)best * 1e9 / Stopwatch.Frequency / ((double)reps * N);
        Console.WriteLine(name + " " + ns.ToString("F2", CultureInfo.InvariantCulture) + " " + acc);
    }

    static void Main()
    {
        Build();
        Run("add", BenchAdd, REPS);
        Run("mul", BenchMul, REPS);
        Run("div", BenchDiv, REPS / 2);
        Run("parse", BenchParse, REPS);
        Run("format", BenchFormat, REPS / 4);
        Run("cmp", BenchCmp, REPS * 2);
    }
}
