import java.sql.*;
import com.microsoft.sqlserver.jdbc.SQLServerBulkCopy;
import com.microsoft.sqlserver.jdbc.SQLServerBulkCopyOptions;
import com.microsoft.sqlserver.jdbc.SQLServerBulkCSVFileRecord;

/** Bulk copy into lexdb's SQL Server door with mssql-jdbc: SQLServerBulkCopy from a CSV file, and
 *  executeBatch sent as bulk copy (useBulkCopyForBatchInsert=true).
 *
 *  javac -cp mssql-jdbc-13.6.2.jre11.jar -d out TdsBulk.java
 *  java -cp out:mssql-jdbc-13.6.2.jre11.jar TdsBulk "jdbc:sqlserver://127.0.0.1:1433;databaseName=lexdb;encrypt=false;user=sa;password=x" rows.csv */
public class TdsBulk {
    public static void main(String[] a) throws Exception {
        java.util.logging.LogManager.getLogManager().reset();
        String url = a[0];
        try (Connection c = DriverManager.getConnection(url); Statement s = c.createStatement()) {
            s.execute("DROP TABLE IF EXISTS bulk_city");
            s.execute("CREATE TABLE bulk_city (id int PRIMARY KEY, name nvarchar(60) NOT NULL, pop bigint, founded date)");

            // 1. a CSV file through SQLServerBulkCopy (INSERT BULK and a BULK_LOAD message, as bcp sends)
            SQLServerBulkCSVFileRecord csv = new SQLServerBulkCSVFileRecord(a[1], "UTF-8", ",", true);
            csv.addColumnMetadata(1, "id", Types.INTEGER, 0, 0);
            csv.addColumnMetadata(2, "name", Types.NVARCHAR, 60, 0);
            csv.addColumnMetadata(3, "pop", Types.BIGINT, 0, 0);
            csv.addColumnMetadata(4, "founded", Types.DATE, 0, 0);
            try (SQLServerBulkCopy bulk = new SQLServerBulkCopy(c)) {
                SQLServerBulkCopyOptions o = new SQLServerBulkCopyOptions();
                o.setCheckConstraints(true);
                o.setBatchSize(1000);
                bulk.setBulkCopyOptions(o);
                bulk.setDestinationTableName("dbo.bulk_city");
                bulk.writeToServer(csv);
            }
        }
        // a new connection: on the one that ran SQLServerBulkCopy, SET FMTONLY ON stays in effect and later
        // queries give no rows (docs/lexdb/KNOWN-ISSUES.md); SET FMTONLY OFF there would do as well
        try (Connection c = DriverManager.getConnection(url); Statement s = c.createStatement();
             ResultSet r = s.executeQuery("SELECT count(*), sum(pop) FROM bulk_city")) {
            r.next();
            System.out.println("from the file: " + r.getInt(1) + " rows, population " + r.getLong(2));
        }
        // 2. a JDBC batch sent as bulk copy
        try (Connection c = DriverManager.getConnection(url + ";useBulkCopyForBatchInsert=true");
             PreparedStatement p = c.prepareStatement("INSERT INTO bulk_city (id, name, pop, founded) VALUES (?, ?, ?, ?)")) {
            for (int i = 0; i < 5000; i++) {
                p.setInt(1, 1000 + i);
                p.setString(2, "town " + i);
                p.setLong(3, 100 + i);
                p.setDate(4, Date.valueOf("2000-01-01"));
                p.addBatch();
            }
            int[] n = p.executeBatch();
            System.out.println("batch: " + n.length + " rows sent");
        }
        try (Connection c = DriverManager.getConnection(url); Statement s = c.createStatement();
             ResultSet r = s.executeQuery("SELECT count(*) FROM bulk_city")) {
            r.next();
            System.out.println("after the batch: " + r.getInt(1) + " rows");
        }
    }
}
