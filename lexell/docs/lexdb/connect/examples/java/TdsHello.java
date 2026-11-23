import java.math.BigDecimal;
import java.sql.*;

/** lexdb through its SQL Server door (TDS), with Microsoft's JDBC driver (mssql-jdbc).
 *  It makes a table, inserts rows with a batch of prepared statements, reads them back,
 *  and shows a transaction rolled back by an error.
 *
 *  javac -d out TdsHello.java
 *  java -cp out:mssql-jdbc-13.6.2.jre11.jar TdsHello "jdbc:sqlserver://127.0.0.1:1433;databaseName=lexdb;encrypt=false;user=sa;password=x" */
public class TdsHello {
    public static void main(String[] a) throws SQLException {
        java.util.logging.LogManager.getLogManager().reset();     // the driver logs a warning for encrypt=false
        String url = a.length > 0 ? a[0] : "jdbc:sqlserver://127.0.0.1:1433;databaseName=lexdb;encrypt=false;user=sa;password=x";
        try (Connection c = DriverManager.getConnection(url)) {
            DatabaseMetaData m = c.getMetaData();
            System.out.println("server: " + m.getDatabaseProductName() + " " + m.getDatabaseProductVersion());
            try (Statement s = c.createStatement()) {
                s.execute("DROP TABLE IF EXISTS jtds_fruit");
                s.execute("CREATE TABLE jtds_fruit (id int PRIMARY KEY, name nvarchar(40) NOT NULL, price decimal(10,2) CHECK (price > 0))");
            }
            // a batch of one prepared INSERT: ? are the parameters
            try (PreparedStatement p = c.prepareStatement("INSERT INTO jtds_fruit VALUES (?, ?, ?)")) {
                String[] names = {"apple", "pear", "plum"};
                String[] prices = {"1.20", "0.85", "2.40"};
                for (int i = 0; i < names.length; i++) {
                    p.setInt(1, i + 1);
                    p.setString(2, names[i]);
                    p.setBigDecimal(3, new BigDecimal(prices[i]));
                    p.addBatch();
                }
                System.out.println("batch: " + p.executeBatch().length + " rows");
            }
            // a transaction: the second INSERT breaks the CHECK, so neither row stays
            c.setAutoCommit(false);
            try (Statement s = c.createStatement()) {
                s.executeUpdate("INSERT INTO jtds_fruit VALUES (4, N'fig', 3.10)");
                s.executeUpdate("INSERT INTO jtds_fruit VALUES (5, N'kiwi', -1)");
                c.commit();
            } catch (SQLException e) {
                c.rollback();
                System.out.println("transaction: rolled back, error " + e.getErrorCode());
            }
            c.setAutoCommit(true);
            try (PreparedStatement q = c.prepareStatement("SELECT TOP (10) id, name, price FROM jtds_fruit WHERE price < ? ORDER BY id")) {
                q.setBigDecimal(1, new BigDecimal("5.00"));
                try (ResultSet r = q.executeQuery()) {
                    while (r.next()) System.out.println(r.getInt(1) + " " + r.getString(2) + " " + r.getBigDecimal(3));
                }
            }
        }
    }
}
