# SELECT ... WAIT

A `SELECT` that, when it finds no rows, waits for a commit that gives it some: a consumer reads a table as an
event stream.

**Door:** PostgreSQL. **Follows:** lexdb's own clause (design/lexdb-events.md); PostgreSQL 18 has none. The same
clause works in the SQL Server and Oracle doors.

## Syntax

```
SELECT select_list
FROM table_name [ [ AS ] alias ]
WHERE cursor_column > value [ AND key_column = value ... ] [ AND condition ... ]
ORDER BY cursor_column
LIMIT count
WAIT count { SECOND | SECONDS | MILLISECOND | MILLISECONDS | MS }
```

## Arguments

*cursor_column*
: The column the stream is read in order of, typically a sequence number that only grows. `WHERE` bounds it from
  below (`>` or `>=`) by the last value the consumer has seen, and `ORDER BY` sorts by it, ascending.

*value*
: A literal or a parameter (`$1`).

*key_column* `=` *value*
: Optional equalities, for a table that holds several streams: `topic = $2 AND seq > $1`.

*condition*
: Other filters on the row itself: no subqueries, and no `nextval`, `setval`, `currval`, `set_config` or
  `current_setting`.

`LIMIT` *count*
: The most rows to return at once.

`WAIT` *count* *unit*
: How long to wait: a whole number, a parameter, or one in parentheses. The wait is capped at 60 seconds. `wait` is
  not a reserved word, and is a column or alias name anywhere else.

## Remarks

- When the query finds rows, it returns them at once. When it finds none, it waits until a commit is written to the
  log, runs again, and returns as soon as it has rows. When the time is up it runs a last time, and returns no rows
  if there are still none.
- The table needs an index (or the primary key) that begins with the *key_column*s, in any order, then
  *cursor_column*, so that each run reads only the rows after the cursor.
- The query must have this shape; anything else is 0A000 with a message beginning `lexdb: WAITFOR`. It reads one
  ordinary table (not a view, a catalog relation or a temporary table), without a column alias list, and has no
  aggregates, `GROUP BY`, `DISTINCT`, window functions, `OFFSET`, `WITH TIES`, locking clause or subqueries.
- Only a statement that begins with `SELECT` takes the clause: not a subquery, and not a `SELECT` after `WITH`
  (42601).
- Outside a transaction block, each run takes a new snapshot.
- In a transaction block, the waiting `SELECT` must be the block's first statement. The block's snapshot is taken
  when the wait ends, so the rest of the block sees what the `SELECT` saw. Its reads are checked at commit as any
  read is, except past the last row it read: rows committed after it by producers do not fail the block's commit.
  A consumer updates its stored position in the same block (`UPDATE ... SET last_seen = $2 WHERE ... AND last_seen
  = $1`), so two consumers never both process the same rows.
- `statement_timeout` ends the wait with 57014 if it comes first.
- A replica refuses a waiting `SELECT` (0A000).
- A waiting session holds its connection for the whole wait; client command timeouts must be longer than the wait.

## Differences from PostgreSQL

- The clause is lexdb's. PostgreSQL's nearest is `LISTEN`/`NOTIFY` with a query after each notice; lexdb has no
  `LISTEN` or `NOTIFY`.
- The refusals' messages say `WAITFOR`, an older name of the clause.
- A cancel request does not end the wait (lexdb ignores cancel requests).

## Examples

<!--setup: postgresql
CREATE TABLE event (seq bigint PRIMARY KEY, topic text NOT NULL, body text);
CREATE INDEX event_topic ON event (topic, seq);
INSERT INTO event VALUES (1, 'order', 'o-1'), (2, 'stock', 's-1'), (3, 'order', 'o-2');
CREATE TABLE consumer (name text PRIMARY KEY, last_seen bigint NOT NULL);
INSERT INTO consumer VALUES ('mailer', 1);
-->

The examples use a stream table and a table of consumers' positions:

```sql
CREATE TABLE event (seq bigint PRIMARY KEY, topic text NOT NULL, body text);
CREATE INDEX event_topic ON event (topic, seq);
INSERT INTO event VALUES (1, 'order', 'o-1'), (2, 'stock', 's-1'), (3, 'order', 'o-2');
CREATE TABLE consumer (name text PRIMARY KEY, last_seen bigint NOT NULL);
INSERT INTO consumer VALUES ('mailer', 1);
```

### A. Rows already there

The query returns at once.

<!-- example: postgresql -->
```sql
SELECT seq, topic, body FROM event WHERE seq > 1 ORDER BY seq LIMIT 10 WAIT 30 SECONDS;
```

```text
 seq | topic | body
-----+-------+------
   2 | stock | s-1
   3 | order | o-2
(2 rows)
```

### B. No rows in time

The query waits 200 milliseconds, then returns no rows.

<!-- example: postgresql -->
```sql
SELECT seq, body FROM event WHERE seq > 3 ORDER BY seq LIMIT 10 WAIT 200 MILLISECONDS;
```

```text
 seq | body
-----+------
(0 rows)
```

### C. One topic

The index on `(topic, seq)` serves `topic = 'order' AND seq > 1`.

<!-- example: postgresql -->
```sql
SELECT seq, body FROM event WHERE topic = 'order' AND seq > 1 ORDER BY seq LIMIT 10 WAIT 5 SECONDS;
```

```text
 seq | body
-----+------
   3 | o-2
(1 row)
```

### D. A consumer's block

The waiting `SELECT` comes first in the block; the consumer then moves its position, only from where it read.

<!-- example: postgresql -->
```sql
BEGIN;
SELECT seq, body FROM event WHERE seq > 1 ORDER BY seq LIMIT 2 WAIT 30 SECONDS;
UPDATE consumer SET last_seen = 3 WHERE name = 'mailer' AND last_seen = 1;
COMMIT;
SELECT * FROM consumer;
```

```text
BEGIN
 seq | body
-----+------
   2 | s-1
   3 | o-2
(2 rows)

UPDATE 1
COMMIT
  name  | last_seen
--------+-----------
 mailer |         3
(1 row)
```

### E. Refused shapes

<!-- example: postgresql -->
```sql
SELECT count(*) FROM event WHERE seq > 0 ORDER BY seq LIMIT 1 WAIT 1 SECOND;
SELECT * FROM event WHERE seq > 0 ORDER BY seq WAIT 1 SECOND;
SELECT * FROM event WHERE body = 'x' AND seq > 0 ORDER BY body LIMIT 1 WAIT 1 SECOND;
SELECT * FROM event WHERE seq > 0 ORDER BY seq LIMIT 1 WAIT 0.5 SECONDS;
BEGIN;
SELECT 1;
SELECT * FROM event WHERE seq > 0 ORDER BY seq LIMIT 1 WAIT 1 SECOND;
ROLLBACK;
```

```text
ERROR:  lexdb: WAITFOR cannot have aggregates, GROUP BY, DISTINCT or windows
ERROR:  lexdb: WAITFOR needs a LIMIT (or TOP)
ERROR:  lexdb: WAITFOR needs ORDER BY c, WHERE c > v and an index on (k ..., c), its k from WHERE's k = v
ERROR:  WAIT takes a whole number of seconds or milliseconds
BEGIN
 ?column?
----------
        1
(1 row)

ERROR:  lexdb: WAITFOR must be the first statement of its transaction block
ROLLBACK
```

## See also

[SELECT](select.md) · [Read replicas](../../replicas.md)
