# PL/SQL control statements

`IF`, `CASE`, `LOOP`, `WHILE`, `FOR`, `EXIT`, `CONTINUE`, `RETURN` and `NULL`.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
IF condition THEN statements [ ELSIF condition THEN statements ]... [ ELSE statements ] END IF;

CASE selector WHEN value THEN statements [ WHEN ... THEN ... ] [ ELSE statements ] END CASE;
CASE WHEN condition THEN statements [ WHEN ... THEN ... ] [ ELSE statements ] END CASE;

[ <<label>> ] LOOP statements END LOOP [ label ];
[ <<label>> ] WHILE condition LOOP statements END LOOP [ label ];
[ <<label>> ] FOR counter IN [ REVERSE ] low .. high LOOP statements END LOOP [ label ];
[ <<label>> ] FOR record IN { cursor [ ( arguments ) ] | ( select ) } LOOP statements END LOOP [ label ];

EXIT [ label ] [ WHEN condition ];
CONTINUE [ label ] [ WHEN condition ];
RETURN [ expr ];
NULL;
```

## Arguments

`IF`, `ELSIF`
: Run the first branch whose condition is true. A condition that is NULL counts as false.

`CASE` statement
: Like the `CASE` expression, but its branches are statements. With no matching branch and no `ELSE`, the statement
  raises `CASE_NOT_FOUND` (ORA-06592).

`LOOP`
: Repeats until an `EXIT`.

`WHILE`
: Repeats while the condition is true.

`FOR counter IN low .. high`
: Runs for each integer from *low* to *high* (from *high* down with `REVERSE`). The counter exists inside the loop
  only and cannot be assigned.

`FOR record IN cursor`
: Runs for each row of a cursor or a query, with the row in *record*: see [cursors](plsql-cursors.md).

`EXIT`, `CONTINUE`
: Leave the loop, or go to its next round, optionally only `WHEN` a condition holds. With a *label* they act on the
  outer loop that carries it.

`RETURN`
: Ends a function with its value, or a procedure or block early.

`NULL`
: Does nothing; it fills a branch that needs a statement.

## Remarks

- Conditions follow SQL's: a comparison with NULL is not true.
- `GOTO` is not supported.

## Differences from Oracle

- `GOTO` is PLS-00103. `FORALL` is PLS-00103.
- `FOR counter IN` over a cursor `FOR` loop's collection range (`FIRST .. LAST`) is not available: collections are not
  supported.

## Examples

### A. IF and CASE

<!-- example: oracle -->
```sql
DECLARE
  n NUMBER := 7;
BEGIN
  IF n < 5 THEN
    DBMS_OUTPUT.PUT_LINE('small');
  ELSIF n < 10 THEN
    DBMS_OUTPUT.PUT_LINE('medium');
  ELSE
    DBMS_OUTPUT.PUT_LINE('large');
  END IF;
  CASE n
    WHEN 7 THEN DBMS_OUTPUT.PUT_LINE('seven');
    ELSE DBMS_OUTPUT.PUT_LINE('other');
  END CASE;
  CASE
    WHEN n > 5 THEN DBMS_OUTPUT.PUT_LINE('greater than five');
  END CASE;
  DBMS_OUTPUT.PUT_LINE(CASE WHEN n > 5 THEN 'expression yes' ELSE 'expression no' END);
END;
/
```

```text
medium
seven
greater than five
expression yes

PL/SQL procedure successfully completed.
```

### B. Loops

<!-- example: oracle -->
```sql
DECLARE
  i NUMBER := 0;
  total NUMBER := 0;
BEGIN
  LOOP
    i := i + 1;
    EXIT WHEN i > 5;
    CONTINUE WHEN MOD(i, 2) = 0;
    total := total + i;
  END LOOP;
  DBMS_OUTPUT.PUT_LINE('loop total ' || total);
  i := 0;
  WHILE i < 3 LOOP
    i := i + 1;
    DBMS_OUTPUT.PUT_LINE('while ' || i);
  END LOOP;
  FOR j IN 1..3 LOOP
    DBMS_OUTPUT.PUT_LINE('for ' || j);
  END LOOP;
  FOR j IN REVERSE 1..3 LOOP
    DBMS_OUTPUT.PUT_LINE('reverse ' || j);
  END LOOP;
END;
/
```

```text
loop total 9
while 1
while 2
while 3
for 1
for 2
for 3
reverse 3
reverse 2
reverse 1

PL/SQL procedure successfully completed.
```

### C. Leaving an outer loop

<!-- example: oracle -->
```sql
BEGIN
  <<outer>>
  FOR i IN 1..3 LOOP
    FOR j IN 1..3 LOOP
      EXIT outer WHEN i * j = 4;
      DBMS_OUTPUT.PUT_LINE(i || 'x' || j);
    END LOOP;
  END LOOP outer;
END;
/
```

```text
1x1
1x2
1x3
2x1

PL/SQL procedure successfully completed.
```

### D. No branch matched

<!-- example: oracle -->
```sql
DECLARE
  n NUMBER := 3;
BEGIN
  CASE n
    WHEN 1 THEN NULL;
  END CASE;
END;
/
```

```text
ERROR:
ORA-06592: CASE not found while executing CASE statement
ORA-06512: at line 4
```

### E. GOTO and FORALL

<!-- example: oracle -->
```sql
BEGIN
  GOTO done;
  <<done>> NULL;
END;
/
BEGIN
  FORALL i IN 1..3 INSERT INTO emp VALUES (i, 'x', 1);
END;
/
```

```text
ERROR:
ORA-06550: line 2, column 3:
PLS-00103: GOTO is not supported

ERROR:
ORA-06550: line 2, column 10:
PLS-00103: Encountered the symbol "i" when expecting one of the following: ;
```

## See also

[PL/SQL blocks](plsql-blocks.md), [Cursors](plsql-cursors.md), [Exceptions](plsql-exceptions.md)
