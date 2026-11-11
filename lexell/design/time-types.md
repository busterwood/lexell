# Dates, times and intervals: the standard library, for lexdb and everyone

2026-11-11. Research and options, for the user's decision. The user's
direction: lexdb needs dates, timestamps and intervals; rather than types
of lexdb's own, the standard library should have date and time types good
enough for a database, as `Decimal` was added for `numeric`. The .NET
types are the user's reference point.

## 1. What Lexell has (lib/time.lxl, lib/tz.lxl)

| type | what | representation |
|---|---|---|
| `Time` | an instant | `sec` (Unix seconds, 64-bit) + `nsec` |
| `Date` | a calendar date (proleptic Gregorian) | `year`, `month`, `day`; `daysOfDate`/`dateOfDays` convert to a day number |
| `TimeOfDay` | a wall-clock time | nanoseconds since midnight |
| `LocalDateTime` | a date and a time of day, no zone ("SQL datetime2, Postgres timestamp") | `Date` + `TimeOfDay` |
| `OffsetDateTime` | a local date-time and its offset ("SQL datetimeoffset, Postgres timestamptz") | `LocalDateTime` + minutes east of UTC |
| `tz.Zone` | a time zone from the system's TZif files and POSIX rules | `z.at(sec)`: offset, DST, abbreviation; `z.localTime(sec)` |

Plus ISO 8601 parsing and printing, `strftime`/`strptime`, HTTP dates.
The SQL clients in lib (`pgwire`, `sqlserver`, `oracle`) already map
their servers' date and time types onto these.

**The epoch is not a limit.** Unix time is only where zero is. With
64-bit seconds the range is about ±292 billion years. The year 2038
problem belongs to 32-bit counters. A `Date` holds any year an `int`
holds.

**What is missing:**
1. **A duration:** an exact length of time ("90 minutes"). There is
   `addMillis` and `millisUntil` only.
2. **A period:** calendar amounts ("1 month 3 days"), whose length depends
   on where they are applied: a month is 28 to 31 days, and a day is 23 or
   25 hours across a DST change in a zone.
3. **Calendar arithmetic:** add months (with the end of the month
   clamped: January 31 + 1 month = February 28 or 29), add days, the
   difference between two dates or date-times.
4. **From local time to an instant in a zone.** `tz` goes from an instant
   to local time only. The other way has to choose, for a local time that
   does not exist (the spring gap) or happens twice (the autumn overlap).
5. Smaller things: days of the week and year exist; ISO week numbers do
   not. Durations and periods need ISO 8601 text (`PT1H30M`, `P1M3D`).

## 2. How others do it

**PostgreSQL** (what lexdb must match on the wire and in SQL):

| type | stored as | range | precision |
|---|---|---|---|
| `date` | int32 days since 2000-01-01 | 4713 BC to 5874897 AD | a day |
| `time` | int64 microseconds since midnight (24:00:00 allowed) | | 1 us |
| `timestamp` | int64 microseconds since 2000-01-01, no zone | 4713 BC to 294276 AD | 1 us |
| `timestamptz` | the same, an instant in UTC | the same | 1 us |
| `interval` | months (int32), days (int32), microseconds (int64), kept apart | about ±178 million years | 1 us |

- `timestamptz` stores no zone. It is an instant, shown in the
  session's `TimeZone`; input with an offset or a zone name is converted
  to UTC.
- An interval keeps months, days and time apart because none converts to
  the others exactly. `timestamptz + interval '1 day'` adds a day in the
  session's zone, so it is 23 or 25 hours across a DST change.
- Intervals compare by counting a month as 30 days and a day as 24 hours.
- There are `infinity` and `-infinity` for dates and timestamps, and
  `epoch`, `now`, `today` as input words.
- Years are written BC/AD: there is no year 0 in the text, where
  astronomical numbering has one.

**.NET** (the user's reference):
- `DateTime` is 64 bits: 62 bits of ticks (100 ns) since 0001-01-01, and 2
  bits of `Kind` (Unspecified, Utc, Local). Its range is 0001 to 9999.
- The `Kind` flag is the type's best-known flaw: one type is sometimes an
  instant and sometimes a wall-clock reading. Comparisons ignore `Kind`,
  and `Local` depends on the machine.
- `DateTimeOffset` (a `DateTime` and an offset) was added to give an
  unambiguous instant; .NET 6 added `DateOnly` and `TimeOnly`.
- `TimeSpan` is an exact duration in ticks. There is no calendar period
  type; Noda Time (Jon Skeet) exists largely to supply `Instant`,
  `LocalDate`, `LocalDateTime`, `ZonedDateTime`, `Period` and `Duration`.
- Range 0001 to 9999 is narrower than PostgreSQL's, and ticks are finer
  than its microseconds.

**java.time** (JSR-310, from Joda-Time; the model Noda Time copies):
- `Instant` (seconds and nanoseconds since the Unix epoch);
- `LocalDate`, `LocalTime`, `LocalDateTime`, `OffsetDateTime`,
  `ZonedDateTime`;
- `Duration` (exact) and `Period` (years, months, days), kept apart;
- zone conversion with explicit gap and overlap rules (`withEarlierOffsetAtOverlap`, and so on).

**SQL standard:** `DATE`, `TIME`, `TIMESTAMP [WITH TIME ZONE]`, and two
kinds of interval, year-month and day-time, which never mix. PostgreSQL
merged them into one.

Lexell's library already follows java.time: the instant, local and offset
types are separate, so it has none of `DateTime.Kind`'s problems. Moving to
the .NET design would be a step back: its own later types (`DateOnly`,
`TimeOnly`, `DateTimeOffset`, and Noda Time's popularity) are the case
against it.

## 3. Options

**A. lexdb types of its own,** on ints, with PostgreSQL's arithmetic
written in lexdb. Quickest, but the opposite of the user's direction:
the same arithmetic would be needed again by every Lexell program.

**B. Finish the standard library along java.time's lines, and build lexdb
on it (recommended).**
- In `lib/time.lxl`:
  - **`Duration`**: exact, in nanoseconds (int64: ±292 years, as
    Go's). Or seconds and nanoseconds, as Java, for a range as wide as
    `Time`'s; a duration beyond 292 years is rare.
  - **`Period`**: years, months and days. Calendar arithmetic: add to a
    date or date-time with the end of the month clamped; the period
    between two dates.
  - **Arithmetic:**
    - `Date.addDays`, `addMonths`, `addYears`, `daysUntil`;
    - `LocalDateTime.plus(Period)`, `plus(Duration)`;
    - `Time.plus(Duration)`, `Time.until(Time): Duration`.
  - **ISO 8601** text for both: `PT1H30M`, `P1Y2M3D`.
  - ISO week numbers, if wanted.
- In `lib/tz.lxl`: **local time to instant in a zone,** with a stated
  rule for gaps and overlaps (java.time's default: in a gap, move forward
  by its length; in an overlap, the earlier offset; PostgreSQL's choices
  to be checked against it). Perhaps a `ZonedDateTime` (a local
  date-time, a zone, an offset) for arithmetic in a zone.
- In lexdb, the SQL types map onto these:
  - `date` is a day number;
  - `time` is microseconds since midnight;
  - `timestamp` is microseconds, local;
  - `timestamptz` is microseconds, UTC;
  - `interval` is (months, days, microseconds): a `Period` of months and
    days plus a `Duration`, as PostgreSQL keeps them.

  Each is stored as ints, so it sorts and keys like an integer.
  PostgreSQL's own rules stay in lexdb, built on the library's
  arithmetic: microsecond rounding, the 30-day month when intervals
  compare, `infinity`, BC years, its text formats and input words, and
  adding in the session's zone.

**C. Redesign the library after .NET.** One `DateTime` with ticks since
0001 and a kind flag. Not recommended, for the reasons in section 2: it
is what .NET itself moved away from, and its range is narrower than a
database needs.

## 4. Decisions to make, and the recommendation for each

1. **The model: B (java.time).** The library is already half of it, and
   lib's SQL clients use it.
2. **Precision:** the library stays in nanoseconds, as clocks and other
   databases need (SQL Server's datetime2 is 100 ns). lexdb stores
   microseconds and rounds to them, as PostgreSQL does.
3. **`Duration`: int64 nanoseconds.** Simple, exact, and wide enough for
   lengths of time (±292 years). lexdb's interval has its own months and
   days, so long intervals do not need it.
4. **One combined interval type in the library or not.** PostgreSQL's
   interval is a period and a duration together. The recommendation is
   `Period` and `Duration` in the library (the standard pair, and what
   programs reason about), with lexdb's interval holding one of each. A
   combined type can be added later if programs want it.
5. **`Date`'s representation:** keep `year`, `month` and `day` as they
   are (36 uses in lib and cmd), with the day number as the fast path
   (`daysOfDate` exists). lexdb stores day numbers anyway.
6. **Range:** the library's is effectively unbounded. lexdb enforces
   PostgreSQL's: 4713 BC to 294276 AD for timestamps, to 5874897 AD for
   dates.
7. **Zones:** lexdb gets a session `TimeZone` (default UTC; `SET
   TimeZone`), using `tz`.

## 5. Order of work, if B is chosen

1. `time`: `Duration`, `Period`, date and date-time arithmetic, ISO 8601
   text for both. Tests against Python's `datetime` and `dateutil`, as
   `tz` is tested against `zoneinfo`.
2. `tz`: local time to instant, with gap and overlap rules. Tests against
   `zoneinfo` (its `fold`).
3. lexdb:
   - first `date`, `timestamp` and `timestamptz` (text in and out, keys,
     the row layout, parameters, OIDs, comparisons);
   - then `now()`, `current_date`, `current_timestamp`, and `extract` and
     `date_trunc`;
   - then `interval` and the arithmetic;
   - then `time`, and `SET TimeZone`.
4. The client probes of lexdb 9.75 as the test: the CREATE TABLEs that
   failed, and values round-tripped through psycopg, node-postgres and
   SQLAlchemy.
