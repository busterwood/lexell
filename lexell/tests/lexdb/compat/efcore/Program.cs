using System;
using System.Collections.Generic;
using System.Linq;
using Microsoft.EntityFrameworkCore;
using Oracle.ManagedDataAccess.Client;

public class Org
{
    public int Id { get; set; }
    public string Name { get; set; } = "";
    public List<User> Users { get; set; } = new();
}

public class User
{
    public int Id { get; set; }
    public int OrgId { get; set; }
    public string Email { get; set; } = "";
    public int Age { get; set; }
    public decimal Balance { get; set; }
    public bool Active { get; set; }
    public Org Org { get; set; } = null!;
}

public class AppDbContext : DbContext
{
    private readonly string _prefix;
    private readonly Action<DbContextOptionsBuilder> _configure;
    public AppDbContext(string prefix, Action<DbContextOptionsBuilder> configure)
    {
        _prefix = prefix;
        _configure = configure;
    }
    public DbSet<Org> Orgs => Set<Org>();
    public DbSet<User> Users => Set<User>();
    protected override void OnConfiguring(DbContextOptionsBuilder b) => _configure(b);
    protected override void OnModelCreating(ModelBuilder m)
    {
        m.Entity<Org>(e =>
        {
            e.ToTable($"ef_{_prefix}_orgs");
            e.HasIndex(x => x.Name).IsUnique();
        });
        m.Entity<User>(e =>
        {
            e.ToTable($"ef_{_prefix}_users");
            e.Property(x => x.Balance).HasPrecision(12, 2);
            e.HasOne(x => x.Org).WithMany(x => x.Users).HasForeignKey(x => x.OrgId).OnDelete(DeleteBehavior.Cascade);
        });
    }
}

class Program
{
    static int fails = 0, passes = 0;

    static void Run(string door, string name, Action fn)
    {
        try
        {
            fn();
            passes++;
            Console.WriteLine($"  [PASS] {door} :: {name}");
        }
        catch (Exception ex)
        {
            fails++;
            var cur = ex;
            var parts = new List<string>();
            while (cur != null) { parts.Add($"{cur.GetType().Name}: {cur.Message}"); cur = cur.InnerException; }
            var msg = string.Join(" => ", parts).Replace("\n", " | ");
            if (msg.Length > 450) msg = msg[..450] + "...";
            Console.WriteLine($"  [FAIL] {door} :: {name} -> {msg}");
        }
    }

    static void TestEfDoor(string door, Action<DbContextOptionsBuilder> cfg)
    {
        Console.WriteLine($"=== .NET Entity Framework Core ({door}) ===");
        Run($"EF-{door}", "EnsureCreated + SaveChanges (parent+children)", () =>
        {
            using var db = new AppDbContext(door.ToLower(), cfg);
            db.Database.EnsureCreated();
            var org = new Org
            {
                Name = $"Acme-{door}",
                Users =
                {
                    new User { Email = "a@acme.com", Age = 30, Balance = 100.50m, Active = true },
                    new User { Email = "b@acme.com", Age = 25, Balance = 50.25m, Active = false }
                }
            };
            db.Orgs.Add(org);
            db.SaveChanges();
            if (org.Id <= 0) throw new Exception($"bad org.Id={org.Id}");
        });

        Run($"EF-{door}", "LINQ Include + OrderBy + Skip/Take + Sum", () =>
        {
            using var db = new AppDbContext(door.ToLower(), cfg);
            var orgs = db.Orgs.Include(o => o.Users).ToList();
            if (orgs.Count != 1 || orgs[0].Users.Count != 2) throw new Exception($"bad counts {orgs.Count}");
            var page = db.Users.OrderByDescending(u => u.Age).Skip(1).Take(1).ToList();
            if (page.Count != 1 || page[0].Email != "b@acme.com") throw new Exception("bad page");
            var sum = db.Users.Sum(u => u.Balance);
            if (sum != 150.75m) throw new Exception($"bad sum {sum}");
        });

        Run($"EF-{door}", "ExecuteUpdate + ExecuteDelete + Transaction rollback", () =>
        {
            using var db = new AppDbContext(door.ToLower(), cfg);
            using var tx = db.Database.BeginTransaction();
            db.Users.Where(u => u.Age < 28).ExecuteUpdate(s => s.SetProperty(u => u.Age, 99));
            var u = db.Users.AsNoTracking().Single(x => x.Email == "b@acme.com");
            if (u.Age != 99) throw new Exception($"expected 99, got {u.Age}");
            tx.Rollback();
            var u2 = db.Users.AsNoTracking().Single(x => x.Email == "b@acme.com");
            if (u2.Age != 25) throw new Exception($"rollback failed, got {u2.Age}");
            var del = db.Users.Where(x => x.Email == "b@acme.com").ExecuteDelete();
            if (del != 1) throw new Exception($"expected 1 deleted, got {del}");
        });
    }

    static void TestOdpNet(string oraPort)
    {
        Console.WriteLine("=== .NET Oracle.ManagedDataAccess.Core (ORA Thin) ===");
        var cs = $"User Id=sa;Password=sa;Data Source=127.0.0.1:{oraPort}/lexdb;Pooling=false;Connection Timeout=5";

        Run("ODP.NET", "connect + DDL + parameterized INSERT/SELECT + rollback", () =>
        {
            using var conn = new OracleConnection(cs);
            conn.Open();
            if (!conn.ServerVersion.StartsWith("23.")) throw new Exception($"unexpected version {conn.ServerVersion}");

            using (var cmd = conn.CreateCommand())
            {
                cmd.CommandText = "CREATE TABLE odp_items (id NUMBER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY, name VARCHAR2(100), price NUMBER(10,2))";
                cmd.ExecuteNonQuery();
            }
            using (var tx = conn.BeginTransaction())
            {
                using (var ins = conn.CreateCommand())
                {
                    ins.Transaction = tx;
                    ins.CommandText = "INSERT INTO odp_items (name, price) VALUES (:1, :2)";
                    ins.Parameters.Add(new OracleParameter("p1", "apple"));
                    ins.Parameters.Add(new OracleParameter("p2", 1.25m));
                    ins.ExecuteNonQuery();
                }
                tx.Commit();
            }
            using (var tx = conn.BeginTransaction())
            {
                using (var ins = conn.CreateCommand())
                {
                    ins.Transaction = tx;
                    ins.CommandText = "INSERT INTO odp_items (name, price) VALUES ('rolled_back', 9.99)";
                    ins.ExecuteNonQuery();
                }
                tx.Rollback();
            }
            using (var q = conn.CreateCommand())
            {
                q.CommandText = "SELECT COUNT(*), SUM(price) FROM odp_items";
                using var r = q.ExecuteReader();
                if (!r.Read()) throw new Exception("no rows");
                if (r.GetInt32(0) != 1 || r.GetDecimal(1) != 1.25m)
                    throw new Exception($"bad aggregate: {r.GetInt32(0)}, {r.GetDecimal(1)}");
            }
        });
    }

    static int Main()
    {
        var pgPort = Environment.GetEnvironmentVariable("PG_PORT") ?? "15433";
        var tdsPort = Environment.GetEnvironmentVariable("TDS_PORT") ?? "11433";
        var oraPort = Environment.GetEnvironmentVariable("ORA_PORT") ?? "11521";
        var doors = (Environment.GetEnvironmentVariable("DOORS") ?? "PG,TDS,ORA").Split(',');

        if (doors.Contains("PG"))
            TestEfDoor("PG", b => b.UseNpgsql($"Host=127.0.0.1;Port={pgPort};Username=postgres;Database=lexdb"));
        if (doors.Contains("TDS"))
            TestEfDoor("TDS", b => b.UseSqlServer($"Server=127.0.0.1,{tdsPort};Database=lexdb;User Id=sa;Password=x;Encrypt=False"));
        if (doors.Contains("ORA"))
            TestOdpNet(oraPort);

        Console.WriteLine($".NET Summary: {passes}/{passes + fails} passed, {fails} failed");
        return fails > 0 ? 1 : 0;
    }
}
