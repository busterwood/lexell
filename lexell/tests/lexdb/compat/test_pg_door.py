import asyncio
import datetime
import decimal
import os
import sys
import uuid

PG_HOST = os.environ.get("PG_HOST", "127.0.0.1")
PG_PORT = int(os.environ.get("PG_PORT", "15433"))
PG_USER = os.environ.get("PG_USER", "postgres")
PG_DB = os.environ.get("PG_DB", "lexdb")

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
# 1. psycopg 3 (text & binary)
# ============================================================
def test_psycopg3():
    import psycopg

    dsn = f"host={PG_HOST} port={PG_PORT} user={PG_USER} dbname={PG_DB}"

    def t_types_text():
        with psycopg.connect(dsn, autocommit=True) as conn:
            conn.execute("DROP TABLE IF EXISTS pg_types_t")
            conn.execute("""
                CREATE TABLE pg_types_t (
                    id int PRIMARY KEY,
                    s2 smallint,
                    s8 bigint,
                    f4 real,
                    f8 double precision,
                    num numeric(12,2),
                    b boolean,
                    txt text,
                    raw bytea,
                    u uuid,
                    d date,
                    tm time,
                    ts timestamp,
                    tstz timestamptz,
                    j json,
                    jb jsonb,
                    ia int[],
                    ta text[]
                )
            """)
            uval = uuid.uuid4()
            row = (
                1, 7, 9000000000, 1.5, 2.25, decimal.Decimal("123.45"), True,
                "hello", b"\x01\x02\x03", uval,
                datetime.date(2026, 11, 26), datetime.time(12, 34, 56),
                datetime.datetime(2026, 11, 26, 12, 34, 56),
                datetime.datetime(2026, 11, 26, 12, 34, 56, tzinfo=datetime.timezone.utc),
                '{"a":1}', '{"b":2}', [1, 2, 3], ["x", "y"],
            )
            conn.execute(
                "INSERT INTO pg_types_t VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                row,
            )
            got = conn.execute("SELECT * FROM pg_types_t WHERE id = %s", (1,)).fetchone()
            assert got[0] == 1 and got[5] == decimal.Decimal("123.45") and got[9] == uval, got
            assert got[16] == [1, 2, 3] and got[17] == ["x", "y"], got

    def t_types_binary():
        with psycopg.connect(dsn, autocommit=True) as conn:
            with conn.cursor(binary=True) as cur:
                cur.execute(
                    "SELECT id, s2, s8, f4, f8, num, b, txt, raw, u, d, tm, ts, tstz, j, jb, ia, ta "
                    "FROM pg_types_t WHERE id = %b",
                    (1,),
                )
                got = cur.fetchone()
                assert got[0] == 1 and got[5] == decimal.Decimal("123.45"), got
                assert got[16] == [1, 2, 3] and got[17] == ["x", "y"], got

    def t_savepoint_and_conflict():
        with psycopg.connect(dsn) as conn:
            conn.execute("DROP TABLE IF EXISTS pg_sp_t")
            conn.execute("CREATE TABLE pg_sp_t (id int PRIMARY KEY, v text)")
            conn.commit()
            with conn.transaction():
                conn.execute("INSERT INTO pg_sp_t VALUES (1, 'a')")
                try:
                    with conn.transaction():
                        conn.execute("INSERT INTO pg_sp_t VALUES (2, 'b')")
                        raise RuntimeError("abort sp")
                except RuntimeError:
                    pass
                conn.execute(
                    "INSERT INTO pg_sp_t VALUES (1, 'a2') "
                    "ON CONFLICT (id) DO UPDATE SET v = EXCLUDED.v RETURNING id, v"
                )
            rows = conn.execute("SELECT id, v FROM pg_sp_t ORDER BY id").fetchall()
            assert rows == [(1, "a2")], rows

    def t_copy_and_executemany():
        with psycopg.connect(dsn, autocommit=True) as conn:
            conn.execute("DROP TABLE IF EXISTS pg_bulk_t")
            conn.execute("CREATE TABLE pg_bulk_t (id int PRIMARY KEY, name text)")
            with conn.cursor() as cur:
                cur.executemany("INSERT INTO pg_bulk_t VALUES (%s, %s)", [(1, "a"), (2, "b")])
                with cur.copy("COPY pg_bulk_t (id, name) FROM STDIN") as cp:
                    cp.write_row((3, "c"))
                    cp.write_row((4, "d"))
            cnt = conn.execute("SELECT count(*) FROM pg_bulk_t").fetchone()[0]
            assert cnt == 4, cnt

    run_test("psycopg3", "all types (text)", t_types_text)
    run_test("psycopg3", "all types (binary=True)", t_types_binary)
    run_test("psycopg3", "savepoints + ON CONFLICT RETURNING", t_savepoint_and_conflict)
    run_test("psycopg3", "executemany + COPY FROM STDIN", t_copy_and_executemany)


# ============================================================
# 2. asyncpg (full binary protocol + arrays + introspection)
# ============================================================
def test_asyncpg():
    import asyncpg

    async def _all_types():
        conn = await asyncpg.connect(host=PG_HOST, port=PG_PORT, user=PG_USER, database=PG_DB)
        try:
            r = await conn.fetchrow(
                "SELECT 1::int2, 2::int4, 3::int8, 1.5::float4, 2.25::float8, "
                "123.45::numeric(12,2), true::bool, 'hi'::text, '\\x0102'::bytea, "
                "'550e8400-e29b-41d4-a716-446655440000'::uuid, DATE '2026-11-26', "
                "TIME '12:34:56', TIMESTAMP '2026-11-26 12:34:56', "
                "TIMESTAMPTZ '2026-11-26 12:34:56+00', '{\"a\":1}'::json, '{\"b\":2}'::jsonb"
            )
            assert r[0] == 1 and r[5] == decimal.Decimal("123.45") and r[6] is True, r

            arr = await conn.fetchrow("SELECT ARRAY[1,2,3], ARRAY['a','b']")
            assert arr[0] == [1, 2, 3] and arr[1] == ["a", "b"], arr

            uval = uuid.uuid4()
            p = await conn.fetchrow(
                "SELECT $1::numeric, $2::uuid, $3::bytea, $4::date, $5::timestamp, $6::timestamptz, $7::int[]",
                decimal.Decimal("99.95"),
                uval,
                b"\xaa\xbb",
                datetime.date(2026, 11, 26),
                datetime.datetime(2026, 11, 26, 1, 2, 3),
                datetime.datetime(2026, 11, 26, 1, 2, 3, tzinfo=datetime.timezone.utc),
                [10, 20],
            )
            assert p[0] == decimal.Decimal("99.95") and p[1] == uval and p[6] == [10, 20], p
        finally:
            await conn.close()

    run_test("asyncpg", "scalars + arrays + binary params", lambda: asyncio.run(_all_types()))


# ============================================================
# 3. SQLAlchemy 2 + Reflection + Alembic autogenerate
# ============================================================
def test_sqlalchemy_pg():
    import sqlalchemy as sa
    from sqlalchemy import (
        Boolean,
        CheckConstraint,
        DateTime,
        ForeignKey,
        Index,
        Integer,
        JSON,
        Numeric,
        String,
        func,
        inspect,
        select,
    )
    from sqlalchemy.orm import (
        DeclarativeBase,
        Mapped,
        Session,
        joinedload,
        mapped_column,
        relationship,
        selectinload,
    )
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    engine = sa.create_engine(f"postgresql+psycopg://{PG_USER}@{PG_HOST}:{PG_PORT}/{PG_DB}")

    class Base(DeclarativeBase):
        pass

    class Org(Base):
        __tablename__ = "sa_pg_orgs"
        id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
        name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
        meta: Mapped[dict] = mapped_column(JSON, nullable=True)
        users: Mapped[list["User"]] = relationship(back_populates="org", cascade="all, delete-orphan")

    class User(Base):
        __tablename__ = "sa_pg_users"
        __table_args__ = (
            CheckConstraint("age >= 0", name="ck_sa_pg_users_age"),
            Index("ix_sa_pg_users_org_age", "org_id", "age"),
        )
        id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
        org_id: Mapped[int] = mapped_column(ForeignKey("sa_pg_orgs.id", ondelete="CASCADE"), nullable=False)
        email: Mapped[str] = mapped_column(String(200), nullable=False)
        age: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
        balance: Mapped[decimal.Decimal] = mapped_column(Numeric(12, 2), default=decimal.Decimal("0.00"))
        active: Mapped[bool] = mapped_column(Boolean, default=True)
        created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
        org: Mapped[Org] = relationship(back_populates="users")

    def t_ddl_and_crud():
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
        with Session(engine) as s:
            o = Org(name="Acme", meta={"tier": "pro"})
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
            users = s.scalars(select(User).options(joinedload(User.org)).order_by(User.age.desc())).all()
            assert users[0].email == "a@acme.com" and users[0].org.name == "Acme"
            tot = s.scalar(select(func.sum(User.balance)))
            assert tot == decimal.Decimal("150.75"), tot

    def t_inspector():
        insp = inspect(engine)
        tables = insp.get_table_names()
        assert "sa_pg_orgs" in tables and "sa_pg_users" in tables, tables
        cols = insp.get_columns("sa_pg_users")
        assert len(cols) == 7, cols
        pk = insp.get_pk_constraint("sa_pg_users")
        assert pk["constrained_columns"] == ["id"], pk
        fks = insp.get_foreign_keys("sa_pg_users")
        assert len(fks) == 1 and fks[0]["referred_table"] == "sa_pg_orgs", fks
        ixs = insp.get_indexes("sa_pg_users")
        assert any(i["name"] == "ix_sa_pg_users_org_age" for i in ixs), ixs
        uqs = insp.get_unique_constraints("sa_pg_orgs")
        assert any(u["column_names"] == ["name"] for u in uqs), uqs
        cks = insp.get_check_constraints("sa_pg_users")
        assert len(cks) >= 1, cks

    def t_alembic_autogenerate():
        with engine.connect() as conn:
            ctx = MigrationContext.configure(
                conn,
                opts={
                    "include_object": lambda obj, name, type_, reflected, compare_to: (
                        name is None or name.startswith("sa_pg_")
                    )
                },
            )
            diffs = compare_metadata(ctx, Base.metadata)
            if diffs:
                raise AssertionError(f"unexpected alembic diffs: {diffs}")

    run_test("SQLAlchemy-PG", "create_all + ORM CRUD + eager loads", t_ddl_and_crud)
    run_test("SQLAlchemy-PG", "Inspector reflection (cols/PK/FK/IX/UQ/CK)", t_inspector)
    run_test("SQLAlchemy-PG", "Alembic autogenerate clean diff", t_alembic_autogenerate)


# ============================================================
# 4. Django PostgreSQL backend
# ============================================================
def test_django_pg():
    import django
    from django.conf import settings
    from django.core.management import call_command
    from django.db import connection, transaction

    if not settings.configured:
        settings.configure(
            DEBUG=False,
            SECRET_KEY="test-key",
            DATABASES={
                "default": {
                    "ENGINE": "django.db.backends.postgresql",
                    "NAME": PG_DB,
                    "USER": PG_USER,
                    "PASSWORD": "",
                    "HOST": PG_HOST,
                    "PORT": str(PG_PORT),
                }
            },
            INSTALLED_APPS=[
                "django.contrib.contenttypes",
                "django.contrib.auth",
                "django.contrib.sessions",
            ],
            USE_TZ=True,
            TIME_ZONE="UTC",
            DEFAULT_AUTO_FIELD="django.db.models.BigAutoField",
        )
        django.setup()

    def t_migrate():
        call_command("migrate", verbosity=0, interactive=False)

    def t_auth_orm():
        from django.contrib.auth.models import Group, User
        from django.db.models import Count, Q
        from django.db.models.functions import Lower

        g, created = Group.objects.get_or_create(name="admins")
        assert created
        u = User.objects.create_user(username="alice", email="alice@example.com", password="secret")
        u.groups.add(g)
        u2 = User.objects.create_user(username="bob", email="bob@example.com", password="secret")
        qs = list(
            User.objects.filter(Q(username="alice") | Q(email__icontains="bob"))
            .annotate(lower_name=Lower("username"), gcount=Count("groups"))
            .order_by("username")
        )
        assert len(qs) == 2 and qs[0].gcount == 1 and qs[1].gcount == 0, [
            (x.username, x.gcount) for x in qs
        ]
        u.first_name = "Alice"
        u2.first_name = "Bob"
        User.objects.bulk_update([u, u2], ["first_name"])
        assert User.objects.get(username="alice").first_name == "Alice"

    def t_atomic_savepoints():
        from django.contrib.auth.models import Group

        with transaction.atomic():
            Group.objects.create(name="outer_g")
            try:
                with transaction.atomic():
                    Group.objects.create(name="inner_g")
                    raise ValueError("rollback inner")
            except ValueError:
                pass
        names = set(Group.objects.values_list("name", flat=True))
        assert "outer_g" in names and "inner_g" not in names, names

    def t_introspection():
        with connection.cursor() as cur:
            tables = connection.introspection.get_table_list(cur)
            t_names = [t.name for t in tables]
            assert "auth_user" in t_names, t_names
            desc = connection.introspection.get_table_description(cur, "auth_user")
            assert len(desc) >= 10, desc
            constraints = connection.introspection.get_constraints(cur, "auth_user")
            assert len(constraints) >= 1, constraints

    run_test("Django-PG", "migrate (auth/contenttypes/sessions)", t_migrate)
    run_test("Django-PG", "ORM CRUD + Q/annotate/Lower/Count/bulk_update", t_auth_orm)
    run_test("Django-PG", "nested transaction.atomic() savepoints", t_atomic_savepoints)
    run_test("Django-PG", "schema introspection (tables/desc/constraints)", t_introspection)


if __name__ == "__main__":
    print("=== PostgreSQL Door Compatibility Suite ===")
    test_psycopg3()
    test_asyncpg()
    test_sqlalchemy_pg()
    test_django_pg()
    fails = [r for r in results if r[2] == "FAIL"]
    print(f"PG Summary: {len(results) - len(fails)}/{len(results)} passed, {len(fails)} failed")
    sys.exit(1 if fails else 0)
