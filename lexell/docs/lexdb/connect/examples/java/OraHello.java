import java.math.BigDecimal;
import java.sql.*;

/** lexdb through its Oracle door (TNS), with Oracle's JDBC thin driver (ojdbc11).
 *  It makes a table, inserts rows with a batch of prepared statements (array DML), reads
 *  them back, calls a PL/SQL block, and shows a transaction rolled back by an error.
 *
 *  javac -d out OraHello.java
 *  java -cp out:ojdbc11-23.26.4.0.0.jar OraHello jdbc:oracle:thin:@//127.0.0.1:1521/lexdb sa SA */
public class OraHello {
    public static void main(String[] a) throws SQLException {
        String url = a.length > 0 ? a[0] : "jdbc:oracle:thin:@//127.0.0.1:1521/lexdb";
        String user = a.length > 1 ? a[1] : "sa";
        String password = a.length > 2 ? a[2] : "SA";
        try (Connection c = DriverManager.getConnection(url, user, password)) {
            DatabaseMetaData m = c.getMetaData();
            System.out.println("server: " + m.getDatabaseProductVersion().lines().findFirst().orElse(""));
            try (Statement s = c.createStatement()) {
                s.execute("DROP TABLE IF EXISTS jora_fruit");
                s.execute("CREATE TABLE jora_fruit (id NUMBER(9) PRIMARY KEY, name VARCHAR2(40) NOT NULL, price NUMBER(10,2) CHECK (price > 0))");
            }
            // a batch of one prepared INSERT, sent as one array DML call: ? are the binds
            try (PreparedStatement p = c.prepareStatement("INSERT INTO jora_fruit VALUES (?, ?, ?)")) {
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
            // a PL/SQL block with an OUT bind
            try (CallableStatement k = c.prepareCall("BEGIN SELECT count(*) INTO ? FROM jora_fruit; END;")) {
                k.registerOutParameter(1, Types.INTEGER);
                k.execute();
                System.out.println("rows: " + k.getInt(1));
            }
            // a transaction: the second INSERT breaks the CHECK, so neither row stays
            c.setAutoCommit(false);
            try (Statement s = c.createStatement()) {
                s.executeUpdate("INSERT INTO jora_fruit VALUES (4, 'fig', 3.10)");
                s.executeUpdate("INSERT INTO jora_fruit VALUES (5, 'kiwi', -1)");
                c.commit();
            } catch (SQLException e) {
                c.rollback();
                System.out.println("transaction: rolled back, ORA-" + String.format("%05d", e.getErrorCode()));
            }
            c.setAutoCommit(true);
            try (PreparedStatement q = c.prepareStatement("SELECT id, name, price FROM jora_fruit WHERE price < ? ORDER BY id")) {
                q.setBigDecimal(1, new BigDecimal("5.00"));
                try (ResultSet r = q.executeQuery()) {
                    while (r.next()) System.out.println(r.getInt(1) + " " + r.getString(2) + " " + r.getBigDecimal(3));
                }
            }
        }
    }
}
