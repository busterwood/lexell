import java.io.*;
import java.nio.charset.StandardCharsets;
import java.sql.*;
import java.util.*;

/** The documentation's runner for the SQL Server and Oracle doors (tools/README.md). It reads example
 *  blocks from stdin, each ended by a line "--@@END@@", runs each on one connection (so a page's examples
 *  share a session), and writes each block's output followed by "--@@END@@".
 *
 *  tsql:   a block is T-SQL batches split by GO lines; the output is as sqlcmd and SSMS's text mode
 *          print it: result sets as aligned columns, "(N rows affected)", PRINT lines, and errors as
 *          "Msg N, Level L, State S, Line K" and the message.
 *  oracle: a block is statements as SQL*Plus takes them: SQL ended by ";" at the end of a line,
 *          PL/SQL (BEGIN, DECLARE, CREATE [OR REPLACE] PROCEDURE, FUNCTION, PACKAGE, TRIGGER, TYPE)
 *          ended by a line "/"; the output is SQL*Plus's with SET FEEDBACK 1 and SET SERVEROUTPUT ON.
 *
 *  usage: DocRun tsql JDBC-URL  |  DocRun oracle JDBC-URL USER PASSWORD */
public class DocRun {
    static final String END = "--@@END@@";
    static Connection c;
    static boolean ora;
    static PrintStream out;

    public static void main(String[] a) throws Exception {
        java.util.logging.LogManager.getLogManager().reset();
        out = new PrintStream(new FileOutputStream(FileDescriptor.out), true, StandardCharsets.UTF_8);
        ora = a[0].equals("oracle");
        c = ora ? DriverManager.getConnection(a[1], a[2], a[3]) : DriverManager.getConnection(a[1]);
        if (ora) c.setAutoCommit(false);   // as SQL*Plus: a transaction runs until COMMIT or ROLLBACK
        if (ora) try (Statement s = c.createStatement()) { s.execute("BEGIN DBMS_OUTPUT.ENABLE(NULL); END;"); }
        BufferedReader in = new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8));
        StringBuilder block = new StringBuilder();
        for (String line; (line = in.readLine()) != null; ) {
            if (line.equals(END)) {
                List<String> o = new ArrayList<>();
                if (ora) oracle(block.toString(), o); else tsql(block.toString(), o);
                while (!o.isEmpty() && o.get(o.size() - 1).isEmpty()) o.remove(o.size() - 1);
                for (String s : o) out.println(s);
                out.println(END);
                block.setLength(0);
            } else {
                block.append(line).append('\n');
            }
        }
        c.close();
    }

    // ---- T-SQL: batches split by GO, as sqlcmd does

    static void tsql(String text, List<String> o) {
        StringBuilder batch = new StringBuilder();
        for (String line : text.split("\n", -1)) {
            if (line.trim().equalsIgnoreCase("go")) { batch(batch.toString(), o); batch.setLength(0); }
            else batch.append(line).append('\n');
        }
        if (!batch.toString().isBlank()) batch(batch.toString(), o);
    }

    static void batch(String sql, List<String> o) {
        if (sql.isBlank()) return;
        try (Statement s = c.createStatement()) {
            boolean rs;
            try { rs = s.execute(sql); } catch (SQLException e) { quietWarnings(s, o); msg(e, o); rs = more(s, o); }
            while (true) {
                warnings(s, o);
                if (rs) {
                    // an error while the rows are read (8134, 512 ...) is printed and the batch goes on, as sqlcmd does
                    try (ResultSet r = s.getResultSet()) { table(r, o); }
                    catch (SQLException e) { msg(e, o); }
                } else {
                    int n = s.getUpdateCount();
                    if (n == -1) break;
                    o.add("(" + n + (n == 1 ? " row" : " rows") + " affected)");
                    o.add("");
                }
                rs = more(s, o);
            }
        } catch (SQLException e) {
            msg(e, o);
        }
    }

    static boolean more(Statement s, List<String> o) {
        String last = null;
        while (true) {
            try { return s.getMoreResults(); }
            catch (SQLException e) {
                // a connection the server closed (RAISERROR at severity 20) throws the same error again: stop
                if (e.getMessage() != null && e.getMessage().equals(last)) return false;
                last = e.getMessage();
                quietWarnings(s, o); msg(e, o);
            }
        }
    }

    // the messages that came before an error, printed before it (sqlcmd's order)
    static void quietWarnings(Statement s, List<String> o) {
        try { warnings(s, o); } catch (SQLException e) { /* none to read */ }
    }

    static void warnings(Statement s, List<String> o) throws SQLException {
        for (SQLWarning w = s.getWarnings(); w != null; w = w.getNextWarning()) o.add(w.getMessage());
        s.clearWarnings();
    }

    // Msg 547, Level 16, State 0, Line 1, as sqlcmd prints a server error
    static void msg(SQLException e, List<String> o) {
        int level = 16, state = 1, line = 1;
        try {
            Object err = e.getClass().getMethod("getSQLServerError").invoke(e);
            if (err != null) {
                level = ((Number) err.getClass().getMethod("getErrorSeverity").invoke(err)).intValue();
                state = ((Number) err.getClass().getMethod("getErrorState").invoke(err)).intValue();
                line = ((Number) err.getClass().getMethod("getLineNumber").invoke(err)).intValue();
            }
        } catch (ReflectiveOperationException x) { /* not a server error */ }
        o.add("Msg " + e.getErrorCode() + ", Level " + level + ", State " + state + ", Line " + line);
        o.add(e.getMessage());
    }

    // ---- Oracle: statements as SQL*Plus splits them

    static void oracle(String text, List<String> o) throws SQLException {
        StringBuilder st = new StringBuilder();
        boolean plsql = false;
        for (String line : text.split("\n", -1)) {
            String t = line.trim();
            if (st.length() == 0) {
                if (t.isEmpty() || t.startsWith("--")) continue;
                plsql = isPlsql(t);
            }
            if (plsql) {
                if (t.equals("/")) { statement(st.toString().strip(), true, o); st.setLength(0); }
                else st.append(line).append('\n');
            } else {
                st.append(line).append('\n');
                if (t.endsWith(";")) {
                    String s = st.toString().strip();
                    statement(s.substring(0, s.length() - 1), false, o);
                    st.setLength(0);
                }
            }
        }
        if (!st.toString().isBlank()) statement(st.toString().strip(), plsql, o);
    }

    static boolean isPlsql(String t) {
        String u = t.toUpperCase(Locale.ROOT).replaceAll("\\s+", " ");
        if (u.startsWith("BEGIN") || u.startsWith("DECLARE")) return true;
        u = u.replaceFirst("^CREATE (OR REPLACE )?((NON)?EDITIONABLE )?", "CREATE ");
        for (String k : new String[]{"PROCEDURE", "FUNCTION", "PACKAGE", "TRIGGER", "TYPE"}) if (u.startsWith("CREATE " + k)) return true;
        return false;
    }

    static void statement(String sql, boolean plsql, List<String> o) throws SQLException {
        try (Statement s = c.createStatement()) {
            if (s.execute(sql)) {
                try (ResultSet r = s.getResultSet()) {
                    int at = o.size();
                    int n = table(r, o);
                    o.remove(o.size() - 1);           // table's "(N rows affected)": SQL*Plus says it its way
                    o.remove(o.size() - 1);
                    if (n == 0) while (o.size() > at) o.remove(o.size() - 1);    // no headings either
                    o.add(n == 0 ? "no rows selected" : n + (n == 1 ? " row selected." : " rows selected."));
                }
            } else {
                String fb = feedback(sql, plsql, s.getUpdateCount());
                // ORA-17110 is the warning for a unit that compiled with errors: SQL*Plus says so
                for (SQLWarning w = s.getWarnings(); w != null; w = w.getNextWarning())
                    if (w.getMessage() != null && w.getMessage().contains("ORA-17110") && fb.matches("(Procedure|Function|Package|Package body|Trigger|Type) (created|altered)\\."))
                        fb = "Warning: " + fb.substring(0, fb.length() - 1) + " with compilation errors.";
                o.add(fb);
            }
        } catch (SQLException e) {
            o.add("ERROR:");
            for (String l : e.getMessage().split("\n")) if (!l.isBlank() && !l.startsWith("https://docs.oracle.com/error-help")) o.add(l);
        }
        o.add("");
        serverOutput(o);
    }

    static void serverOutput(List<String> o) throws SQLException {
        List<String> lines = new ArrayList<>();
        try (CallableStatement k = c.prepareCall("BEGIN DBMS_OUTPUT.GET_LINE(?, ?); END;")) {
            k.registerOutParameter(1, Types.VARCHAR);
            k.registerOutParameter(2, Types.INTEGER);
            while (true) {
                k.execute();
                if (k.getInt(2) != 0) break;
                String l = k.getString(1);
                lines.add(l == null ? "" : l);
            }
        }
        if (lines.isEmpty()) return;
        int at = o.size() - 2;                        // before the feedback line, as SQL*Plus prints it
        o.addAll(Math.max(at, 0), lines);
        o.add(Math.max(at, 0) + lines.size(), "");
    }

    // SQL*Plus's feedback for a statement that is not a query
    static String feedback(String sql, boolean plsql, int n) {
        String u = sql.toUpperCase(Locale.ROOT).replaceAll("\\s+", " ").trim();
        String rows = n + (n == 1 ? " row" : " rows");
        if (u.startsWith("INSERT")) return rows + " created.";
        if (u.startsWith("UPDATE")) return rows + " updated.";
        if (u.startsWith("DELETE")) return rows + " deleted.";
        if (u.startsWith("MERGE")) return rows + " merged.";
        if (u.startsWith("COMMIT")) return "Commit complete.";
        if (u.startsWith("ROLLBACK")) return "Rollback complete.";
        if (u.startsWith("SAVEPOINT")) return "Savepoint created.";
        if (u.startsWith("TRUNCATE")) return "Table truncated.";
        if (u.startsWith("GRANT")) return "Grant succeeded.";
        if (u.startsWith("REVOKE")) return "Revoke succeeded.";
        if (u.startsWith("ALTER SESSION")) return "Session altered.";
        if (u.startsWith("COMMENT")) return "Comment created.";
        if (u.startsWith("LOCK")) return "Table(s) Locked.";
        if (u.startsWith("BEGIN") || u.startsWith("DECLARE") || u.startsWith("CALL")) return "PL/SQL procedure successfully completed.";
        String[] w = u.replaceFirst("^CREATE (OR REPLACE )?((NON)?EDITIONABLE )?", "CREATE ").replaceFirst("^CREATE (UNIQUE|BITMAP) ", "CREATE ")
                      .replaceFirst("^CREATE GLOBAL TEMPORARY ", "CREATE ").replaceFirst("^CREATE (PUBLIC|PRIVATE) ", "CREATE ").split(" ");
        if (w.length >= 2 && (w[0].equals("CREATE") || w[0].equals("ALTER") || w[0].equals("DROP"))) {
            String what = w[1].charAt(0) + w[1].substring(1).toLowerCase(Locale.ROOT);
            if (w.length >= 3 && w[1].equals("PACKAGE") && w[2].equals("BODY")) what = "Package body";
            if (w.length >= 3 && w[1].equals("MATERIALIZED")) what = "Materialized view";
            String verb = w[0].equals("CREATE") ? "created." : w[0].equals("ALTER") ? "altered." : "dropped.";
            return what + " " + verb;
        }
        return plsql ? "PL/SQL procedure successfully completed." : "Statement processed.";
    }

    // ---- a result set as aligned columns; numbers to the right in the Oracle door, as SQL*Plus

    static int table(ResultSet r, List<String> o) throws SQLException {
        ResultSetMetaData m = r.getMetaData();
        int n = m.getColumnCount();
        String[] head = new String[n];
        boolean[] num = new boolean[n];
        int[] w = new int[n];
        for (int i = 0; i < n; i++) {
            String l = m.getColumnLabel(i + 1);
            head[i] = (l == null || l.isEmpty()) && !ora ? "(No column name)" : l;
            int t = m.getColumnType(i + 1);
            num[i] = ora && (t == Types.NUMERIC || t == Types.DECIMAL || t == Types.INTEGER || t == Types.BIGINT || t == Types.SMALLINT
                             || t == Types.FLOAT || t == Types.DOUBLE || t == Types.REAL || t == 100 || t == 101);
            w[i] = head[i].length();
        }
        List<String[]> rows = new ArrayList<>();
        while (r.next()) {
            String[] v = new String[n];
            for (int i = 0; i < n; i++) {
                String s = r.getString(i + 1);
                v[i] = s == null ? (ora ? "" : "NULL") : s;
                w[i] = Math.max(w[i], v[i].length());
            }
            rows.add(v);
        }
        o.add(line(head, w, num));
        String[] dash = new String[n];
        for (int i = 0; i < n; i++) dash[i] = "-".repeat(w[i]);
        o.add(line(dash, w, new boolean[n]));
        for (String[] v : rows) o.add(line(v, w, num));
        o.add("");
        o.add("(" + rows.size() + (rows.size() == 1 ? " row" : " rows") + " affected)");
        o.add("");
        return rows.size();
    }

    static String line(String[] v, int[] w, boolean[] right) {
        StringBuilder b = new StringBuilder();
        for (int i = 0; i < v.length; i++) {
            if (i > 0) b.append(' ');
            String pad = " ".repeat(w[i] - v[i].length());
            b.append(right[i] ? pad + v[i] : v[i] + (i == v.length - 1 ? "" : pad));
        }
        return b.toString().stripTrailing();
    }
}
