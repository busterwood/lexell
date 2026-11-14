import java.sql.*;
import java.util.Properties;

/** Oracle's JDBC thin over TLS (TCPS) against lexdb --tcps.
 *  usage: OracleTcps jdbc:oracle:thin:@tcps://127.0.0.1:15235/lexdb USER PASSWORD TRUSTSTORE.jks (password "changeit", type JKS) */
public class OracleTcps {
    public static void main(String[] a) throws Exception {
        java.util.logging.LogManager.getLogManager().reset();
        Properties p = new Properties();
        p.put("user", a[1]); p.put("password", a[2]);
        p.put("javax.net.ssl.trustStore", a[3]); p.put("javax.net.ssl.trustStorePassword", "changeit"); p.put("javax.net.ssl.trustStoreType", "JKS");
        p.put("oracle.net.ssl_server_dn_match", "false");
        try (Connection c = DriverManager.getConnection(a[0], p); Statement s = c.createStatement(); ResultSet r = s.executeQuery("select 1 from dual")) {
            r.next();
            Check.eq("select over TCPS", r.getInt(1), 1);
        }
        Check.done();
    }
}
