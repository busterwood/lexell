# Example programs

Small, complete programs that connect to lexdb through each door. Each makes its own table (dropping it first), so
it can be run again.

| Program | Door | Client | What it shows |
|---|---|---|---|
| [java/PgHello.java](java/PgHello.java) | PostgreSQL | pgjdbc 42.7.14 | batch insert, a transaction rolled back, a parameterised query |
| [java/PgCopy.java](java/PgCopy.java) | PostgreSQL | pgjdbc 42.7.14 | `COPY FROM STDIN` from a file and from the program, `COPY TO STDOUT` |
| [java/TdsHello.java](java/TdsHello.java) | SQL Server | mssql-jdbc 13.6.2 | batch insert, a transaction rolled back, a parameterised query |
| [java/TdsBulk.java](java/TdsBulk.java) | SQL Server | mssql-jdbc 13.6.2 | `SQLServerBulkCopy` from a CSV file, a batch sent as bulk copy |
| [java/OraHello.java](java/OraHello.java) | Oracle | ojdbc11 23.26.4 | array DML, a PL/SQL block with an OUT bind, a transaction rolled back |
| [lexell/pg_hello.lxl](lexell/pg_hello.lxl) | PostgreSQL | lib/postgres | parameters, a transaction rolled back |
| [lexell/tds_hello.lxl](lexell/tds_hello.lxl) | SQL Server | lib/sqlserver | parameters, bulk copy, a transaction rolled back |
| [lexell/tns_hello.lxl](lexell/tns_hello.lxl) | Oracle | lib/oracle | binds, a PL/SQL block, a transaction rolled back |

[java/cities.csv](java/cities.csv) is the input of PgCopy and TdsBulk.

## Java

Java 17 or later. The drivers are on Maven Central:

```sh
curl -LO https://repo1.maven.org/maven2/org/postgresql/postgresql/42.7.14/postgresql-42.7.14.jar
curl -LO https://repo1.maven.org/maven2/com/microsoft/sqlserver/mssql-jdbc/13.6.2.jre11/mssql-jdbc-13.6.2.jre11.jar
curl -LO https://repo1.maven.org/maven2/com/oracle/database/jdbc/ojdbc11/23.26.4.0.0/ojdbc11-23.26.4.0.0.jar
```

Compile in a scratch directory, with the drivers on the class path for the programs that use their classes:

```sh
JARS=postgresql-42.7.14.jar:mssql-jdbc-13.6.2.jre11.jar:ojdbc11-23.26.4.0.0.jar
javac -cp $JARS -d out lexell/docs/lexdb/connect/examples/java/*.java
java -cp out:$JARS PgHello 'jdbc:postgresql://127.0.0.1:5433/lexdb' postgres x
java -cp out:$JARS TdsHello 'jdbc:sqlserver://127.0.0.1:1433;databaseName=lexdb;encrypt=false;user=sa;password=x'
java -cp out:$JARS OraHello jdbc:oracle:thin:@//127.0.0.1:1521/lexdb sa SA
```

`PgCopy` and `TdsBulk` take the CSV file's path after the connection arguments.

## Lexell

```sh
lexell/compiler/out/lxlc lexell/docs/lexdb/connect/examples/lexell/pg_hello.lxl -o pg_hello
./pg_hello "host=127.0.0.1 port=5433 user=postgres dbname=lexdb"
lexell/compiler/out/lxlc lexell/docs/lexdb/connect/examples/lexell/tds_hello.lxl -o tds_hello
./tds_hello "Server=127.0.0.1,1433;Database=lexdb;UID=sa;PWD=x;Encrypt=no"
lexell/compiler/out/lxlc lexell/docs/lexdb/connect/examples/lexell/tns_hello.lxl -o tns_hello
./tns_hello "User Id=sa;Password=sa;Data Source=127.0.0.1:1521/lexdb"
```

lxlc finds `postgres`, `sqlserver` and `oracle` in the library beside the compiler (`lexell/lib`); `LXL_LIB` points
it at another.

The output of each program is in its door's connect page.
