# Trigonometric functions

Sine, cosine and their kin, in radians and in degrees, and the hyperbolic functions.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
sin ( x ) → double precision
cos ( x ) → double precision
tan ( x ) → double precision
cot ( x ) → double precision
asin ( x ) → double precision
acos ( x ) → double precision
atan ( x ) → double precision
atan2 ( y, x ) → double precision
sind ( x ) → double precision
cosd ( x ) → double precision
tand ( x ) → double precision
cotd ( x ) → double precision
asind ( x ) → double precision
acosd ( x ) → double precision
atand ( x ) → double precision
atan2d ( y, x ) → double precision
sinh ( x ) → double precision
cosh ( x ) → double precision
tanh ( x ) → double precision
asinh ( x ) → double precision
acosh ( x ) → double precision
atanh ( x ) → double precision
```

*x* and *y* are any numeric type, converted to `double precision`.

## Functions

`sin`, `cos`, `tan`, `cot`
: The sine, cosine, tangent and cotangent of an angle in radians.

`asin`, `acos`, `atan`
: The inverse functions, in radians. `asin` and `acos` take -1 to 1; outside that is 22003.

`atan2`
: The angle in radians of the point (*x*, *y*), from -π to π.

`sind`, `cosd`, `tand`, `cotd`, `asind`, `acosd`, `atand`, `atan2d`
: The same with angles in degrees. They give exact results at whole multiples of 30 and 45 degrees: `sind(30)` is
  exactly 0.5.

`sinh`, `cosh`, `tanh`
: The hyperbolic sine, cosine and tangent.

`asinh`, `acosh`, `atanh`
: The inverse hyperbolic functions. `acosh` takes 1 and above, `atanh` -1 to 1; outside that is 22003.

## Remarks

- [`pi()`, `degrees` and `radians`](functions-math.md) convert between the two units.
- A NULL argument gives NULL.

## Differences from PostgreSQL

None known.

## Examples

### A. Radians

<!-- example: postgresql -->
```sql
SELECT sin(0) AS sin0, cos(0) AS cos0, round(sin(pi() / 6)::numeric, 6) AS sin30, round(tan(pi() / 4)::numeric, 6)
       AS tan45, round(cot(pi() / 4)::numeric, 6) AS cot45;
```

```text
 sin0 | cos0 |  sin30   |  tan45   |  cot45
------+------+----------+----------+----------
    0 |    1 | 0.500000 | 1.000000 | 1.000000
(1 row)
```

### B. Degrees

<!-- example: postgresql -->
```sql
SELECT sind(30) AS sind, cosd(60) AS cosd, tand(45) AS tand, cotd(45) AS cotd,
       asind(0.5) AS asind, acosd(0.5) AS acosd, atand(1) AS atand, atan2d(1, 1) AS atan2d;
```

```text
 sind | cosd | tand | cotd | asind | acosd | atand | atan2d
------+------+------+------+-------+-------+-------+--------
  0.5 |  0.5 |    1 |    1 |    30 |    60 |    45 |     45
(1 row)
```

### C. Inverse functions

<!-- example: postgresql -->
```sql
SELECT round(asin(1)::numeric, 6) AS asin, round(acos(0)::numeric, 6) AS acos, round(atan(1)::numeric, 6) AS atan,
       round(atan2(1, -1)::numeric, 6) AS atan2;
```

```text
   asin   |   acos   |   atan   |  atan2
----------+----------+----------+----------
 1.570796 | 1.570796 | 0.785398 | 2.356194
(1 row)
```

### D. Hyperbolic functions

<!-- example: postgresql -->
```sql
SELECT sinh(0) AS sinh, cosh(0) AS cosh, round(tanh(1)::numeric, 6) AS tanh,
       round(asinh(1)::numeric, 6) AS asinh, acosh(1) AS acosh, round(atanh(0.5)::numeric, 6) AS atanh;
```

```text
 sinh | cosh |   tanh   |  asinh   | acosh |  atanh
------+------+----------+----------+-------+----------
    0 |    1 | 0.761594 | 0.881374 |     0 | 0.549306
(1 row)
```

### E. Distance on a sphere

The great-circle distance in kilometres between two points given in degrees.

<!-- example: postgresql -->
```sql
SELECT round((6371 * acos(sind(48.85) * sind(51.51) + cosd(48.85) * cosd(51.51) * cosd(-0.13 - 2.35)))::numeric)
       AS paris_london_km;
```

```text
 paris_london_km
-----------------
             344
(1 row)
```

### F. Errors

<!-- example: postgresql -->
```sql
SELECT asin(2);
SELECT acosh(0.5);
```

```text
ERROR:  input is out of range
ERROR:  input is out of range
```

## See also

[Mathematical functions](functions-math.md) · [Numeric types](data-types-numeric.md)
