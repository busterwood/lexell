import datetime
import decimal
import os
import sys

TDS_HOST = os.environ.get("TDS_HOST", "127.0.0.1")
TDS_PORT = int(os.environ.get("TDS_PORT", "11433"))
TDS_USER = os.environ.get("TDS_USER", "sa")
TDS_PASS = os.environ.get("TDS_PASS", "x")
TDS_DB = os.environ.get("TDS_DB", "lexdb")

results = []


def run_test(section, name, fn):
    try:
        fn()
        results.append((section, name, "PASS", ""))
        print(f"  [PASS] {section} :: {name}")
    except Exception as e:
        msg = f"{type(e).__name__}: {e}".replace("\n", " | ")
        if len(msg) > 400:
            msg = msg[:400] + "..."
        results.append((section, name, "FAIL", msg))
        print(f"  [FAIL] {section} :: {name} -> {msg}")


# ============================================================
# 1. pymssql direct driver tests
# ============================================================
def test_pymssql():
    import pymssql

    def conn(autocommit=True):
        return pymssql.connect(
            server=TDS_HOST,
            port=TDS_PORT,
            user=TDS_USER,
            password=TDS_PASS,
            database=TDS_DB,
            autocommit=autocommit,
        )

    def t_basic_and_types():
        with conn() as c:
            cur = c.cursor()
            cur.execute("DROP TABLE IF EXISTS dbo.tds_types_t")
            cur.execute("""
                CREATE TABLE dbo.tds_types_t (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    s2 SMALLINT,
                    s8 BIGINT,
                    f8 FLOAT,
                    num DECIMAL(12,2),
                    b BIT,
                    txt NVARCHAR(200),
                    raw VARBINARY(100),
                    d DATE,
                    dt DATETIME2
                )
            """)
            cur.execute(
                "INSERT INTO dbo.tds_types_t (s2, s8, f8, num, b, txt, raw, d, dt) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    7,
                    9000000000,
                    2.5,
                    decimal.Decimal("42.75"),
                    True,
                    "hello",
                    b"\x01\x02",
                    datetime.date(2026, 11, 26),
                    datetime.datetime(2026, 11, 26, 12, 34, 56),
                ),
            )
            cur.execute("SELECT SCOPE_IDENTITY()")
            sid = cur.fetchone()[0]
            assert int(sid) == 1, sid
            cur.execute("SELECT id, s2, s8, f8, num, b, txt, raw, d, dt FROM dbo.tds_types_t WHERE id = %s", (1,))
            row = cur.fetchone()
            assert row[0] == 1 and row[4] == decimal.Decimal("42.75") and row[6] == "hello", row

    def t_output_and_temp():
        with conn() as c:
            cur = c.cursor()
            cur.execute("CREATE TABLE #tmp_t (id INT PRIMARY KEY, v NVARCHAR(50))")
            cur.execute("INSERT INTO #tmp_t OUTPUT INSERTED.id, INSERTED.v VALUES (1, N'one'), (2, N'two')")
            rows = cur.fetchall()
            assert rows == [(1, "one"), (2, "two")], rows

    def t_tx_rollback():
        with conn(autocommit=False) as c:
            cur = c.cursor()
            cur.execute("DROP TABLE IF EXISTS dbo.tds_tx_t")
            cur.execute("CREATE TABLE dbo.tds_tx_t (id INT PRIMARY KEY, v NVARCHAR(50))")
            c.commit()
            cur.execute("INSERT INTO dbo.tds_tx_t VALUES (1, N'ok')")
            c.commit()
            cur.execute("INSERT INTO dbo.tds_tx_t VALUES (2, N'nope')")
            c.rollback()
            cur.execute("SELECT id, v FROM dbo.tds_tx_t")
            rows = cur.fetchall()
            assert rows == [(1, "ok")], rows

    run_test("pymssql", "connect + types + IDENTITY + SCOPE_IDENTITY", t_basic_and_types)
    run_test("pymssql", "#temp table + OUTPUT INSERTED", t_output_and_temp)
    run_test("pymssql", "transaction commit + rollback", t_tx_rollback)


# ============================================================
# 2. SQLAlchemy 2 (mssql+pymssql) + Reflection + Alembic
# ============================================================
def test_sqlalchemy_tds():
    import sqlalchemy as sa
    from sqlalchemy import (
        Boolean,
        CheckConstraint,
        ForeignKey,
        Index,
        Integer,
        Numeric,
        String,
        func,
        inspect,
        select,
    )
    from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, selectinload
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    engine = sa.create_engine(f"mssql+pymssql://{TDS_USER}:{TDS_PASS}@{TDS_HOST}:{TDS_PORT}/{TDS_DB}")

    class Base(DeclarativeBase):
        pass

    class Org(Base):
        __tablename__ = "sa_tds_orgs"
        id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
        name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
        users: Mapped[list["User"]] = relationship(back_populates="org", cascade="all, delete-orphan")

    class User(Base):
        __tablename__ = "sa_tds_users"
        __table_args__ = (
            CheckConstraint("age >= 0", name="ck_sa_tds_users_age"),
            Index("ix_sa_tds_users_org_age", "org_id", "age"),
        )
        id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
        org_id: Mapped[int] = mapped_column(ForeignKey("sa_tds_orgs.id", ondelete="CASCADE"), nullable=False)
        email: Mapped[str] = mapped_column(String(200), nullable=False)
        age: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
        balance: Mapped[decimal.Decimal] = mapped_column(Numeric(12, 2), default=decimal.Decimal("0.00"))
        active: Mapped[bool] = mapped_column(Boolean, default=True)
        org: Mapped[Org] = relationship(back_populates="users")

    def t_ddl_and_crud():
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
        with Session(engine) as s:
            o = Org(name="Acme")
            o.users = [
                User(email="a@acme.com", age=30, balance=decimal.Decimal("100.50")),
                User(email="b@acme.com", age=25, balance=decimal.Decimal("50.25")),
            ]
            s.add(o)
            s.commit()
            assert o.id is not None and o.users[0].id is not None

        with Session(engine) as s:
            orgs = s.scalars(select(Org).options(selectinload(Org.users))).all()
            assert len(orgs) == 1 and len(orgs[0].users) == 2
            page = s.scalars(select(User).order_by(User.age.desc()).offset(1).limit(1)).all()
            assert len(page) == 1 and page[0].email == "b@acme.com", page
            tot = s.scalar(select(func.sum(User.balance)))
            assert tot == decimal.Decimal("150.75"), tot

    def t_inspector():
        insp = inspect(engine)
        tables = insp.get_table_names()
        assert "sa_tds_orgs" in tables and "sa_tds_users" in tables, tables
        cols = insp.get_columns("sa_tds_users")
        assert len(cols) == 6, cols
        pk = insp.get_pk_constraint("sa_tds_users")
        assert pk["constrained_columns"] == ["id"], pk
        fks = insp.get_foreign_keys("sa_tds_users")
        assert len(fks) == 1 and fks[0]["referred_table"] == "sa_tds_orgs", fks
        ixs = insp.get_indexes("sa_tds_users")
        assert any(i["name"] == "ix_sa_tds_users_org_age" for i in ixs), ixs
        org_ixs = insp.get_indexes("sa_tds_orgs")
        assert any(i.get("unique") and i["column_names"] == ["name"] for i in org_ixs), org_ixs

    def t_alembic_autogenerate():
        with engine.connect() as conn:
            ctx = MigrationContext.configure(
                conn,
                opts={
                    "include_object": lambda obj, name, type_, reflected, compare_to: (
                        name is None or name.startswith("sa_tds_")
                    )
                },
            )
            diffs = compare_metadata(ctx, Base.metadata)
            if diffs:
                raise AssertionError(f"unexpected alembic diffs: {diffs}")

    run_test("SQLAlchemy-TDS", "create_all + ORM CRUD + OFFSET/FETCH", t_ddl_and_crud)
    run_test("SQLAlchemy-TDS", "Inspector reflection (cols/PK/FK/IX/UQ)", t_inspector)
    run_test("SQLAlchemy-TDS", "Alembic autogenerate clean diff", t_alembic_autogenerate)


if __name__ == "__main__":
    print("=== SQL Server (TDS) Door Compatibility Suite ===")
    test_pymssql()
    test_sqlalchemy_tds()
    fails = [r for r in results if r[2] == "FAIL"]
    print(f"TDS Summary: {len(results) - len(fails)}/{len(results)} passed, {len(fails)} failed")
    sys.exit(1 if fails else 0)
