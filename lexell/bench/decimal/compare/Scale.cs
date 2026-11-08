using System;
using System.Diagnostics;
using System.Globalization;

// One decimal operation at a given digit count, to see which internal path
// .NET takes.  usage: Scale mul|add DIGITS REPS
class Scale
{
    const int N = 4096;
    static ulong seed = 0x2545f4914f6cdd1dUL;
    static decimal SinkD;

    static ulong Next()
    {
        seed += 0x9e3779b97f4a7c15UL;
        ulong z = seed;
        z = (z ^ (z >> 30)) * 0xbf58476d1ce4e5b9UL;
        z = (z ^ (z >> 27)) * 0x94d049bb133111ebUL;
        return z ^ (z >> 31);
    }

    static string Digits(int d)
    {
        var c = new char[d];
        c[0] = (char)('1' + (int)(Next() % 9));
        for (int i = 1; i < d; i++) c[i] = (char)('0' + (int)(Next() % 10));
        return new string(c);
    }

    static void Main(string[] args)
    {
        string op = args[0];
        int d = int.Parse(args[1], CultureInfo.InvariantCulture);
        int reps = int.Parse(args[2], CultureInfo.InvariantCulture);
        var xs = new decimal[N];
        var ys = new decimal[N];
        for (int i = 0; i < N; i++)
        {
            xs[i] = decimal.Parse(Digits(d), CultureInfo.InvariantCulture);
            ys[i] = decimal.Parse(Digits(d), CultureInfo.InvariantCulture);
        }
        Func<int, long> f;
        if (op == "mul") f = reps2 => { long a = 0; for (int r = 0; r < reps2; r++) for (int i = 0; i < N; i++) { decimal v = xs[i] * ys[i]; SinkD = v; a += v.GetHashCode(); } return a; };
        else f = reps2 => { long a = 0; for (int r = 0; r < reps2; r++) for (int i = 0; i < N; i++) { decimal v = xs[i] + ys[i]; SinkD = v; a += v.GetHashCode(); } return a; };

        for (int k = 0; k < 3; k++) f(reps);
        long best = long.MaxValue;
        for (int k = 0; k < 5; k++)
        {
            long t0 = Stopwatch.GetTimestamp();
            f(reps);
            long dt = Stopwatch.GetTimestamp() - t0;
            if (dt < best) best = dt;
        }
        double ns = (double)best * 1e9 / Stopwatch.Frequency / ((double)reps * N);
        Console.WriteLine(op + " d=" + d + " " + ns.ToString("F2", CultureInfo.InvariantCulture));
    }
}
