#
#  Copyright © 2024-2024 Mergify SAS
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

from __future__ import annotations

import pytest
import sqlparse

import sql_compare


@pytest.mark.parametrize(
    ("first_sql", "second_sql"),
    [
        # CREATE TABLE
        ("CREATE TABLE foo (id INT)", "CREATE TABLE foo (id INT)"),
        # Quoted column name
        (
            'CREATE TABLE foo ("authorization" jsonb NOT NULL)',
            'CREATE TABLE foo ("authorization" jsonb NOT NULL)',
        ),
        # Ignore whitespace
        ("CREATE TABLE foo(id INT)", "CREATE TABLE foo (id INT)"),
        # Ignore comment
        ("-- hello\nCREATE TABLE foo (id INT)", "CREATE TABLE foo (id INT)"),
        # Ignore column order
        (
            "CREATE TABLE foo (id INT, name TEXT)",
            "CREATE TABLE foo (name TEXT, id INT)",
        ),
        (
            "CREATE TABLE foo (bar JSON, baz JSONB)",
            "CREATE TABLE foo (baz JSONB, bar JSON)",
        ),
        (
            "CREATE TABLE foo (at timestamp with time zone DEFAULT now() NOT NULL, id bigint NOT NULL)",
            "CREATE TABLE foo (id bigint NOT NULL, at timestamp with time zone DEFAULT now() NOT NULL)",
        ),
        # CREATE ENUM
        (
            "CREATE TYPE public.colors AS ENUM ('RED', 'GREEN', 'BLUE')",
            "CREATE TYPE public.colors AS ENUM ('RED', 'GREEN', 'BLUE')",
        ),
        # Ignore values order in ENUM
        (
            "CREATE TYPE public.colors AS ENUM ('RED', 'GREEN', 'BLUE')",
            "CREATE TYPE public.colors AS ENUM ('RED', 'BLUE', 'GREEN')",
        ),
        # CREATE FUNCTION
        (
            "CREATE FUNCTION foo() RETURNS trigger LANGUAGE plpgsql AS $$BEGIN SELECT 1; END;$$;",
            "CREATE FUNCTION foo() RETURNS trigger LANGUAGE plpgsql AS $$BEGIN SELECT 1; END;$$;",
        ),
        # CREATE SEQUENCE
        (
            "CREATE SEQUENCE foo.bar START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1;",
            "CREATE SEQUENCE foo.bar START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1;",
        ),
        # ALTER TABLE SET DEFAULT
        (
            "ALTER TABLE ONLY foo.bar ALTER COLUMN id SET DEFAULT nextval('foo.bar_id_seq'::regclass);",
            "ALTER TABLE ONLY foo.bar ALTER COLUMN id SET DEFAULT nextval('foo.bar_id_seq'::regclass);",
        ),
        # ALTER TABLE ADD CONSTRAINT
        (
            "ALTER TABLE ONLY foo ADD CONSTRAINT foo_pkey PRIMARY KEY (id1, id2);",
            "ALTER TABLE ONLY foo ADD CONSTRAINT foo_pkey PRIMARY KEY (id1, id2);",
        ),
        # CREATE INDEX
        (
            "CREATE INDEX foo_idx ON foo (id1, id2)",
            "CREATE INDEX foo_idx ON foo (id1, id2)",
        ),
    ],
)
def test_compare_eq(first_sql: str, second_sql: str) -> None:
    assert sql_compare.compare(first_sql, second_sql)


@pytest.mark.parametrize(
    ("first_sql", "second_sql"),
    [
        # Different table name
        ("CREATE TABLE foo (id INT)", "CREATE TABLE bar (id INT)"),
        # Different column name
        ("CREATE TABLE foo (id INT)", "CREATE TABLE foo (ident INT)"),
        # Different column constraint
        ("CREATE TABLE foo (id INT)", "CREATE TABLE foo (id INT NOT NULL)"),
        # Different column type
        ("CREATE TABLE foo (id INT)", "CREATE TABLE foo (id TEXT)"),
        # Different column type
        ("CREATE TABLE foo (bar JSONB)", "CREATE TABLE foo (bar JSON)"),
        # Different column types (JSON and JSONB mixed)
        (
            "CREATE TABLE foo (bar JSONB, baz JSON)",
            "CREATE TABLE foo (bar JSON, baz JSONB)",
        ),
        # Different values in ENUM
        (
            "CREATE TYPE public.colors AS ENUM ('RED', 'GREEN', 'BLUE')",
            "CREATE TYPE public.colors AS ENUM ('RED', 'GREEN')",
        ),
        (
            "CREATE TYPE public.colors AS ENUM ('RED', 'GREEN', 'BLUE')",
            "CREATE TYPE public.colors AS ENUM ('red', 'green', 'blue')",
        ),
        # Different function body
        (
            "CREATE FUNCTION foo() RETURNS trigger LANGUAGE plpgsql AS $$BEGIN SELECT 1; END;$$;",
            "CREATE FUNCTION foo() RETURNS trigger LANGUAGE plpgsql AS $$BEGIN SELECT 2; END;$$;",
        ),
        # Different sequence arguments
        (
            "CREATE SEQUENCE foo.bar START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1;",
            "CREATE SEQUENCE foo.bar START WITH 2 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1;",
        ),
        (
            "CREATE SEQUENCE foo.bar START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1;",
            "CREATE SEQUENCE foo.bar START WITH 1 INCREMENT BY 2 NO MINVALUE NO MAXVALUE CACHE 1;",
        ),
        # Different ALTER TABLE SET DEFAULT
        (
            "ALTER TABLE ONLY foo.bar ALTER COLUMN id SET DEFAULT nextval('foo.bar_id_seq'::regclass);",
            "ALTER TABLE ONLY foo.bar ALTER COLUMN id SET DEFAULT nextval('foo.another_id_seq'::regclass);",
        ),
        # Different primary key columns
        (
            "ALTER TABLE ONLY foo ADD CONSTRAINT foo_pkey PRIMARY KEY (id1, id2);",
            "ALTER TABLE ONLY foo ADD CONSTRAINT foo_pkey PRIMARY KEY (id2, id1);",
        ),
        # Different CREATE INDEX columns
        (
            "CREATE INDEX foo_idx ON foo (id1, id2)",
            "CREATE INDEX foo_idx ON foo (id2, id1)",
        ),
    ],
)
def test_compare_neq(first_sql: str, second_sql: str) -> None:
    assert not sql_compare.compare(first_sql, second_sql)


@pytest.mark.parametrize(
    ("sql", "expected_type"),
    [
        ("SELECT id FROM foo", "SELECT"),
        ("INSERT INTO foo (id) VALUES (1)", "INSERT"),
        ("UPDATE foo SET id = 1", "UPDATE"),
        ("DELETE FROM foo WHERE id = 1", "DELETE"),
        ("CREATE TABLE foo (id INT)", "CREATE TABLE"),
        ("CREATE TYPE public.colors AS ENUM ('RED', 'GREEN', 'BLUE')", "CREATE TYPE"),
        (
            "CREATE FUNCTION foo() RETURNS trigger LANGUAGE plpgsql AS $$BEGIN SELECT 1; END;$$;",
            "CREATE FUNCTION",
        ),
        (
            "CREATE SEQUENCE foo.bar START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1;",
            "CREATE SEQUENCE",
        ),
        ("CREATE INDEX foo_idx ON foo (id)", "CREATE INDEX"),
        (
            "ALTER TABLE ONLY foo.bar ALTER COLUMN id SET DEFAULT nextval('foo.bar_id_seq'::regclass);",
            "ALTER TABLE",
        ),
        (
            "ALTER TABLE ONLY foo ADD CONSTRAINT foo_pkey PRIMARY KEY (id1, id2);",
            "ALTER TABLE",
        ),
        ("DROP TABLE foo", "DROP TABLE"),
        ("DROP INDEX foo_idx", "DROP INDEX"),
    ],
)
def test_statement_type(sql: str, expected_type: str) -> None:
    statement = sql_compare.Statement(sqlparse.parse(sql)[0])
    assert statement.statement_type == expected_type
