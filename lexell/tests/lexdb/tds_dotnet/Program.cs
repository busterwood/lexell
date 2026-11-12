using System;
using System.Data;
using Microsoft.Data.SqlClient;

var cs = args[0];
void Step(string name, Action a) {
    try { a(); } catch (Exception e) { Console.WriteLine($"{name}: FAILED {e.GetType().Name}: {e.Message}"); }
}
using (var c = new SqlConnection(cs)) {
    c.Open();
    Console.WriteLine($"open: version {c.ServerVersion} database {c.Database}");
    Step("create", () => new SqlCommand("CREATE TABLE people (id int primary key, name nvarchar(50), born date, balance decimal(10,2), seen datetime2, ok bit)", c).ExecuteNonQuery());
    Step("insert with parameters", () => {
        for (int i = 1; i <= 3; i++) {
            var cmd = new SqlCommand("INSERT INTO people VALUES (@id, @name, @born, @bal, @seen, @ok)", c);
            cmd.Parameters.AddWithValue("@id", i);
            cmd.Parameters.AddWithValue("@name", i == 2 ? (object)DBNull.Value : $"pérson {i}");
            cmd.Parameters.AddWithValue("@born", new DateTime(1990 + i, 1, 2));
            cmd.Parameters.AddWithValue("@bal", 10.25m * i);
            cmd.Parameters.AddWithValue("@seen", new DateTime(2026, 11, 11, 10, 0, i));
            cmd.Parameters.AddWithValue("@ok", i != 3);
            Console.WriteLine($"insert {i}: {cmd.ExecuteNonQuery()}");
        }
    });
    Step("reader", () => {
        using var r = new SqlCommand("SELECT id, name, born, balance, seen, ok FROM people ORDER BY id", c).ExecuteReader();
        while (r.Read())
            Console.WriteLine($"row: {r.GetInt32(0)} {(r.IsDBNull(1) ? "NULL" : r.GetString(1))} {r.GetDateTime(2):yyyy-MM-dd} {r.GetDecimal(3)} {r.GetDateTime(4):yyyy-MM-dd HH:mm:ss} {r.GetBoolean(5)}");
    });
    Step("prepared", () => {
        var p = new SqlCommand("SELECT balance FROM people WHERE id = @id", c);
        p.Parameters.Add("@id", SqlDbType.Int);
        p.Prepare();
        for (int i = 1; i <= 3; i++) { p.Parameters["@id"].Value = i; Console.WriteLine($"prepared {i}: {p.ExecuteScalar()}"); }
    });
    Step("output parameter", () => {
        var o = new SqlCommand("SET @out = @in * 2", c);
        o.Parameters.AddWithValue("@in", 21);
        var op = o.Parameters.Add("@out", SqlDbType.Int); op.Direction = ParameterDirection.Output;
        o.ExecuteNonQuery();
        Console.WriteLine($"output: {op.Value}");
    });
    Step("rollback", () => {
        using (var tx = c.BeginTransaction()) {
            new SqlCommand("INSERT INTO people (id, name) VALUES (10, N'gone')", c, tx).ExecuteNonQuery();
            Console.WriteLine($"in transaction: {new SqlCommand("SELECT @@TRANCOUNT", c, tx).ExecuteScalar()}");
            tx.Rollback();
        }
        Console.WriteLine($"after rollback: {new SqlCommand("SELECT count(*) FROM people WHERE id = 10", c).ExecuteScalar()}");
    });
    Step("commit", () => {
        using (var tx = c.BeginTransaction(IsolationLevel.ReadCommitted)) {
            new SqlCommand("INSERT INTO people (id, name) VALUES (11, N'kept')", c, tx).ExecuteNonQuery();
            tx.Commit();
        }
        Console.WriteLine($"after commit: {new SqlCommand("SELECT count(*) FROM people WHERE id = 11", c).ExecuteScalar()}");
    });
    Step("error", () => {
        try { new SqlCommand("INSERT INTO people (id) VALUES (1)", c).ExecuteNonQuery(); }
        catch (SqlException e) { Console.WriteLine($"error: {e.Number} class {e.Class}"); }
    });
    Step("nocount on", () => new SqlCommand("SET NOCOUNT ON", c).ExecuteNonQuery());
}
Step("pooled again", () => {
    using var c = new SqlConnection(cs);
    c.Open();
    var n = new SqlCommand("UPDATE people SET ok = ok WHERE id = 1", c).ExecuteNonQuery();
    Console.WriteLine($"pooled: rows {n} (reset: NOCOUNT off), trancount {new SqlCommand("SELECT @@TRANCOUNT", c).ExecuteScalar()}");
});
