import java.math.BigDecimal;
import java.sql.*;

/** lexdb through its PostgreSQL door, with the PostgreSQL JDBC driver (pgjdbc).
 *  It makes a table, inserts rows with a batch of prepared statements, reads them back,
 *  and shows a transaction rolled back by an error.
 *
 *  javac -d out PgHello.java
 *  java -cp out:postgresql-42.7.14.jar PgHello jdbc:postgresql://127.0.0.1:5433/lexdb postgres x */
public class PgHello {
    public static void main(String[] a) throws SQLException {
        String url = a.length > 0 ? a[0] : "jdbc:postgresql://127.0.0.1:5433/lexdb";
        String user = a.length > 1 ? a[1] : "postgres";
        String password = a.length > 2 ? a[2] : "x";
        try (Connection c = DriverManager.getConnection(url, user, password)) {
            DatabaseMetaData m = c.getMetaData();
            System.out.println("server: " + m.getDatabaseProductName() + " " + m.getDatabaseProductVersion());
            try (Statement s = c.createStatement()) {
                s.execute("DROP TABLE IF EXISTS jpg_fruit");
                s.execute("CREATE TABLE jpg_fruit (id int PRIMARY KEY, name text NOT NULL, price numeric(10,2) CHECK (price > 0))");
            }
            // a batch of one prepared INSERT: ? are the parameters
            try (PreparedStatement p = c.prepareStatement("INSERT INTO jpg_fruit VALUES (?, ?, ?)")) {
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
                s.executeUpdate("INSERT INTO jpg_fruit VALUES (4, 'fig', 3.10)");
                s.executeUpdate("INSERT INTO jpg_fruit VALUES (5, 'kiwi', -1)");
                c.commit();
            } catch (SQLException e) {
                c.rollback();
                System.out.println("transaction: rolled back, SQLSTATE " + e.getSQLState());
            }
            c.setAutoCommit(true);
            try (PreparedStatement q = c.prepareStatement("SELECT id, name, price FROM jpg_fruit WHERE price < ? ORDER BY id")) {
                q.setBigDecimal(1, new BigDecimal("5.00"));
                try (ResultSet r = q.executeQuery()) {
                    while (r.next()) System.out.println(r.getInt(1) + " " + r.getString(2) + " " + r.getBigDecimal(3));
                }
            }
        }
    }
}
