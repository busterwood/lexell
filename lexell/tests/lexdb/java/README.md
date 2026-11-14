# JDBC clients against lexdb

Java programs that drive lexdb's Oracle door (`--tns`, `--tcps`) and TDS door (`--tds`) with the vendors' own JDBC
drivers, and, to see what the right answer is, a real Oracle Database Free and SQL Server (the same program, the
same assertions). No jars are kept here; fetch them:

    # Oracle: ojdbc11 (Maven Central, com.oracle.database.jdbc:ojdbc11), SQLcl for the command line
    curl -LO https://repo1.maven.org/maven2/com/oracle/database/jdbc/ojdbc11/23.26.4.0.0/ojdbc11-23.26.4.0.0.jar
    curl -LO https://download.oracle.com/otn_software/java/sqldeveloper/sqlcl-latest.zip     # unzip: sqlcl/bin/sql
    # SQL Server: mssql-jdbc
    curl -LO https://repo1.maven.org/maven2/com/microsoft/sqlserver/mssql-jdbc/13.6.2.jre11/mssql-jdbc-13.6.2.jre11.jar

Compile in a scratch directory (not in a downloaded one) and run with the class path (Java 17 or later):

    OUT=/tmp/jdbc-test; mkdir -p $OUT
    javac -d $OUT -cp ojdbc11.jar tests/lexdb/java/Check.java tests/lexdb/java/OracleJdbc.java tests/lexdb/java/OracleTcps.java
    javac -d $OUT -cp mssql-jdbc.jar tests/lexdb/java/Check.java tests/lexdb/java/MssqlJdbc.java tests/lexdb/java/MssqlJdbcTvp.java

    lexdb DATADIR 127.0.0.1:PG --tns 127.0.0.1:1521 --tds 127.0.0.1:1433 &       # trust login: user sa, password SA (Oracle) or any (TDS)
    java -cp $OUT:ojdbc11.jar OracleJdbc jdbc:oracle:thin:@//127.0.0.1:1521/lexdb sa SA
    java -cp $OUT:mssql-jdbc.jar MssqlJdbc 'jdbc:sqlserver://127.0.0.1:1433;encrypt=false;databaseName=lexdb;user=sa;password=x'
    java -cp $OUT:mssql-jdbc.jar MssqlJdbcTvp 'jdbc:sqlserver://127.0.0.1:1433;encrypt=false;databaseName=lexdb;user=sa;password=x'

Under `--auth trust` an Oracle login with no stored verifier takes the user's name, upper-cased by the driver, as its
password: `sa`/`SA`. A role with a password (`CREATE USER`, `CREATE ROLE ... PASSWORD`) logs in with it.

`OracleJdbc` and `MssqlJdbc` print `FAIL name: got X, want Y` for a difference (and exit 1), `KNOWN ...` for a
difference lexdb is known to have (design/lexdb-oracle.md and lexdb-tds.md, "Java client pass"; not a failure),
and `SKIP ...` for a feature that is missing (generated keys by column name, server cursors, T-SQL stored
procedures). Against a real Oracle (`gvenzl/oracle-free`, `tools/oracle_container.sh`, FREEPDB1, `app`/`app`) and a real
SQL Server 2022 the same programs print `0 failed`, which is what the expectations are. `MssqlJdbcTvp` is the
table-valued parameters (`SQLServerDataTable`, `setStructured` with a table and with a `ResultSet`; lexdb-tds.md,
"As built: table-valued parameters"): it makes and drops its own types and tables, so point it at a scratch database.

TLS: start lexdb with `--tls-cert c.pem --tls-key k.pem --tcps 127.0.0.1:1522`; for the trust store make a JKS with
`keytool -importcert -alias lexdb -file c.pem -keystore ts.jks -storepass changeit`. `MssqlJdbc` takes more URLs after
the first, `ok:URL` (must connect) or `fail:URL` (must be refused), e.g. `ok:...;encrypt=true;trustServerCertificate=true`
and `fail:...;encrypt=strict;...` (TDS 8.0 is refused at once). `OracleTcps` connects over TCPS with that trust store.

SQLcl: `sql -S sa/SA@127.0.0.1:1521/lexdb` (give it a scratch `-Duser.home` through `JAVA_TOOL_OPTIONS`, it writes
there).
