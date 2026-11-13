-- A schema made over PostgreSQL's protocol, for the VS Code live check (vscode.py, through psql) and
-- run/tds_pgcatalog.lxl: a schema other than dbo, serial and bigserial keys, PostgreSQL's types, a
-- cascading foreign key, an index and a view.
DROP VIEW IF EXISTS app.recent_events;
DROP TABLE IF EXISTS app.events;
DROP TABLE IF EXISTS app.users;
DROP SCHEMA IF EXISTS app;
CREATE SCHEMA app;
CREATE TABLE app.users (id bigserial PRIMARY KEY, login varchar(40) NOT NULL UNIQUE, bio text, balance numeric(12,2) NOT NULL DEFAULT 0, active boolean NOT NULL DEFAULT true, born date, seen timestamp, joined timestamptz NOT NULL DEFAULT now(), score float8, ratio real, level smallint, token uuid NOT NULL DEFAULT gen_random_uuid());
CREATE TABLE app.events (id serial PRIMARY KEY, user_id bigint NOT NULL REFERENCES app.users(id) ON DELETE CASCADE, took interval, payload bytea, at time, tags text[]);
CREATE INDEX events_user_at ON app.events (user_id, at);
CREATE VIEW app.recent_events AS SELECT id, user_id, at FROM app.events WHERE at > '12:00';
INSERT INTO app.users (login, bio) VALUES ('ann', 'hello'), ('bob', NULL);
INSERT INTO app.events (user_id, took, payload, at, tags) VALUES (1, '1 hour', '\x00ff', '13:00', '{a,b}');
