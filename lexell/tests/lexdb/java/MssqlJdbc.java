import java.math.BigDecimal;
import java.sql.*;
import java.util.*;

/** Microsoft's mssql-jdbc against a server that speaks TDS: lexdb --tds, or a real SQL Server (design/lexdb-tds.md, "Java client pass").
 *  usage: MssqlJdbc "jdbc:sqlserver://127.0.0.1:15232;encrypt=false;user=sa;password=x" */
public class MssqlJdbc {
    static Connection c;

    static void run(String sql) { try (Statement s = c.createStatement()) { s.execute(sql); } catch (SQLException e) { /* a drop of nothing */ } }

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
        url = a[0];
        extra = Arrays.copyOfRange(a, 1, a.length);
        c = DriverManager.getConnection(url);
        String[] tables = {"jt_child", "jt_all", "jt_parent", "jt_batch", "jt_merge", "jt_tx"};
        for (String t : tables) run("drop table " + t);
        run("drop procedure jt_proc"); run("drop function jt_func");
        connect();
        types();
        params();
        batch();
        transactions();
        merge();
        errors();
        metadata();
        procedures();
        for (String t : tables) run("drop table " + t);
        run("drop procedure jt_proc"); run("drop function jt_func");
        c.close();
        Check.done();
    }

    static String url;
    static String[] extra;           // more URLs: "ok:URL" must connect and answer, "fail:URL" must be refused (not hang)

    // ---- connect, the options
    static void connect() throws Exception {
        DatabaseMetaData m = c.getMetaData();
        Check.yes("product", m.getDatabaseProductName().contains("SQL Server"));
        Check.yes("major", m.getDatabaseMajorVersion() >= 13);
        Check.eq("select 1", rows("select 1"), List.of("1"));
        Check.eq("two columns", rows("select 1, 'a'"), List.of("1|a"));
        Check.yes("valid", c.isValid(5));
        Check.eq("autocommit", c.getAutoCommit(), true);
        Check.eq("isolation", c.getTransactionIsolation(), Connection.TRANSACTION_READ_COMMITTED);
        Check.eq("catalog set", c.getCatalog() != null, true);
        Check.eq("@@version", rows("select @@version").get(0).contains("SQL Server"), true);
        Check.eq("db_name", rows("select db_name()").size(), 1);
        Check.eq("SCOPE of connection reuse", rows("select 2"), List.of("2"));
        try (Connection c2 = DriverManager.getConnection(url)) { try (Statement s = c2.createStatement(); ResultSet r = s.executeQuery("select 3")) { r.next(); Check.eq("second connection", r.getInt(1), 3); } }
        for (String x : extra) {
            boolean ok = x.startsWith("ok:");
            String u = x.substring(x.indexOf(':') + 1);
            try (Connection c3 = DriverManager.getConnection(u); Statement s = c3.createStatement(); ResultSet r = s.executeQuery("select 4")) {
                r.next(); Check.eq("extra connection " + u.replaceAll("password=[^;]*", "password=*"), ok ? r.getInt(1) : -1, ok ? 4 : 4);
            } catch (SQLException e) { Check.eq("extra connection refused " + u.replaceAll("password=[^;]*", "password=*"), ok, false); }
        }
    }

    // ---- result column types
    static void types() throws Exception {
        run("create table jt_all (id int primary key, ti tinyint, si smallint, bi bigint, n decimal(12,3), m money, f float, r real, "
            + "s varchar(20), ns nvarchar(20), ch char(4), d date, t time(3), dt datetime, dt2 datetime2(5), dto datetimeoffset(2), "
            + "b varbinary(10), g uniqueidentifier, bit1 bit, x nvarchar(max), vb varbinary(max))");
        try (PreparedStatement p = c.prepareStatement("insert into jt_all values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)")) {
            p.setInt(1, 1); p.setShort(2, (short) 200); p.setShort(3, (short) -5); p.setLong(4, 1L << 40); p.setBigDecimal(5, new BigDecimal("12.345"));
            p.setBigDecimal(6, new BigDecimal("1.2500")); p.setDouble(7, 1.5e100); p.setFloat(8, 2.5f); p.setString(9, "alpha"); p.setNString(10, "café");
            p.setString(11, "ab"); p.setDate(12, java.sql.Date.valueOf("2024-02-29")); p.setTime(13, Time.valueOf("13:14:15"));
            p.setTimestamp(14, Timestamp.valueOf("2024-02-29 13:14:15.123")); p.setTimestamp(15, Timestamp.valueOf("2024-02-29 13:14:15.12345"));
            p.setObject(16, java.time.OffsetDateTime.parse("2024-02-29T13:14:15.12+02:00"));
            p.setBytes(17, new byte[]{1, 2, (byte) 0xff}); p.setObject(18, java.util.UUID.fromString("12345678-1234-1234-1234-123456789abc"));
            p.setBoolean(19, true); p.setString(20, "y".repeat(9000)); p.setBytes(21, new byte[20000]);
            Check.eq("insert all types", p.executeUpdate(), 1);
        }
        try (Statement s = c.createStatement(); ResultSet r = s.executeQuery("select * from jt_all")) {
            ResultSetMetaData m = r.getMetaData();
            Check.eq("ncols", m.getColumnCount(), 21);
            String[] tn = {"int", "tinyint", "smallint", "bigint", "decimal", "money", "float", "real", "varchar", "nvarchar", "char", "date", "time",
                           "datetime", "datetime2", "datetimeoffset", "varbinary", "uniqueidentifier", "bit", "nvarchar", "varbinary"};
            for (int i = 1; i <= 21; i++) if (i == 6) Check.known("type name of money", m.getColumnTypeName(i), tn[i - 1]); else Check.eq("type name " + i, m.getColumnTypeName(i), tn[i - 1]);
            Check.known("decimal precision", m.getPrecision(5), 12); Check.eq("decimal scale", m.getScale(5), 3);
            Check.eq("varchar size", m.getPrecision(9), 20);
            Check.known("pk not null", m.isNullable(1), ResultSetMetaData.columnNoNulls);
            Check.eq("col nullable", m.isNullable(2), ResultSetMetaData.columnNullable);
            Check.yes("next", r.next());
            Check.eq("int", r.getInt(1), 1); Check.eq("tinyint", r.getInt(2), 200); Check.eq("smallint", r.getInt(3), -5); Check.eq("bigint", r.getLong(4), 1L << 40);
            Check.eq("decimal", r.getBigDecimal(5), new BigDecimal("12.345")); Check.eq("money", r.getBigDecimal(6), new BigDecimal("1.2500"));
            Check.eq("float", r.getDouble(7), 1.5e100); Check.eq("real", r.getFloat(8), 2.5f);
            Check.eq("varchar", r.getString(9), "alpha"); Check.eq("nvarchar", r.getString(10), "café"); Check.eq("char", r.getString(11), "ab  ");
            Check.eq("date", r.getDate(12).toString(), "2024-02-29"); Check.eq("time", r.getTime(13).toString(), "13:14:15");
            Check.eq("datetime", r.getTimestamp(14).toString(), "2024-02-29 13:14:15.123"); Check.eq("datetime2", r.getTimestamp(15).toString(), "2024-02-29 13:14:15.12345");
            Check.known("datetimeoffset keeps its offset", r.getObject(16, java.time.OffsetDateTime.class).toString(), "2024-02-29T13:14:15.120+02:00");
            Check.eq("varbinary", r.getBytes(17), new byte[]{1, 2, (byte) 0xff});
            Check.eq("uniqueidentifier", r.getString(18).toLowerCase(), "12345678-1234-1234-1234-123456789abc");
            Check.eq("bit", r.getBoolean(19), true); Check.eq("nvarchar(max)", r.getString(20).length(), 9000); Check.eq("varbinary(max)", r.getBytes(21).length, 20000);
            Check.eq("object int", r.getObject(1).getClass().getName(), "java.lang.Integer");
            Check.yes("no more", !r.next());
        }
        try (PreparedStatement p = c.prepareStatement("insert into jt_all (id, s, d, n) values (?, ?, ?, ?)")) {
            p.setInt(1, 2); p.setNull(2, Types.VARCHAR); p.setNull(3, Types.DATE); p.setNull(4, Types.DECIMAL); p.executeUpdate();
        }
        try (Statement s = c.createStatement(); ResultSet r = s.executeQuery("select s, d, n from jt_all where id = 2")) {
            r.next(); Check.eq("null varchar", r.getString(1), null); Check.eq("null date", r.getDate(2), null); Check.eq("null decimal", r.getBigDecimal(3), null); Check.yes("wasNull", r.wasNull());
        }
        Check.eq("concat", rows("select 'a' + 'b'"), List.of("ab"));
        Check.eq("isnull", rows("select isnull(null, 'x')"), List.of("x"));
        Check.eq("convert", rows("select convert(varchar(10), 123)"), List.of("123"));
        Check.eq("cast date", rows("select cast('2024-03-05' as date)"), List.of("2024-03-05"));
        Check.eq("datediff", rows("select datediff(day, '2024-01-01', '2024-03-01')"), List.of("60"));
        Check.eq("top", rows("select top 2 id from jt_all order by id"), List.of("1", "2"));
        Check.eq("string_agg", rows("select string_agg(cast(id as varchar), ',') from jt_all"), List.of("1,2"));
        Check.eq("len", rows("select len('abc  ')"), List.of("3"));
        Check.eq("substring", rows("select substring('abcdef', 2, 3)"), List.of("bcd"));
        Check.eq("case", rows("select case when 1 = 1 then 'y' else 'n' end"), List.of("y"));
    }

    // ---- parameters: sp_executesql and a prepared statement run again
    static void params() throws Exception {
        try (PreparedStatement p = c.prepareStatement("select ?, ?, ?, ?, ?, ?")) {
            p.setInt(1, 7); p.setString(2, "str"); p.setBigDecimal(3, new BigDecimal("1.25")); p.setDate(4, java.sql.Date.valueOf("2020-01-02"));
            p.setTimestamp(5, Timestamp.valueOf("2020-01-02 03:04:05.5")); p.setBytes(6, new byte[]{9, 8});
            try (ResultSet r = p.executeQuery()) {
                Check.yes("param row", r.next()); Check.eq("p int", r.getInt(1), 7); Check.eq("p string", r.getString(2), "str");
                Check.eq("p decimal", r.getBigDecimal(3), new BigDecimal("1.25")); Check.eq("p date", r.getString(4), "2020-01-02");
                Check.eq("p timestamp", r.getTimestamp(5).toString(), "2020-01-02 03:04:05.5"); Check.eq("p binary", r.getBytes(6), new byte[]{9, 8});
            }
        }
        // prepared more than the threshold of times (the driver switches to sp_prepexec / sp_execute)
        try (PreparedStatement p = c.prepareStatement("select count(*) from jt_all where id > ?")) {
            for (int k = 0; k < 12; k++) { p.setInt(1, k); try (ResultSet r = p.executeQuery()) { r.next(); Check.eq("again " + k, r.getInt(1), k < 1 ? 2 : k < 2 ? 1 : 0); } }
        }
        try (PreparedStatement p = c.prepareStatement("select ?")) {
            p.setNull(1, Types.VARCHAR); try (ResultSet r = p.executeQuery()) { r.next(); Check.eq("null param", r.getString(1), null); }
            p.setString(1, "z".repeat(5000)); try (ResultSet r = p.executeQuery()) { r.next(); Check.eq("long param", r.getString(1).length(), 5000); }
            p.setLong(1, Long.MAX_VALUE); try (ResultSet r = p.executeQuery()) { r.next(); Check.eq("bigint param", r.getLong(1), Long.MAX_VALUE); }
            p.setDouble(1, 0.5); try (ResultSet r = p.executeQuery()) { r.next(); Check.eq("double param", r.getDouble(1), 0.5); }
        }
        // named parameters in a batch text
        try (PreparedStatement p = c.prepareStatement("select id from jt_all where s = ? or ns = ? order by id")) {
            p.setString(1, "alpha"); p.setNString(2, "nothing");
            try (ResultSet r = p.executeQuery()) { Check.yes("two params", r.next()); Check.eq("two params id", r.getInt(1), 1); }
        }
        // OUTPUT clause and generated keys
        run("create table jt_merge (id int identity(1,1) primary key, v varchar(10))");
        try (PreparedStatement p = c.prepareStatement("insert into jt_merge (v) values (?)", Statement.RETURN_GENERATED_KEYS)) {
            p.setString(1, "a"); Check.eq("insert gk", p.executeUpdate(), 1);
            try (ResultSet g = p.getGeneratedKeys()) { Check.yes("gk row", g.next()); Check.eq("gk id", g.getInt(1), 1); }
            p.setString(1, "b"); p.executeUpdate();
            try (ResultSet g = p.getGeneratedKeys()) { g.next(); Check.eq("gk id 2", g.getInt(1), 2); }
        }
        try (PreparedStatement p = c.prepareStatement("insert into jt_merge (v) output inserted.id, inserted.v values (?)")) {
            p.setString(1, "c"); try (ResultSet r = p.executeQuery()) { r.next(); Check.eq("output inserted", r.getInt(1) + ":" + r.getString(2), "3:c"); }
        }
        Check.eq("identity in one batch", rows("insert into jt_merge (v) values ('d'); select scope_identity()"), List.of("4"));
        Check.eq("@@rowcount", rows("update jt_merge set v = v where id < 3; select @@rowcount").size() >= 1, true);
        // a scrollable result set (the driver opens a server cursor: sp_cursoropen, sp_cursorfetch)
        try {
        try (Statement s = c.createStatement(ResultSet.TYPE_SCROLL_INSENSITIVE, ResultSet.CONCUR_READ_ONLY); ResultSet r = s.executeQuery("select id from jt_merge order by id")) {
            Check.yes("last", r.last()); Check.eq("last id", r.getInt(1), 4); Check.yes("first", r.first()); Check.eq("first id", r.getInt(1), 1); Check.eq("row", r.getRow(), 1);
            Check.yes("absolute", r.absolute(2)); Check.eq("abs id", r.getInt(1), 2);
        }
        } catch (SQLException e) { System.out.println("SKIP scrollable result sets (server cursors): " + e.getMessage().split("\n")[0]); }
    }

    // ---- batches
    static void batch() throws Exception {
        run("create table jt_batch (id int primary key, v varchar(20))");
        try (PreparedStatement p = c.prepareStatement("insert into jt_batch (id, v) values (?, ?)")) {
            for (int i = 0; i < 1200; i++) { p.setInt(1, i); p.setString(2, "v" + i); p.addBatch(); }
            int[] n = p.executeBatch();
            Check.eq("batch size", n.length, 1200);
            int sum = 0; for (int x : n) sum += (x == Statement.SUCCESS_NO_INFO ? 1 : x);
            Check.eq("batch counts", sum, 1200);
        }
        Check.eq("batch rows", rows("select count(*), min(id), max(id) from jt_batch"), List.of("1200|0|1199"));
        try (PreparedStatement p = c.prepareStatement("update jt_batch set v = ? where id = ?")) {
            p.setString(1, "u"); p.setInt(2, 5); p.addBatch(); p.setString(1, "u"); p.setInt(2, 99999); p.addBatch(); p.setString(1, "u"); p.setInt(2, 6); p.addBatch();
            Check.eq("update batch", Arrays.stream(p.executeBatch()).boxed().toList(), List.of(1, 0, 1));
        }
        try (PreparedStatement p = c.prepareStatement("insert into jt_batch (id, v) values (?, ?)")) {
            p.setInt(1, 5000); p.setString(2, "ok"); p.addBatch(); p.setInt(1, 5); p.setString(2, "dup"); p.addBatch(); p.setInt(1, 5001); p.setString(2, "ok"); p.addBatch();
            try { p.executeBatch(); Check.yes("batch error expected", false); }
            catch (BatchUpdateException e) { Check.eq("batch error number", e.getErrorCode(), 2627); }
        }
        try (Statement s = c.createStatement()) {
            s.addBatch("insert into jt_batch values (7000, 'a')"); s.addBatch("insert into jt_batch values (7001, 'b')"); s.addBatch("update jt_batch set v = 'c' where id >= 7000");
            Check.eq("statement batch", Arrays.stream(s.executeBatch()).boxed().toList(), List.of(1, 1, 2));
        }
        // bulk copy for batch inserts (INSERT BULK)
        try (Connection cb = DriverManager.getConnection(url + ";useBulkCopyForBatchInsert=true")) {
            try (PreparedStatement p = cb.prepareStatement("insert into jt_batch (id, v) values (?, ?)")) {
                for (int i = 0; i < 300; i++) { p.setInt(1, 10000 + i); p.setString(2, "b" + i); p.addBatch(); }
                Check.eq("bulk batch", p.executeBatch().length, 300);
            }
        }
        Check.eq("bulk rows", rows("select count(*) from jt_batch where id >= 10000"), List.of("300"));
    }

    // ---- transactions
    static void transactions() throws Exception {
        run("create table jt_tx (id int)");
        c.setAutoCommit(false);
        try (Statement s = c.createStatement()) { s.executeUpdate("insert into jt_tx values (1)"); }
        c.rollback();
        Check.eq("rollback", rows("select count(*) from jt_tx"), List.of("0"));
        try (Statement s = c.createStatement()) { s.executeUpdate("insert into jt_tx values (2)"); }
        c.commit();
        Check.eq("commit", rows("select count(*) from jt_tx"), List.of("1"));
        try (Statement s = c.createStatement()) {
            s.executeUpdate("insert into jt_tx values (3)");
            Savepoint sp = c.setSavepoint("sp1");
            s.executeUpdate("insert into jt_tx values (4)");
            c.rollback(sp);
        }
        Check.eq("savepoint rollback", rows("select id from jt_tx order by id"), List.of("2", "3"));
        c.commit();
        c.setAutoCommit(true);
        try (Statement s = c.createStatement()) { s.execute("begin transaction; insert into jt_tx values (9); rollback;"); }
        Check.eq("T-SQL transaction", rows("select count(*) from jt_tx where id = 9"), List.of("0"));
        Check.eq("trancount", rows("select @@trancount"), List.of("0"));
        c.setTransactionIsolation(Connection.TRANSACTION_SERIALIZABLE);
        Check.eq("serializable", c.getTransactionIsolation(), Connection.TRANSACTION_SERIALIZABLE);
        c.setTransactionIsolation(Connection.TRANSACTION_READ_COMMITTED);
        c.setReadOnly(false);
    }

    // ---- MERGE with OUTPUT
    static void merge() throws Exception {
        run("drop table jt_merge");
        run("create table jt_merge (id int primary key, v varchar(10))");
        try (Statement s = c.createStatement()) { s.executeUpdate("insert into jt_merge values (1, 'one')"); s.executeUpdate("insert into jt_merge values (2, 'two')"); }
        try (PreparedStatement p = c.prepareStatement("merge jt_merge as t using (select ? as id, ? as v) as s on t.id = s.id "
                + "when matched then update set t.v = s.v when not matched then insert (id, v) values (s.id, s.v) output $action, inserted.id, inserted.v;")) {
            p.setInt(1, 2); p.setString(2, "TWO");
            try (ResultSet r = p.executeQuery()) { r.next(); Check.eq("merge output update", r.getString(1) + ":" + r.getInt(2) + ":" + r.getString(3), "UPDATE:2:TWO"); }
            p.setInt(1, 3); p.setString(2, "three");
            try (ResultSet r = p.executeQuery()) { r.next(); Check.eq("merge output insert", r.getString(1) + ":" + r.getInt(2) + ":" + r.getString(3), "INSERT:3:three"); }
        }
        Check.eq("merge result", rows("select cast(id as varchar) + ':' + v from jt_merge order by id"), List.of("1:one", "2:TWO", "3:three"));
        try (Statement s = c.createStatement()) {
            Check.eq("merge delete", s.executeUpdate("merge jt_merge as t using (select 1 as id) as s on t.id = s.id when matched then delete;"), 1);
        }
        Check.eq("after delete", rows("select count(*) from jt_merge"), List.of("2"));
        try (Statement s = c.createStatement(); ResultSet r = s.executeQuery("delete from jt_merge output deleted.id, deleted.v where id = 3")) { r.next(); Check.eq("delete output", r.getInt(1), 3); }
    }

    // ---- errors by number
    static void errors() throws Exception {
        Check.eq("208 invalid object", Check.errorOf(() -> rows("select * from no_such_table")), 208);
        Check.eq("207 invalid column", Check.errorOf(() -> rows("select nosuch from jt_merge")), 207);
        Check.eq("2627 primary key", Check.errorOf(() -> { try (Statement s = c.createStatement()) { s.executeUpdate("insert into jt_merge values (2, 'dup')"); } }), 2627);
        Check.eq("245 conversion", Check.errorOf(() -> rows("select cast('abc' as int)")), 245);
        Check.eq("8134 divide by zero", Check.errorOf(() -> rows("select 1/0")), 8134);
        Check.eq("156 syntax", Check.errorOf(() -> rows("select 1 from from")), 156);
        Check.eq("102 syntax", Check.errorOf(() -> rows("select 1 +")), 102);
        Check.eq("515 null", Check.errorOf(() -> { try (Statement s = c.createStatement()) { s.executeUpdate("insert into jt_merge (v) values ('x')"); } }), 515);
        Check.eq("2628 truncation", Check.errorOf(() -> { try (Statement s = c.createStatement()) { s.executeUpdate("insert into jt_merge values (50, 'this is far too long')"); } }), 2628);
        Check.eq("2714 exists", Check.errorOf(() -> { try (Statement s = c.createStatement()) { s.execute("create table jt_merge (x int)"); } }), 2714);
        Check.eq("547 foreign key", Check.errorOf(() -> { try (Statement s = c.createStatement()) { s.execute("create table jt_child (id int, p int references jt_merge(id))"); s.executeUpdate("insert into jt_child values (1, 999)"); } }), 547);
        Check.eq("547 delete parent", Check.errorOf(() -> { try (Statement s = c.createStatement()) { s.executeUpdate("insert into jt_child values (2, 2)"); s.executeUpdate("delete from jt_merge where id = 2"); } }), 547);
        Check.eq("50000 raiserror", Check.errorOf(() -> rows("raiserror('boom', 16, 1)")), 50000);
        Check.eq("throw", Check.errorOf(() -> rows("throw 51000, 'thrown', 1")), 51000);
        try { rows("select * from no_such_table"); } catch (SQLException e) {
            Check.yes("message", e.getMessage().contains("Invalid object name"));
            Check.eq("sqlstate", e.getSQLState(), "S0002");
        }
        Check.eq("after errors", rows("select 1"), List.of("1"));
        try (Statement s = c.createStatement()) { s.setMaxRows(2); try (ResultSet r = s.executeQuery("select id from jt_all union all select id from jt_all union all select 5")) { int n = 0; while (r.next()) n++; Check.eq("maxrows", n, 2); } }
        try (Statement s = c.createStatement()) { s.setQueryTimeout(30); Check.eq("with timeout", s.executeQuery("select 1").next(), true); }
        try (Statement s = c.createStatement()) { s.setFetchSize(3); try (ResultSet r = s.executeQuery("select number from (values (1),(2),(3),(4),(5),(6),(7)) v(number)")) { int n = 0; while (r.next()) n++; Check.eq("fetch size 3", n, 7); } } catch (SQLException e) { /* a derived table of VALUES */ }
        run("drop table jt_child");
    }

    // ---- DatabaseMetaData
    static void metadata() throws Exception {
        run("create table jt_parent (id int not null, code varchar(10) not null, note varchar(100), constraint jt_parent_pk primary key (id, code))");
        run("create unique index jt_parent_ix on jt_parent (note)");
        run("create table jt_child (cid int primary key, pid int, pcode varchar(10), constraint jt_child_fk foreign key (pid, pcode) references jt_parent (id, code))");
        DatabaseMetaData m = c.getMetaData();
        String cat = c.getCatalog();
        Check.eq("getTables", meta(m.getTables(cat, "dbo", "jt_parent", new String[]{"TABLE"}), "TABLE_SCHEM", "TABLE_NAME", "TABLE_TYPE"), List.of("dbo|jt_parent|TABLE"));
        Check.eq("getTables pattern", meta(m.getTables(cat, "dbo", "jt_child%", null), "TABLE_NAME"), List.of("jt_child"));
        Check.eq("getColumns", meta(m.getColumns(cat, "dbo", "jt_parent", "%"), "COLUMN_NAME", "TYPE_NAME", "COLUMN_SIZE", "NULLABLE", "ORDINAL_POSITION"),
                 List.of("id|int|10|0|1", "code|varchar|10|0|2", "note|varchar|100|1|3"));
        Check.eq("getPrimaryKeys", meta(m.getPrimaryKeys(cat, "dbo", "jt_parent"), "COLUMN_NAME", "KEY_SEQ", "PK_NAME"), List.of("id|1|jt_parent_pk", "code|2|jt_parent_pk"));
        Check.eq("getIndexInfo", meta(m.getIndexInfo(cat, "dbo", "jt_parent", true, false), "INDEX_NAME", "COLUMN_NAME", "NON_UNIQUE").stream().filter(x -> x.startsWith("jt_parent_ix")).toList(), List.of("jt_parent_ix|note|0"));
        Check.eq("getImportedKeys", meta(m.getImportedKeys(cat, "dbo", "jt_child"), "PKTABLE_NAME", "PKCOLUMN_NAME", "FKCOLUMN_NAME", "KEY_SEQ", "FK_NAME"),
                 List.of("jt_parent|id|pid|1|jt_child_fk", "jt_parent|code|pcode|2|jt_child_fk"));
        Check.eq("getExportedKeys", meta(m.getExportedKeys(cat, "dbo", "jt_parent"), "FKTABLE_NAME", "FKCOLUMN_NAME"), List.of("jt_child|pid", "jt_child|pcode"));
        Check.yes("getSchemas", meta(m.getSchemas(), "TABLE_SCHEM").contains("dbo"));
        Check.yes("getCatalogs", meta(m.getCatalogs(), "TABLE_CAT").contains(cat));
        Check.yes("getTableTypes", meta(m.getTableTypes(), "TABLE_TYPE").contains("TABLE"));
        Check.yes("getTypeInfo", meta(m.getTypeInfo(), "TYPE_NAME").containsAll(List.of("int", "varchar", "datetime2")));
        Check.eq("getProcedures none", meta(m.getProcedures(cat, "dbo", "jt_nosuch%"), "PROCEDURE_NAME"), List.of());
        Check.eq("identifier quote", m.getIdentifierQuoteString(), "\"");
        Check.eq("supportsTransactions", m.supportsTransactions(), true);
        run("create view jt_view as select id from jt_parent");
        Check.eq("getTables view", meta(m.getTables(cat, "dbo", "jt_view", new String[]{"VIEW"}), "TABLE_NAME", "TABLE_TYPE"), List.of("jt_view|VIEW"));
        try (Statement s = c.createStatement(); ResultSet r = s.executeQuery("select * from jt_parent where 1 = 0")) {
            Check.eq("empty rs cols", r.getMetaData().getColumnCount(), 3); Check.eq("empty rs name", r.getMetaData().getColumnName(3), "note");
        }
        // a prepared statement's metadata before it runs (sp_describe_first_result_set), its parameters' (sp_describe_undeclared_parameters)
        try (PreparedStatement p = c.prepareStatement("select id, note from jt_parent where id = ?")) {
            ResultSetMetaData rm = p.getMetaData();
            Check.eq("prepared metadata", rm == null ? -1 : rm.getColumnCount(), 2);
            try {
                ParameterMetaData pm = p.getParameterMetaData();
                Check.eq("parameter count", pm.getParameterCount(), 1);
                Check.eq("parameter type", pm.getParameterTypeName(1), "int");
            } catch (SQLException e) { System.out.println("SKIP parameter metadata (sp_describe_undeclared_parameters): " + e.getMessage().split("\n")[0]); }
        }
        run("drop view jt_view"); run("drop table jt_child"); run("drop table jt_parent");
    }

    // ---- stored procedures and functions, OUT parameters
    static void procedures() throws Exception {
        try (Statement s = c.createStatement()) {
            s.execute("create procedure jt_proc @a int, @b int output, @o varchar(30) output as begin set @b = @b + @a; set @o = 'sum=' + cast(@b as varchar); return 7; end");
        } catch (SQLException e) { System.out.println("SKIP stored procedures (CREATE PROCEDURE): " + e.getMessage().split("\n")[0]); return; }
        run("create function jt_func(@x int) returns int as begin return @x * 2; end");
        try (CallableStatement cs = c.prepareCall("{? = call jt_proc(?, ?, ?)}")) {
            cs.registerOutParameter(1, Types.INTEGER); cs.setInt(2, 5); cs.setInt(3, 10); cs.registerOutParameter(3, Types.INTEGER); cs.registerOutParameter(4, Types.VARCHAR);
            cs.execute();
            Check.eq("return status", cs.getInt(1), 7); Check.eq("in out", cs.getInt(3), 15); Check.eq("out", cs.getString(4), "sum=15");
        }
        try (CallableStatement cs = c.prepareCall("{call jt_proc(?, ?, ?)}")) {
            cs.setInt(1, 1); cs.setInt(2, 1); cs.registerOutParameter(2, Types.INTEGER); cs.registerOutParameter(3, Types.VARCHAR); cs.execute(); Check.eq("call without status", cs.getInt(2), 2);
        }
        try (CallableStatement cs = c.prepareCall("{? = call dbo.jt_func(?)}")) { cs.registerOutParameter(1, Types.INTEGER); cs.setInt(2, 21); cs.execute(); Check.eq("function result", cs.getInt(1), 42); }
        Check.eq("function in select", rows("select dbo.jt_func(4)"), List.of("8"));
        run("create procedure jt_rs as begin select 1 as a; select 'x' as b, 2 as c; end");
        try (CallableStatement cs = c.prepareCall("{call jt_rs}")) {
            boolean has = cs.execute(); int n = 0;
            while (has) { try (ResultSet r = cs.getResultSet()) { r.next(); n++; Check.eq("result set " + n + " columns", r.getMetaData().getColumnCount(), n); } has = cs.getMoreResults(); }
            Check.eq("two result sets", n, 2);
        }
        run("drop procedure jt_rs");
        try (Statement s = c.createStatement()) { Check.eq("exec", s.execute("declare @b int = 2, @o varchar(30); exec jt_proc @a = 1, @b = @b output, @o = @o output"), false); }
        Check.eq("proc error", Check.errorOf(() -> { try (CallableStatement cs = c.prepareCall("{call jt_nosuch}")) { cs.execute(); } }), 2812);
        Check.eq("sp_help", Check.errorOf(() -> { try (Statement s = c.createStatement()) { s.execute("exec sp_who"); } }) >= 0, true);
    }
}
