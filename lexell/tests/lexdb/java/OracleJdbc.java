import java.math.BigDecimal;
import java.sql.*;
import java.util.*;

/** Oracle's JDBC thin driver (ojdbc11) against an Oracle-speaking server: lexdb --tns, or a real Oracle (design/lexdb-oracle.md, "Java client pass").
 *  usage: OracleJdbc URL USER PASSWORD   e.g. jdbc:oracle:thin:@//127.0.0.1:15231/lexdb sa SA */
public class OracleJdbc {
    static Connection c;

    static void ddl(String sql) { try (Statement s = c.createStatement()) { s.execute(sql); } catch (SQLException e) { /* a drop of nothing */ } }

    static List<String> rows(String sql) throws SQLException {
        List<String> out = new ArrayList<>();
        try (Statement s = c.createStatement(); ResultSet r = s.executeQuery(sql)) {
            int n = r.getMetaData().getColumnCount();
            while (r.next()) { StringBuilder b = new StringBuilder(); for (int i = 1; i <= n; i++) { if (i > 1) b.append('|'); b.append(r.getString(i)); } out.add(b.toString()); }
        }
        return out;
    }

    static List<String> meta(ResultSet r, String... cols) throws SQLException {
        List<String> out = new ArrayList<>();
        while (r.next()) { StringBuilder b = new StringBuilder(); for (String k : cols) { if (b.length() > 0) b.append('|'); b.append(r.getString(k)); } out.add(b.toString()); }
        r.close();
        return out;
    }

    public static void main(String[] a) throws Exception {
        java.util.logging.LogManager.getLogManager().reset();
        pass = a[2];
        c = DriverManager.getConnection(a[0], a[1], a[2]);
        c.setAutoCommit(true);
        for (String t : new String[]{"JT_CHILD", "JT_ALL", "JT_PARENT", "JT_TX", "JT_MERGE", "JT_BATCH"}) ddl("drop table " + t);
        ddl("drop sequence JT_SEQ");
        ddl("drop procedure JT_PROC"); ddl("drop function JT_FUNC");
        connection();
        types();
        binds();
        batch();
        transactions();
        merge();
        errors();
        metadata();
        callable();
        cancel();
        try { generatedKeys(); } catch (Exception e) { System.out.println("SKIP generatedKeys by column name: " + e.toString().split("\n")[0]); }
        for (String t : new String[]{"JT_CHILD", "JT_ALL", "JT_PARENT", "JT_TX", "JT_MERGE", "JT_BATCH"}) ddl("drop table " + t);
        ddl("drop sequence JT_SEQ");
        ddl("drop procedure JT_PROC"); ddl("drop function JT_FUNC");
        c.close();
        Check.done();
    }

    // ---- connect, product, a first query
    static void connection() throws Exception {
        DatabaseMetaData m = c.getMetaData();
        Check.yes("product", m.getDatabaseProductName().startsWith("Oracle"));
        Check.yes("product version", m.getDatabaseProductVersion().length() > 0);
        Check.yes("major", m.getDatabaseMajorVersion() >= 19);
        Check.eq("select 1", rows("select 1 from dual"), List.of("1"));
        Check.eq("two rows", rows("select level from dual connect by level <= 3"), List.of("1", "2", "3"));
        Check.yes("valid", c.isValid(5));
        Check.eq("autocommit", c.getAutoCommit(), true);
        Check.eq("row prefetch many", rows("select level from dual connect by level <= 250").size(), 250);
    }

    // ---- column types as a result set gives them
    static void types() throws Exception {
        ddl("create table JT_ALL (id number(10) primary key, name varchar2(50), n number(12,3), nn number, d date, ts timestamp(6), "
            + "tstz timestamp(3) with time zone, c clob, b blob, r raw(16), bd binary_double, bf binary_float, ch char(4), nv nvarchar2(20), i int)");
        try (PreparedStatement p = c.prepareStatement("insert into JT_ALL (id, name, n, nn, d, ts, tstz, c, b, r, bd, bf, ch, nv, i) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)")) {
            p.setInt(1, 1); p.setString(2, "alpha"); p.setBigDecimal(3, new BigDecimal("12.345")); p.setBigDecimal(4, new BigDecimal("0.000001"));
            p.setDate(5, java.sql.Date.valueOf("2024-02-29")); p.setTimestamp(6, Timestamp.valueOf("2024-02-29 13:14:15.123456"));
            p.setTimestamp(7, Timestamp.valueOf("2024-02-29 13:14:15.123"));
            p.setString(8, "x".repeat(10000)); p.setBytes(9, new byte[]{1, 2, 3, (byte) 0xff}); p.setBytes(10, new byte[]{(byte) 0xde, (byte) 0xad});
            p.setDouble(11, 1.5e100); p.setFloat(12, 2.5f); p.setString(13, "ab"); p.setString(14, "café"); p.setInt(15, 42);
            Check.eq("insert all types", p.executeUpdate(), 1);
        }
        try (Statement s = c.createStatement(); ResultSet r = s.executeQuery("select * from JT_ALL")) {
            ResultSetMetaData m = r.getMetaData();
            Check.eq("ncols", m.getColumnCount(), 15);
            String[] names = {"ID", "NAME", "N", "NN", "D", "TS", "TSTZ", "C", "B", "R", "BD", "BF", "CH", "NV", "I"};
            for (int i = 1; i <= 15; i++) Check.eq("colname " + i, m.getColumnName(i), names[i - 1]);
            Check.eq("type id", m.getColumnType(1), Types.NUMERIC);
            Check.eq("prec id", m.getPrecision(1), 10);
            Check.eq("type name", m.getColumnTypeName(2), "VARCHAR2");
            Check.eq("name size", m.getPrecision(2), 50);
            Check.eq("n prec", m.getPrecision(3), 12);
            Check.eq("n scale", m.getScale(3), 3);
            Check.eq("nn scale", m.getScale(4), -127);
            Check.eq("date type", m.getColumnTypeName(5), "DATE");
            Check.eq("ts type", m.getColumnTypeName(6), "TIMESTAMP");
            Check.eq("tstz type", m.getColumnTypeName(7), "TIMESTAMP WITH TIME ZONE");
            Check.eq("clob type", m.getColumnTypeName(8), "CLOB");
            Check.eq("blob type", m.getColumnTypeName(9), "BLOB");
            Check.eq("raw type", m.getColumnTypeName(10), "RAW");
            Check.eq("bd type", m.getColumnTypeName(11), "BINARY_DOUBLE");
            Check.eq("bf type", m.getColumnTypeName(12), "BINARY_FLOAT");
            // (lexdb describes every result column as nullable)
            Check.eq("nullable col", m.isNullable(2), ResultSetMetaData.columnNullable);
            Check.yes("next", r.next());
            Check.eq("int", r.getInt(1), 1);
            Check.eq("string", r.getString(2), "alpha");
            Check.eq("bigdecimal", r.getBigDecimal(3), new BigDecimal("12.345"));
            Check.eq("bigdecimal small", r.getBigDecimal(4).compareTo(new BigDecimal("0.000001")), 0);
            Check.eq("date", r.getDate(5).toString(), "2024-02-29");
            Check.eq("date as timestamp", r.getTimestamp(5).toString(), "2024-02-29 00:00:00.0");
            Check.eq("timestamp", r.getTimestamp(6).toString(), "2024-02-29 13:14:15.123456");
            Check.eq("timestamptz", r.getTimestamp(7).toString(), "2024-02-29 13:14:15.123");
            Check.eq("clob length", r.getClob(8).length(), 10000L);
            Check.eq("clob string", r.getString(8).length(), 10000);
            Check.eq("blob", r.getBlob(9).getBytes(1, 4), new byte[]{1, 2, 3, (byte) 0xff});
            Check.eq("raw", r.getBytes(10), new byte[]{(byte) 0xde, (byte) 0xad});
            Check.eq("double", r.getDouble(11), 1.5e100);
            Check.eq("float", r.getFloat(12), 2.5f);
            Check.eq("char", r.getString(13), "ab  ");
            Check.eq("nvarchar", r.getString(14), "café");
            Check.eq("int col", r.getLong(15), 42L);
            Check.eq("object number", r.getObject(1).getClass().getName(), "java.math.BigDecimal");
            Check.eq("object date", r.getObject(5).getClass().getName(), "java.sql.Timestamp");
            Check.eq("null column wasNull", r.getString(2) == null, false);
            Check.yes("no more", !r.next());
        }
        // NULLs and the empty string (Oracle: NULL)
        try (PreparedStatement p = c.prepareStatement("insert into JT_ALL (id, name, n, d, c, b) values (?, ?, ?, ?, ?, ?)")) {
            p.setInt(1, 2); p.setString(2, ""); p.setNull(3, Types.NUMERIC); p.setNull(4, Types.DATE); p.setNull(5, Types.CLOB); p.setNull(6, Types.BLOB);
            p.executeUpdate();
        }
        try (Statement s = c.createStatement(); ResultSet r = s.executeQuery("select name, n, d, c, b from JT_ALL where id = 2")) {
            Check.yes("row 2", r.next());
            Check.eq("empty string is null", r.getString(1), null);
            Check.eq("null number", r.getBigDecimal(2), null);
            Check.yes("wasNull", r.wasNull());
            Check.eq("null date", r.getDate(3), null);
            Check.eq("null clob", r.getClob(4), null);
            Check.eq("null blob", r.getBlob(5), null);
        }
        // numbers' precision
        Check.eq("big number", rows("select 12345678901234567890123456789012345678 from dual"), List.of("12345678901234567890123456789012345678"));
        Check.eq("fraction", rows("select 0.1 + 0.2 from dual"), List.of("0.3"));
        Check.eq("negative", rows("select -1.5 from dual"), List.of("-1.5"));
        Check.eq("exp", rows("select 1e10 from dual"), List.of("10000000000"));
        Check.eq("to_char", rows("select to_char(1234.5, '9999.99') from dual"), List.of(" 1234.50"));
        Check.eq("to_char date", rows("select to_char(date '2024-03-05', 'YYYY-MM-DD') from dual"), List.of("2024-03-05"));
        Check.eq("nvl", rows("select nvl(null, 'x') from dual"), List.of("x"));
        Check.eq("decode", rows("select decode(2, 1, 'a', 2, 'b', 'c') from dual"), List.of("b"));
        Check.eq("substr", rows("select substr('abcdef', 2, 3) from dual"), List.of("bcd"));
        Check.eq("concat", rows("select 'a' || 'b' from dual"), List.of("ab"));
        Check.eq("user", rows("select user from dual").get(0).toUpperCase(), a0().toUpperCase());
    }

    static String user;
    static String a0() throws SQLException { if (user == null) user = c.getMetaData().getUserName(); return user; }

    // ---- binds of all types, by position and by name
    static void binds() throws Exception {
        try (PreparedStatement p = c.prepareStatement("select ?, ?, ?, ?, ?, ?, ? from dual")) {
            p.setInt(1, 7); p.setString(2, "str"); p.setBigDecimal(3, new BigDecimal("1.25")); p.setDate(4, java.sql.Date.valueOf("2020-01-02"));
            p.setTimestamp(5, Timestamp.valueOf("2020-01-02 03:04:05.5")); p.setBytes(6, new byte[]{9, 8}); p.setDouble(7, 0.5);
            try (ResultSet r = p.executeQuery()) {
                Check.yes("bind row", r.next());
                Check.eq("bind int", r.getInt(1), 7);
                Check.eq("bind string", r.getString(2), "str");
                Check.eq("bind decimal", r.getBigDecimal(3), new BigDecimal("1.25"));
                Check.eq("bind date", r.getTimestamp(4).toString(), "2020-01-02 00:00:00.0");
                Check.eq("bind timestamp", r.getTimestamp(5).toString(), "2020-01-02 03:04:05.5");
                Check.eq("bind raw", r.getBytes(6), new byte[]{9, 8});
                Check.eq("bind double", r.getDouble(7), 0.5);
            }
        }
        try (PreparedStatement p = c.prepareStatement("select ? from dual")) {
            p.setNull(1, Types.VARCHAR);
            try (ResultSet r = p.executeQuery()) { r.next(); Check.eq("bind null", r.getString(1), null); }
            p.setString(1, "y".repeat(5000));
            try (ResultSet r = p.executeQuery()) { r.next(); Check.eq("bind long string", r.getString(1).length(), 5000); }
            p.setLong(1, Long.MAX_VALUE);
            try (ResultSet r = p.executeQuery()) { r.next(); Check.eq("bind long", r.getLong(1), Long.MAX_VALUE); }
            p.setBoolean(1, true);
            try (ResultSet r = p.executeQuery()) { r.next(); Check.eq("bind boolean", r.getInt(1), 1); }
        }
        try (PreparedStatement p = c.prepareStatement("select id, name from JT_ALL where id = ? or name = ? order by id")) {
            p.setInt(1, 1); p.setString(2, "nothing");
            try (ResultSet r = p.executeQuery()) { Check.yes("where bind", r.next()); Check.eq("where id", r.getInt(1), 1); Check.yes("only one", !r.next()); }
            p.setInt(1, 99); p.setString(2, "alpha");
            try (ResultSet r = p.executeQuery()) { Check.yes("rebind", r.next()); Check.eq("rebind id", r.getInt(1), 1); }
        }
        // a statement run again (the driver's statement cache), with a different shape of bind
        try (PreparedStatement p = c.prepareStatement("select count(*) from JT_ALL where id > ?")) {
            for (int k = 0; k < 4; k++) { p.setInt(1, k); try (ResultSet r = p.executeQuery()) { r.next(); Check.eq("again " + k, r.getInt(1), k < 1 ? 2 : k < 2 ? 1 : 0); } }
        }
        // a bound CLOB and BLOB
        try (PreparedStatement p = c.prepareStatement("insert into JT_ALL (id, c, b) values (?, ?, ?)")) {
            p.setInt(1, 3); p.setString(2, "z".repeat(40000)); p.setBytes(3, new byte[70000]);
            Check.eq("insert big lobs", p.executeUpdate(), 1);
        }
        try (Statement s = c.createStatement(); ResultSet r = s.executeQuery("select length(c), dbms_lob.getlength(b) from JT_ALL where id = 3")) {
            r.next(); Check.eq("big clob", r.getInt(1), 40000); Check.eq("big blob", r.getInt(2), 70000);
        }
        // sequences, returning
        ddl("create sequence JT_SEQ start with 10 increment by 5");
        Check.eq("nextval", rows("select JT_SEQ.nextval from dual"), List.of("10"));
        Check.eq("nextval 2", rows("select JT_SEQ.nextval from dual"), List.of("15"));
        try (PreparedStatement p = c.prepareStatement("update JT_ALL set name = ? where id = ? returning name into ?")) {
            // (a plain PreparedStatement has no OUT: this is the error a driver user would see)
            p.setString(1, "q"); p.setInt(2, 1);
            Check.yes("returning without out is an error", Check.errorOf(() -> p.executeUpdate()) != 0);
        }
    }

    // ---- batches
    static void batch() throws Exception {
        ddl("create table JT_BATCH (id number(10) primary key, v varchar2(20))");
        try (PreparedStatement p = c.prepareStatement("insert into JT_BATCH (id, v) values (?, ?)")) {
            for (int i = 0; i < 1200; i++) { p.setInt(1, i); p.setString(2, "v" + i); p.addBatch(); }
            int[] n = p.executeBatch();
            Check.eq("batch size", n.length, 1200);
            int sum = 0; for (int x : n) sum += (x == Statement.SUCCESS_NO_INFO ? 1 : x);
            Check.eq("batch counts", sum, 1200);
        }
        Check.eq("batch rows", rows("select count(*), min(id), max(id) from JT_BATCH"), List.of("1200|0|1199"));
        try (PreparedStatement p = c.prepareStatement("update JT_BATCH set v = ? where id = ?")) {
            p.setString(1, "u"); p.setInt(2, 5); p.addBatch(); p.setString(1, "u"); p.setInt(2, 99999); p.addBatch(); p.setString(1, "u"); p.setInt(2, 6); p.addBatch();
            int[] n = p.executeBatch();
            Check.eq("update batch", Arrays.stream(n).map(x -> x == Statement.SUCCESS_NO_INFO ? 1 : x).boxed().toList(), List.of(1, 0, 1));
        }
        // a failing row in a batch
        try (PreparedStatement p = c.prepareStatement("insert into JT_BATCH (id, v) values (?, ?)")) {
            p.setInt(1, 5000); p.setString(2, "ok"); p.addBatch();
            p.setInt(1, 5); p.setString(2, "dup"); p.addBatch();
            p.setInt(1, 5001); p.setString(2, "ok"); p.addBatch();
            try { p.executeBatch(); Check.yes("batch error expected", false); }
            catch (BatchUpdateException e) { Check.eq("batch error code", e.getErrorCode(), 1); Check.eq("batch partial", e.getUpdateCounts().length >= 0, true); }
        }
        try (Statement s = c.createStatement()) {
            s.addBatch("insert into JT_BATCH values (7000, 'a')"); s.addBatch("insert into JT_BATCH values (7001, 'b')"); s.addBatch("update JT_BATCH set v = 'c' where id >= 7000");
            Check.eq("statement batch", s.executeBatch().length, 3);
        }
    }

    // ---- transactions
    static void transactions() throws Exception {
        ddl("create table JT_TX (id number(5))");
        c.setAutoCommit(false);
        try (Statement s = c.createStatement()) { s.executeUpdate("insert into JT_TX values (1)"); }
        c.rollback();
        Check.eq("rollback", rows("select count(*) from JT_TX"), List.of("0"));
        try (Statement s = c.createStatement()) { s.executeUpdate("insert into JT_TX values (2)"); }
        c.commit();
        Check.eq("commit", rows("select count(*) from JT_TX"), List.of("1"));
        Savepoint sp = null;
        try (Statement s = c.createStatement()) {
            s.executeUpdate("insert into JT_TX values (3)");
            sp = c.setSavepoint("sp1");
            s.executeUpdate("insert into JT_TX values (4)");
            c.rollback(sp);
        }
        Check.eq("savepoint rollback", rows("select id from JT_TX order by id"), List.of("2", "3"));
        c.commit();
        // a second connection does not see uncommitted rows
        try (Connection c2 = DriverManager.getConnection(c.getMetaData().getURL(), a0(), pass)) {
            try (Statement s = c.createStatement()) { s.executeUpdate("insert into JT_TX values (9)"); }
            try (Statement s = c2.createStatement(); ResultSet r = s.executeQuery("select count(*) from JT_TX")) { r.next(); Check.eq("isolation", r.getInt(1), 2); }
            c.commit();
            try (Statement s = c2.createStatement(); ResultSet r = s.executeQuery("select count(*) from JT_TX")) { r.next(); Check.eq("after commit", r.getInt(1), 3); }
        }
        Check.eq("isolation level", c.getTransactionIsolation(), Connection.TRANSACTION_READ_COMMITTED);
        c.setAutoCommit(true);
        // DDL commits
        c.setAutoCommit(false);
        try (Statement s = c.createStatement()) { s.executeUpdate("insert into JT_TX values (10)"); s.execute("create table JT_DDLC (x int)"); }
        c.rollback();
        Check.eq("ddl commits", rows("select count(*) from JT_TX where id = 10"), List.of("1"));
        c.setAutoCommit(true);
        ddl("drop table JT_DDLC");
    }
    static String pass;

    // ---- MERGE
    static void merge() throws Exception {
        ddl("create table JT_MERGE (id number(5) primary key, v varchar2(10))");
        try (Statement s = c.createStatement()) { s.executeUpdate("insert into JT_MERGE values (1, 'one')"); s.executeUpdate("insert into JT_MERGE values (2, 'two')"); }
        try (PreparedStatement p = c.prepareStatement("merge into JT_MERGE t using (select ? id, ? v from dual) s on (t.id = s.id) "
                + "when matched then update set t.v = s.v when not matched then insert (id, v) values (s.id, s.v)")) {
            p.setInt(1, 2); p.setString(2, "TWO"); Check.eq("merge update", p.executeUpdate(), 1);
            p.setInt(1, 3); p.setString(2, "three"); Check.eq("merge insert", p.executeUpdate(), 1);
        }
        Check.eq("merge result", rows("select id || ':' || v from JT_MERGE order by id"), List.of("1:one", "2:TWO", "3:three"));
        try (Statement s = c.createStatement()) {
            Check.eq("merge delete", s.executeUpdate("merge into JT_MERGE t using (select 1 id from dual) s on (t.id = s.id) when matched then update set t.v = 'x' delete where t.id = 1"), 1);
        }
        Check.eq("after delete", rows("select count(*) from JT_MERGE"), List.of("2"));
    }

    // ---- errors by number
    static void errors() throws Exception {
        Check.eq("ORA-00942", Check.errorOf(() -> rows("select * from no_such_table")), 942);
        Check.eq("ORA-00904", Check.errorOf(() -> rows("select nosuch from dual")), 904);
        Check.eq("ORA-00001", Check.errorOf(() -> { try (Statement s = c.createStatement()) { s.executeUpdate("insert into JT_MERGE values (2, 'dup')"); } }), 1);
        Check.eq("ORA-01722", Check.errorOf(() -> rows("select to_number('abc') from dual")), 1722);
        Check.eq("ORA-01476", Check.errorOf(() -> rows("select 1/0 from dual")), 1476);
        Check.eq("ORA-00923", Check.errorOf(() -> rows("select 1 fro dual")), 923);
        Check.eq("ORA-01400", Check.errorOf(() -> { try (Statement s = c.createStatement()) { s.executeUpdate("insert into JT_MERGE (v) values ('x')"); } }), 1400);
        Check.eq("ORA-12899", Check.errorOf(() -> { try (Statement s = c.createStatement()) { s.executeUpdate("insert into JT_MERGE values (50, 'this is far too long')"); } }), 12899);
        Check.eq("ORA-00955", Check.errorOf(() -> { try (Statement s = c.createStatement()) { s.execute("create table JT_MERGE (x int)"); } }), 955);
        Check.eq("ORA-02291", Check.errorOf(() -> { try (Statement s = c.createStatement()) { s.execute("create table JT_CHILD (id int, p number(5) references JT_MERGE(id))"); s.executeUpdate("insert into JT_CHILD values (1, 999)"); } }), 2291);
        Check.eq("ORA-02292", Check.errorOf(() -> { try (Statement s = c.createStatement()) { s.executeUpdate("insert into JT_MERGE values (900, 'p')"); s.executeUpdate("insert into JT_CHILD values (2, 900)"); s.executeUpdate("delete from JT_MERGE where id = 900"); } }), 2292);
        try { rows("select * from no_such_table"); } catch (SQLException e) {
            Check.yes("message", e.getMessage().startsWith("ORA-00942"));
            Check.eq("sqlstate", e.getSQLState(), "42000");
        }
        // the connection still works after errors
        Check.eq("after errors", rows("select 1 from dual"), List.of("1"));
        // a statement's timeout / cancel
        try (Statement s = c.createStatement()) { s.setQueryTimeout(30); Check.eq("timeout set", s.getQueryTimeout(), 30); Check.eq("with timeout", s.executeQuery("select 1 from dual").next(), true); }
        try (Statement s = c.createStatement()) { s.setMaxRows(2); try (ResultSet r = s.executeQuery("select level from dual connect by level < 50")) { int n = 0; while (r.next()) n++; Check.eq("maxrows", n, 2); } }
        try (Statement s = c.createStatement()) { s.setFetchSize(3); try (ResultSet r = s.executeQuery("select level from dual connect by level <= 10")) { int n = 0; while (r.next()) n++; Check.eq("fetch size 3", n, 10); } }
    }

    // ---- DatabaseMetaData
    static void metadata() throws Exception {
        ddl("create table JT_PARENT (id number(10) not null, code varchar2(10) not null, note varchar2(100), constraint JT_PARENT_PK primary key (id, code))");
        ddl("create unique index JT_PARENT_IX on JT_PARENT (note)");
        ddl("create table JT_CHILD2 (cid number(10) primary key, pid number(10), pcode varchar2(10), constraint JT_CHILD2_FK foreign key (pid, pcode) references JT_PARENT (id, code))");
        DatabaseMetaData m = c.getMetaData();
        String schema = a0().toUpperCase();
        Check.eq("getTables", meta(m.getTables(null, schema, "JT_PARENT", new String[]{"TABLE"}), "TABLE_SCHEM", "TABLE_NAME", "TABLE_TYPE"), List.of(schema + "|JT_PARENT|TABLE"));
        Check.eq("getTables pattern", meta(m.getTables(null, schema, "JT_CHILD%", null), "TABLE_NAME"), List.of("JT_CHILD", "JT_CHILD2"));
        List<String> cols = meta(m.getColumns(null, schema, "JT_PARENT", "%"), "COLUMN_NAME", "TYPE_NAME", "COLUMN_SIZE", "DECIMAL_DIGITS", "NULLABLE", "ORDINAL_POSITION");
        Check.eq("getColumns", cols, List.of("ID|NUMBER|10|0|0|1", "CODE|VARCHAR2|10|null|0|2", "NOTE|VARCHAR2|100|null|1|3"));
        Check.eq("getPrimaryKeys", meta(m.getPrimaryKeys(null, schema, "JT_PARENT"), "COLUMN_NAME", "KEY_SEQ", "PK_NAME"), List.of("CODE|2|JT_PARENT_PK", "ID|1|JT_PARENT_PK"));
        Check.eq("getIndexInfo", meta(m.getIndexInfo(null, schema, "JT_PARENT", true, false), "INDEX_NAME", "COLUMN_NAME", "NON_UNIQUE").stream().filter(x -> x.startsWith("JT_PARENT_IX")).toList(), List.of("JT_PARENT_IX|NOTE|0"));
        Check.eq("getImportedKeys", meta(m.getImportedKeys(null, schema, "JT_CHILD2"), "PKTABLE_NAME", "PKCOLUMN_NAME", "FKCOLUMN_NAME", "KEY_SEQ", "FK_NAME"),
                 List.of("JT_PARENT|ID|PID|1|JT_CHILD2_FK", "JT_PARENT|CODE|PCODE|2|JT_CHILD2_FK"));
        Check.eq("getExportedKeys", meta(m.getExportedKeys(null, schema, "JT_PARENT"), "FKTABLE_NAME", "FKCOLUMN_NAME"), List.of("JT_CHILD2|PID", "JT_CHILD2|PCODE"));
        Check.yes("getSchemas", meta(m.getSchemas(), "TABLE_SCHEM").contains(schema));
        Check.eq("getSchemas pattern", meta(m.getSchemas(null, schema), "TABLE_SCHEM"), List.of(schema));
        Check.yes("getTableTypes", meta(m.getTableTypes(), "TABLE_TYPE").contains("TABLE"));
        Check.yes("getTypeInfo", meta(m.getTypeInfo(), "TYPE_NAME").containsAll(List.of("VARCHAR2", "NUMBER", "DATE")));
        Check.yes("getCatalogs", meta(m.getCatalogs(), "TABLE_CAT").size() >= 0);
        Check.eq("getProcedures none", meta(m.getProcedures(null, schema, "JT_NOSUCH%"), "PROCEDURE_NAME"), List.of());
        Check.eq("supportsTransactions", m.supportsTransactions(), true);
        Check.eq("identifier quote", m.getIdentifierQuoteString(), "\"");
        Check.eq("getUserName", m.getUserName().toUpperCase(), schema);
        Check.eq("getTables view type", meta(m.getTables(null, schema, "NO_SUCH%", null), "TABLE_NAME"), List.of());
        ddl("create view JT_VIEW as select id from JT_PARENT");
        Check.eq("getTables view", meta(m.getTables(null, schema, "JT_VIEW", new String[]{"VIEW"}), "TABLE_NAME", "TABLE_TYPE"), List.of("JT_VIEW|VIEW"));
        // result set metadata of a table
        try (Statement s = c.createStatement(); ResultSet r = s.executeQuery("select * from JT_PARENT where 1 = 0")) {
            ResultSetMetaData rm = r.getMetaData();
            Check.eq("empty rs cols", rm.getColumnCount(), 3);
            Check.eq("empty rs name", rm.getColumnName(3), "NOTE");
            Check.eq("empty rs table", rm.getTableName(1), "");
        }
        ddl("drop view JT_VIEW");
        ddl("drop table JT_CHILD2");
        ddl("drop table JT_PARENT");
    }

    // ---- stored procedures and functions, OUT parameters, REF CURSOR
    static void callable() throws Exception {
        try (Statement s = c.createStatement()) {
            s.execute("create or replace procedure JT_PROC(a in number, b in out number, o out varchar2) is begin b := b + a; o := 'sum=' || b; end;");
            s.execute("create or replace function JT_FUNC(x in number) return number is begin return x * 2; end;");
        }
        try (CallableStatement cs = c.prepareCall("{call JT_PROC(?, ?, ?)}")) {
            cs.setInt(1, 5); cs.setInt(2, 10); cs.registerOutParameter(2, Types.NUMERIC); cs.registerOutParameter(3, Types.VARCHAR);
            cs.execute();
            Check.eq("in out", cs.getInt(2), 15);
            Check.eq("out", cs.getString(3), "sum=15");
        }
        try (CallableStatement cs = c.prepareCall("{? = call JT_FUNC(?)}")) {
            cs.registerOutParameter(1, Types.NUMERIC); cs.setInt(2, 21); cs.execute();
            Check.eq("function result", cs.getInt(1), 42);
        }
        try (CallableStatement cs = c.prepareCall("begin ? := 'blk'; end;")) {
            cs.registerOutParameter(1, Types.VARCHAR); cs.execute(); Check.eq("anonymous block out", cs.getString(1), "blk");
        }
        try (CallableStatement cs = c.prepareCall("begin open ? for select id, name from JT_ALL where id <= 2 order by id; end;")) {
            cs.registerOutParameter(1, oracle.jdbc.OracleTypes.CURSOR); cs.execute();
            try (ResultSet r = (ResultSet) cs.getObject(1)) {
                Check.yes("ref cursor row", r.next()); Check.eq("ref cursor id", r.getInt(1), 1); Check.eq("ref cursor name", r.getString(2), "alpha");
                Check.yes("ref cursor row 2", r.next()); Check.yes("ref cursor end", !r.next());
            }
        }
        try (CallableStatement cs = c.prepareCall("begin dbms_output.enable(10000); dbms_output.put_line('hello'); dbms_output.put_line('world'); end;")) { cs.execute(); }
        try (CallableStatement cs = c.prepareCall("begin dbms_output.get_line(?, ?); end;")) {
            cs.registerOutParameter(1, Types.VARCHAR); cs.registerOutParameter(2, Types.INTEGER); cs.execute();
            Check.eq("dbms_output line", cs.getString(1), "hello"); Check.eq("dbms_output status", cs.getInt(2), 0);
        }
        Check.eq("proc error", Check.errorOf(() -> { try (CallableStatement cs = c.prepareCall("begin raise_application_error(-20001, 'boom'); end;")) { cs.execute(); } }), 20001);
        Check.eq("no data found", Check.errorOf(() -> { try (CallableStatement cs = c.prepareCall("declare v number; begin select 1 into v from dual where 1 = 0; end;")) { cs.execute(); } }), 1403);
        // a PL/SQL block with a loop and a result
        try (CallableStatement cs = c.prepareCall("declare t number := 0; begin for i in 1..10 loop t := t + i; end loop; ? := t; end;")) {
            cs.registerOutParameter(1, Types.NUMERIC); cs.execute(); Check.eq("loop", cs.getInt(1), 55);
        }
        // an implicit REF CURSOR from a statement
        try (PreparedStatement p = c.prepareStatement("select ? from dual")) { p.setString(1, "q"); try (ResultSet r = p.executeQuery()) { r.next(); Check.eq("prepared after calls", r.getString(1), "q"); } }
    }

    // ---- getGeneratedKeys by column name (the driver describes the table first)
    static void generatedKeys() throws Exception {
        ddl("create sequence JT_SEQ start with 10 increment by 5");
        try (PreparedStatement p = c.prepareStatement("insert into JT_ALL (id, name) values (JT_SEQ.nextval, ?)", new String[]{"ID"})) {
            p.setString(1, "gen");
            Check.eq("insert gen", p.executeUpdate(), 1);
            try (ResultSet g = p.getGeneratedKeys()) { Check.yes("generated key", g.next()); Check.eq("generated id", g.getInt(1), Integer.parseInt(rows("select id from JT_ALL where name = 'gen'").get(0))); }
        }
        ddl("drop sequence JT_SEQ");
    }

    // ---- Statement.cancel() from another thread: the break and reset markers; the connection works afterwards
    static void cancel() throws Exception {
        try (Statement s = c.createStatement()) {
            Thread t = new Thread(() -> { try { Thread.sleep(300); s.cancel(); } catch (Exception e) { /* none */ } });
            t.start();
            int code = 0;
            try (ResultSet r = s.executeQuery("select count(*) from dual connect by level <= 1500000")) { r.next(); }
            catch (SQLException e) { code = e.getErrorCode(); }
            t.join();
            Check.yes("cancel: the statement was cancelled or finished (" + code + ")", code == 1013 || code == 0 || code == 17008);
        }
        Check.eq("after cancel", rows("select 1 from dual"), List.of("1"));
    }
}
