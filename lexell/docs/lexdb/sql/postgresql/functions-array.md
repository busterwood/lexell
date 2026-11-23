# Array functions

Functions that build, search, measure and change arrays.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
array_append ( array, element ) → array
array_prepend ( element, array ) → array
array_cat ( array, array ) → array
array_remove ( array, element ) → array
array_replace ( array, from, to ) → array
array_position ( array, element [, start ] ) → integer
array_positions ( array, element ) → integer[]
array_to_string ( array, delimiter [, null_string ] ) → text
array_length ( array, dimension ) → integer
array_lower ( array, dimension ) → integer
array_upper ( array, dimension ) → integer
array_ndims ( array ) → integer
array_dims ( array ) → text
cardinality ( array ) → integer
trim_array ( array, n ) → array
array_reverse ( array ) → array
array_shuffle ( array ) → array
array_sample ( array, n ) → array
unnest ( array ) → setof element
generate_subscripts ( array, dimension [, reverse ] ) → setof integer
```

## Functions

`array_append`, `array_prepend`, `array_cat`
: The array with an element added at the end or the start, or two arrays joined. `||` does the same.

`array_remove`
: The array without the elements equal to *element* (NULL removes NULLs).

`array_replace`
: The array with each element equal to *from* replaced by *to*.

`array_position`
: The place of the first element equal to *element*, from *start*; NULL if there is none.

`array_positions`
: The places of all the elements equal to *element*.

`array_to_string`
: The elements as text, with *delimiter* between them. NULL elements are left out, or written as *null_string*.

`array_length`, `array_upper`
: The number of elements in *dimension* (1). NULL for an empty array.

`array_lower`
: The first subscript, 1.

`array_ndims`
: The number of dimensions: 1, or NULL for an empty array.

`array_dims`
: The bounds as text, `[1:n]`.

`cardinality`
: The number of elements; 0 for an empty array.

`trim_array`
: The array without its last *n* elements (PostgreSQL 14).

`array_reverse`
: The elements in the opposite order (PostgreSQL 18).

`array_shuffle`, `array_sample`
: The elements in random order, or *n* of them chosen at random (PostgreSQL 16).

`unnest`
: The elements as rows. See [set-returning functions](functions-srf.md) for `WITH ORDINALITY`.

`generate_subscripts`
: The subscripts of *dimension* as rows, from the last with *reverse* true.

## Remarks

- See [array types](data-types-arrays.md) for array constants, subscripts, `ANY`, `ALL`, `@>`, `<@` and `&&`.
- `array_agg` makes an array from rows: see [aggregate functions](functions-aggregate.md).
- A NULL array gives NULL.

## Differences from PostgreSQL

- Arrays have one dimension, so *dimension* can only be 1.
- `generate_subscripts` works in the select list only: in `FROM` it is 42883 (`function
  generate_subscripts(unknown, unknown) does not exist`).
- An element of another type is not refused: `array_append(ARRAY[1, 2], 'x')` gives `{1,2,x}` (PostgreSQL: 22P02).
- `array_fill`, `array_to_json` and `array_sort` do not exist.

## Examples

### A. Adding and joining

<!-- example: postgresql -->
```sql
SELECT array_append(ARRAY[1, 2], 3) AS append, array_prepend(0, ARRAY[1, 2]) AS prepend,
       array_cat(ARRAY[1, 2], ARRAY[3, 4]) AS cat;
```

```text
 append  | prepend |    cat
---------+---------+-----------
 {1,2,3} | {0,1,2} | {1,2,3,4}
(1 row)
```

### B. Removing and replacing

<!-- example: postgresql -->
```sql
SELECT array_remove(ARRAY[1, 2, 1, 3], 1) AS remove, array_replace(ARRAY[1, 2, 1], 1, 9) AS replace,
       trim_array(ARRAY[1, 2, 3, 4], 2) AS trimmed, array_reverse(ARRAY[1, 2, 3]) AS reversed;
```

```text
 remove | replace | trimmed | reversed
--------+---------+---------+----------
 {2,3}  | {9,2,9} | {1,2}   | {3,2,1}
(1 row)
```

### C. Searching

<!-- example: postgresql -->
```sql
SELECT array_position(ARRAY['a', 'b', 'c', 'b'], 'b') AS first_b, array_position(ARRAY['a', 'b', 'c', 'b'], 'b', 3)
       AS next_b, array_positions(ARRAY['a', 'b', 'c', 'b'], 'b') AS all_b, array_position(ARRAY['a'], 'z') AS none;
```

```text
 first_b | next_b | all_b | none
---------+--------+-------+------
       2 |      4 | {2,4} |
(1 row)
```

### D. To text

<!-- example: postgresql -->
```sql
SELECT array_to_string(ARRAY['a', NULL, 'c'], ',') AS skip_null, array_to_string(ARRAY['a', NULL, 'c'], ',', '-')
       AS with_null;
```

```text
 skip_null | with_null
-----------+-----------
 a,c       | a,-,c
(1 row)
```

### E. Sizes

<!-- example: postgresql -->
```sql
SELECT array_length(ARRAY[1, 2, 3], 1) AS len, array_lower(ARRAY[1, 2, 3], 1) AS lower,
       array_upper(ARRAY[1, 2, 3], 1) AS upper, array_ndims(ARRAY[1, 2, 3]) AS ndims,
       array_dims(ARRAY[1, 2, 3]) AS dims, cardinality(ARRAY[1, 2, 3]) AS card,
       cardinality(ARRAY[]::int[]) AS card_empty, array_length(ARRAY[]::int[], 1) AS len_empty;
```

```text
 len | lower | upper | ndims | dims  | card | card_empty | len_empty
-----+-------+-------+-------+-------+------+------------+-----------
   3 |     1 |     3 |     1 | [1:3] |    3 |          0 |
(1 row)
```

### F. Random order

The values change from call to call, so the example sorts them.

<!-- example: postgresql -->
```sql
SELECT (SELECT array_agg(x ORDER BY x) FROM unnest(array_shuffle(ARRAY[3, 1, 2])) x) AS shuffled_sorted,
       cardinality(array_sample(ARRAY[1, 2, 3, 4, 5], 2)) AS sample_size;
```

```text
 shuffled_sorted | sample_size
-----------------+-------------
 {1,2,3}         |           2
(1 row)
```

### G. unnest and generate_subscripts

<!-- example: postgresql -->
```sql
SELECT unnest(ARRAY['x', 'y', 'z']) AS element;
SELECT generate_subscripts(ARRAY['x', 'y', 'z'], 1) AS i;
SELECT generate_subscripts(ARRAY['x', 'y', 'z'], 1, true) AS i;
```

```text
 element
---------
 x
 y
 z
(3 rows)

 i
---
 1
 2
 3
(3 rows)

 i
---
 3
 2
 1
(3 rows)
```

### H. On a column

<!-- example: postgresql -->
```sql
CREATE TABLE post (id int, tags text[]);
INSERT INTO post VALUES (1, '{sql,lexdb}'), (2, '{sql}'), (3, '{}');
UPDATE post SET tags = array_append(tags, 'new') WHERE id = 2;
SELECT id, tags, cardinality(tags) AS n, array_to_string(tags, ' | ') AS shown FROM post ORDER BY id;
```

```text
CREATE TABLE
INSERT 0 3
UPDATE 1
 id |    tags     | n |    shown
----+-------------+---+-------------
  1 | {sql,lexdb} | 2 | sql | lexdb
  2 | {sql,new}   | 2 | sql | new
  3 | {}          | 0 |
(3 rows)
```

### I. Errors

<!-- example: postgresql -->
```sql
SELECT * FROM generate_subscripts(ARRAY['x', 'y', 'z'], 1);
SELECT array_fill(0, ARRAY[3]);
```

```text
ERROR:  function generate_subscripts(unknown, unknown) does not exist
HINT:  No function matches the given name and argument types. You might need to add explicit type casts.
ERROR:  function array_fill with 2 arguments does not exist
```

## See also

[Array types](data-types-arrays.md) · [Set-returning functions](functions-srf.md) ·
[Aggregate functions](functions-aggregate.md) · [Operators](operators.md)
