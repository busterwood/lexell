import java.util.*;

/** A tiny assertion harness: each check prints "ok" or "FAIL name: got X, want Y"; main exits 1 on any failure. */
public class Check {
    public static int failed = 0, passed = 0;
    private static String show(Object o) {
        if (o == null) return "null";
        if (o instanceof byte[]) { StringBuilder b = new StringBuilder("0x"); for (byte x : (byte[]) o) b.append(String.format("%02x", x)); return b.toString(); }
        if (o instanceof Object[]) return Arrays.deepToString((Object[]) o);
        return String.valueOf(o);
    }
    public static void eq(String name, Object got, Object want) {
        if (Objects.equals(show(got), show(want))) { passed++; if (System.getenv("VERBOSE") != null) System.out.println("ok   " + name); }
        else { failed++; System.out.println("FAIL " + name + ": got " + show(got) + ", want " + show(want)); }
    }
    /** A difference that is known and listed (design/lexdb-oracle.md, lexdb-tds.md): shown, not counted as a failure. */
    public static void known(String name, Object got, Object want) {
        if (!Objects.equals(show(got), show(want))) System.out.println("KNOWN " + name + ": got " + show(got) + ", want " + show(want));
        else { passed++; }
    }
    public static void yes(String name, boolean cond) { eq(name, cond, true); }
    public static void done() {
        System.out.println(passed + " passed, " + failed + " failed");
        if (failed > 0) System.exit(1);
    }
    /** The error code of what the runnable throws (0: nothing thrown). */
    public interface Body { void run() throws Exception; }
    public static int errorOf(Body b) {
        try { b.run(); return 0; }
        catch (java.sql.SQLException e) { return e.getErrorCode(); }
        catch (Exception e) { return -1; }
    }
}
