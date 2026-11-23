import java.io.*;
import java.nio.charset.StandardCharsets;
import java.sql.*;
import org.postgresql.PGConnection;
import org.postgresql.copy.CopyManager;

/** COPY into and out of lexdb's PostgreSQL door with pgjdbc's CopyManager.
 *
 *  javac -cp postgresql-42.7.14.jar -d out PgCopy.java
 *  java -cp out:postgresql-42.7.14.jar PgCopy "jdbc:postgresql://127.0.0.1:5433/lexdb" postgres x cities.csv */
public class PgCopy {
    public static void main(String[] a) throws Exception {
        try (Connection c = DriverManager.getConnection(a[0], a[1], a[2]); Statement s = c.createStatement()) {
            s.execute("DROP TABLE IF EXISTS copy_city");
            s.execute("CREATE TABLE copy_city (id int PRIMARY KEY, name text NOT NULL, pop bigint, founded date)");
            CopyManager copy = c.unwrap(PGConnection.class).getCopyAPI();

            // a CSV file in, as it is read
            try (Reader in = new InputStreamReader(new FileInputStream(a[3]), StandardCharsets.UTF_8)) {
                long n = copy.copyIn("COPY copy_city FROM STDIN WITH (FORMAT csv, HEADER true)", in);
                System.out.println("copied in: " + n + " rows");
            }
            // rows made by the program, in COPY's text format (tab between fields, \N for NULL)
            StringBuilder b = new StringBuilder();
            for (int i = 0; i < 10000; i++) b.append(100 + i).append("\ttown ").append(i).append('\t').append(i % 7 == 0 ? "\\N" : String.valueOf(500 + i)).append("\t2000-01-01\n");
            long m = copy.copyIn("COPY copy_city FROM STDIN", new StringReader(b.toString()));
            System.out.println("copied in: " + m + " rows");

            // a query out, as CSV
            StringWriter out = new StringWriter();
            long k = copy.copyOut("COPY (SELECT id, name, pop FROM copy_city WHERE id < 100 ORDER BY id) TO STDOUT WITH (FORMAT csv, HEADER true)", out);
            System.out.print(out);
            System.out.println("copied out: " + k + " rows");
        }
    }
}
