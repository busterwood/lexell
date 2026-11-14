import java.math.BigDecimal;
import java.sql.*;
import java.util.*;
import com.microsoft.sqlserver.jdbc.SQLServerDataTable;
import com.microsoft.sqlserver.jdbc.SQLServerPreparedStatement;

/** Table-valued parameters from Microsoft's mssql-jdbc (SQLServerDataTable, setStructured with a table and with a
 *  ResultSet) against lexdb --tds or a real SQL Server (design/lexdb-tds.md, "As built: table-valued parameters"):
 *  every column kind and NULLs, an empty table, a scalar beside one, FROM, JOIN, IN (SELECT ...), INSERT ... SELECT,
 *  many rows, the same statement run until the driver prepares it (sp_executesql, then sp_prepexec, then sp_execute),
 *  a transaction rolled back, and the server's errors (a type that is not there, a conversion, NOT NULL, a key,
 *  writing to the parameter). SQL Server 2022 passes every check; so must lexdb.
 *  usage: MssqlJdbcTvp "jdbc:sqlserver://127.0.0.1:1433;encrypt=false;user=sa;password=x" */
public class MssqlJdbcTvp {
    static Connection c;

    static void run(String sql) { try (Statement s = c.createStatement()) { s.execute(sql); } catch (SQLException e) { /* a drop of nothing */ } }

    static List<String> rows(PreparedStatement p) throws SQLException {
        List<String> out = new ArrayList<>();
        try (ResultSet r = p.executeQuery()) {
            int n = r.getMetaData().getColumnCount();
            while (r.next()) { StringBuilder b = new StringBuilder(); for (int i = 1; i <= n; i++) { if (i > 1) b.append('|'); b.append(r.getString(i)); } out.add(b.toString()); }
        }
        return out;
    }

    static List<String> rows(String sql) throws SQLException {
        try (PreparedStatement p = c.prepareStatement(sql)) { return rows(p); }
    }

    static SQLServerDataTable items() throws SQLException {
        SQLServerDataTable t = itemsMeta();
        t.addRow(1, "one", new BigDecimal("12.50"), java.sql.Date.valueOf("2026-11-14"), true, new byte[] {0, (byte) 0xff}, "n1");
        t.addRow(2, "two", null, null, null, null, null);
        t.addRow(3, "caf\u00e9", new BigDecimal("-0.01"), java.sql.Date.valueOf("2000-01-01"), false, new byte[0], "x".repeat(5000));
        return t;
    }

    static SQLServerDataTable itemsMeta() throws SQLException {
        SQLServerDataTable t = new SQLServerDataTable();
        t.addColumnMetadata("id", Types.INTEGER);
        t.addColumnMetadata("name", Types.NVARCHAR);
        t.addColumnMetadata("amt", Types.DECIMAL);
        t.addColumnMetadata("d", Types.DATE);
        t.addColumnMetadata("flag", Types.BIT);
        t.addColumnMetadata("data", Types.VARBINARY);
        t.addColumnMetadata("note", Types.NVARCHAR);
        return t;
    }

    static SQLServerDataTable ids(int from, int to) throws SQLException {
        SQLServerDataTable t = new SQLServerDataTable();
        t.addColumnMetadata("id", Types.BIGINT);
        for (int i = from; i <= to; i++) t.addRow((long) i);
        return t;
    }

    static PreparedStatement with(String sql, String type, SQLServerDataTable t) throws SQLException {
        PreparedStatement p = c.prepareStatement(sql);
        p.unwrap(SQLServerPreparedStatement.class).setStructured(1, type, t);
        return p;
    }

    static int errorOf(String sql, String type, SQLServerDataTable t) {
        return Check.errorOf(() -> { try (PreparedStatement p = with(sql, type, t)) { p.execute(); } });
    }

    public static void main(String[] a) throws Exception {
        java.util.logging.LogManager.getLogManager().reset();
        c = DriverManager.getConnection(a[0]);
        run("drop table jt_tvp_prod"); run("drop table jt_tvp_target");
        run("drop type dbo.JtItems"); run("drop type dbo.JtIds");
        try (Statement s = c.createStatement()) {
            s.execute("create type dbo.JtItems as table (id int primary key, name nvarchar(30) not null, amt decimal(10,2), d date, flag bit, " +
                      "data varbinary(10), note nvarchar(max))");
            s.execute("create type dbo.JtIds as table (id bigint)");
            s.execute("create table jt_tvp_prod (id int primary key, label varchar(20))");
            s.execute("insert into jt_tvp_prod values (1, 'one'), (2, 'two'), (3, 'three'), (4, 'four')");
            s.execute("create table jt_tvp_target (id int, name nvarchar(30))");
        }
        try (PreparedStatement p = with("select id, name, amt, d, flag, data, len(note) from ? order by id", "dbo.JtItems", items())) {
            Check.eq("rows", rows(p), List.of("1|one|12.50|2026-11-14|1|00FF|2", "2|two|null|null|null|null|null", "3|café|-0.01|2000-01-01|0||5000"));
        }
        try (PreparedStatement p = with("select count(*) from ?", "dbo.JtItems", itemsMeta())) {
            Check.eq("empty", rows(p), List.of("0"));
        }
        try (PreparedStatement p = with("select p.label, i.name from jt_tvp_prod p join ? i on i.id = p.id order by p.id", "dbo.JtItems", items())) {
            Check.eq("join", rows(p), List.of("one|one", "two|two", "three|café"));
        }
        try (PreparedStatement p = with("select label from jt_tvp_prod where id in (select id from ?) order by id", "dbo.JtIds", ids(2, 3))) {
            Check.eq("in", rows(p), List.of("two", "three"));
        }
        try (PreparedStatement p = with("select count(*) from ? where id > ?", "JtIds", ids(1, 10))) {
            p.setInt(2, 4);
            Check.eq("with a scalar", rows(p), List.of("6"));
        }
        try (PreparedStatement p = with("insert into jt_tvp_target select id, name from ?", "dbo.JtItems", items())) {
            Check.eq("insert select", p.executeUpdate(), 3);
        }
        Check.eq("inserted", rows("select count(*), min(name) from jt_tvp_target"), List.of("3|café"));
        try (PreparedStatement p = with("select count(*), sum(id), max(id) from ?", "dbo.JtIds", ids(1, 3000))) {
            Check.eq("many", rows(p), List.of("3000|4501500|3000"));
        }
        // the same statement, run until the driver prepares it (sp_prepexec, then sp_execute)
        try (PreparedStatement p = c.prepareStatement("select count(*), sum(id) from ?")) {
            for (int k = 1; k <= 4; k++) {
                p.unwrap(SQLServerPreparedStatement.class).setStructured(1, "dbo.JtIds", ids(1, k));
                Check.eq("prepared " + k, rows(p), List.of(k + "|" + (k * (k + 1) / 2)));
            }
        }
        // a ResultSet as the table: its columns' metadata from the query
        try (Statement s = c.createStatement(); ResultSet src = s.executeQuery("select id, label from jt_tvp_prod where id <= 2 order by id");
             PreparedStatement p = c.prepareStatement("select max(id), count(*) from ?")) {
            run("drop type dbo.JtPairs");
            try (Statement d = c.createStatement()) { d.execute("create type dbo.JtPairs as table (id int, label varchar(20))"); }
            p.unwrap(SQLServerPreparedStatement.class).setStructured(1, "dbo.JtPairs", src);
            Check.eq("from a result set", rows(p), List.of("2|2"));
        }
        // in a transaction, rolled back
        c.setAutoCommit(false);
        try (PreparedStatement p = with("insert into jt_tvp_target select id, name from ?", "dbo.JtItems", items())) {
            Check.eq("in a transaction", p.executeUpdate(), 3);
        }
        c.rollback();
        c.setAutoCommit(true);
        Check.eq("rolled back", rows("select count(*) from jt_tvp_target"), List.of("3"));
        // the server's errors, the connection usable after each
        Check.eq("no type", errorOf("select count(*) from ?", "dbo.JtNope", ids(1, 2)), 351);
        SQLServerDataTable bad = new SQLServerDataTable();
        bad.addColumnMetadata("id", Types.NVARCHAR);
        bad.addRow("x");
        Check.eq("text into bigint", errorOf("select count(*) from ?", "dbo.JtIds", bad), 8114);
        SQLServerDataTable nul = items();
        nul.addRow(4, null, null, null, null, null, null);
        Check.eq("null into not null", errorOf("select count(*) from ?", "dbo.JtItems", nul), 515);
        SQLServerDataTable dup = items();
        dup.addRow(1, "again", null, null, null, null, null);
        Check.eq("duplicate key", errorOf("select count(*) from ?", "dbo.JtItems", dup), 2627);
        Check.eq("write to it", errorOf("delete from ? where id = 1", "dbo.JtIds", ids(1, 2)), 10700);
        Check.eq("after errors", rows("select 1"), List.of("1"));
        run("drop table jt_tvp_prod"); run("drop table jt_tvp_target");
        run("drop type dbo.JtItems"); run("drop type dbo.JtIds"); run("drop type dbo.JtPairs");
        c.close();
        Check.done();
    }
}
