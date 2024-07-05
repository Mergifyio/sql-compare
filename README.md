# SQL Compare

Compare SQL schemas.

This package allows to compare two SQL files (or strings) to know whether their
statements are the same or not. The comparison doesn't care about the order of
the columns in a table or the order of the values in an enumerator. It also
excludes irrelevant data like comments.

Its main usage is to compare the schemas of two databases (e.g. staging and
production). See this [blog post](https://blog.mergify.com/ensuring-seamless-sql-migrations-in-production/)
that tells about the creation of the package.

## Installation

```bash
$ pip install sql-compare
```

## Usage

Compare two SQL schemas using strings.

```python
import sql_compare

assert sql_compare.compare(first_schema, second_schema)
```

Compare two SQL schemas using files.

```python
import pathlib
import sql_compare

first_schema = pathlib.Path("/path/to/schema.sql")
second_schema = pathlib.Path("/path/to/other/schema.sql")

assert sql_compare.compare_files(first_schema, second_schema)
```

## Dependencies

SQL Compare relies on [`sqlparse`](https://sqlparse.readthedocs.io/en/latest/)
to parse SQL statements.
