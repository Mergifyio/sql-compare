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

"""Compare SQL schemas."""

from __future__ import annotations

import dataclasses
import itertools
import typing

import sqlparse


if typing.TYPE_CHECKING:
    from collections.abc import Generator
    import pathlib


def compare_files(first_file: pathlib.Path, second_file: pathlib.Path) -> bool:
    """Compare two SQL files."""
    return compare(first_file.read_text(), second_file.read_text())


def compare(first_sql: str, second_sql: str) -> bool:
    """Compare two SQL strings."""
    first_sql_statements = [Statement(t) for t in sqlparse.parse(first_sql)]
    second_sql_statements = [Statement(t) for t in sqlparse.parse(second_sql)]
    return first_sql_statements == second_sql_statements


def get_diff(
    first_sql: str,
    second_sql: str,
) -> list[list[list[str]]]:
    """Show the difference between two SQL schemas, ignoring differences due to column order and other non-significant SQL changes."""
    first_set = {Statement(t) for t in sqlparse.parse(first_sql)}
    second_set = {Statement(t) for t in sqlparse.parse(second_sql)}
    first_diffs = sorted([stmt.str_tokens for stmt in first_set - second_set])
    second_diffs = sorted([stmt.str_tokens for stmt in second_set - first_set])

    return [first_diffs, second_diffs]


@dataclasses.dataclass
class Token:
    """Wrapper around `sqlparse.sql.Token`."""

    token: sqlparse.sql.Token

    def __repr__(self) -> str:
        """Return the hash."""
        return f'"{self.token.normalized}"'

    @property
    def hash(self) -> str:
        """Return the normalized token value."""
        return str(self.token.normalized)

    @property
    def ignore(self) -> bool:
        """Return whether the token should be ignored."""
        return self.token.is_whitespace or self.is_comment

    @property
    def is_comment(self) -> bool:
        """Return whether the token is a comment."""
        return isinstance(self.token, sqlparse.sql.Comment)

    @property
    def is_separator(self) -> bool:
        """Return whether the token is a separator."""
        return bool(
            self.token.ttype == sqlparse.tokens.Punctuation
            and self.token.normalized == ",",
        )

    @property
    def str_tokens(self) -> list[str]:
        """Return the token value."""
        if self.hash.strip():
            return [self.hash]
        return []


@dataclasses.dataclass
class TokenList:
    """Wrapper around `sqlparse.sql.TokenList`."""

    token_list: sqlparse.sql.TokenList
    parent: TokenList | None = None

    def __eq__(self, other: object) -> bool:
        """Compare two list of tokens."""
        if not isinstance(other, TokenList):
            return NotImplemented

        return self.hash == other.hash

    def __hash__(self) -> int:
        """Return the hash of the `TokenList` instance."""
        return hash(self.hash)

    @property
    def hash(self) -> str:
        """Return the hash of the `TokenList` instance."""
        return "".join(t.hash for t in self.tokens if not t.ignore)

    @property
    def ignore(self) -> bool:
        """Return whether the token list should be ignored."""
        return self.is_comment

    @property
    def is_comment(self) -> bool:
        """Return whether the token list is a comment."""
        return isinstance(self.token_list, sqlparse.sql.Comment)

    @property
    def tokens(self) -> Generator[Token | TokenList, None, None]:
        """Yield relevant tokens in a deterministic order."""
        for token in self.token_list.tokens:
            if token.is_group:
                if UnorderedTokenList.is_unordered(token, self.statement_type):
                    yield UnorderedTokenList(token, parent=self)
                else:
                    yield TokenList(token, parent=self)
            else:
                yield Token(token)

    @property
    def statement_type(self) -> str:
        """Return the type of SQL statement."""
        if self.parent:
            return self.parent.statement_type

        return Statement.UNKNOWN_TYPE

    @property
    def str_tokens(self) -> list[str]:
        """Return the reconstructed SQL statement from tokens as a list of strings."""
        return [t.hash for t in self.tokens if not t.ignore]


class Statement(TokenList):
    """SQL statement."""

    UNKNOWN_TYPE = "UNKNOWN"

    @property
    def statement_type(self) -> str:
        """Return the type of SQL statement."""
        keywords: list[str] = [
            t.normalized for t in self.token_list.tokens if t.is_keyword
        ]

        # No keywords found
        if not keywords:
            return self.UNKNOWN_TYPE

        # Need 2 keywords to determine the statement type (e.g.: CREATE TABLE)
        if keywords[0] in {"CREATE", "ALTER", "DROP"}:
            return " ".join(keywords[:2])

        # Only one keyword (e.g.: SELECT, INSERT, DELETE, etc.)
        return keywords[0]

    @property
    def str_tokens(self) -> list[str]:
        """Return the reconstructed SQL statement from tokens as a list of strings."""
        return [t for token in self.tokens for t in token.str_tokens]


class UnorderedTokenList(TokenList):
    """Unordered token list."""

    STATEMENT_TYPES: typing.ClassVar[tuple[str, ...]] = ("CREATE TABLE", "CREATE TYPE")

    @staticmethod
    def is_unordered(token_list: sqlparse.sql.TokenList, statement_type: str) -> bool:
        """Return whether the token list order is important or not."""
        return (
            isinstance(token_list, sqlparse.sql.Parenthesis)
            and statement_type in UnorderedTokenList.STATEMENT_TYPES
        )

    @property
    def tokens(self) -> Generator[Token | TokenList, None, None]:
        """Yield relevant tokens in a deterministic order."""
        filtered_tokens = [t for t in self.flatten_tokens if not t.ignore]

        # Split punctuations and identifiers (columns, types, etc.)
        split_result = self._split_identifiers(filtered_tokens)

        # Tokens are "()", no need to sort them
        if not split_result.identifier_groups and not split_result.separators:
            yield from filtered_tokens

        # Sort identifier groups by their hash
        split_result.identifier_groups.sort(key=lambda g: "".join(t.hash for t in g))
        # Join back the tokens in the expected order
        sorted_tokens = self._join_identifiers(split_result)

        yield from sorted_tokens

    @property
    def flatten_tokens(self) -> Generator[Token, None, None]:
        """Yield all tokens in the token tree."""
        yield from (Token(t) for t in self.token_list.flatten())

    @staticmethod
    def _split_identifiers(tokens: list[Token]) -> SplitIdentifierResult:
        """Split tokens into identifier groups.

        Example:
        -------
        >>> tokens = ["(", "id", "INT", ",", "name", "TEXT", ")"]
        >>> self._split_identifiers(tokens)
        SplitIdentifierResult(
            opening_parenthesis="(",
            identifier_groups=[
                ["id", "INT"],
                ["name", "TEXT"],
            ],
            separators=[","],
            closing_parenthesis=")",
        )

        """
        opening_parenthesis, closing_parenthesis = tokens.pop(0), tokens.pop(-1)

        # No identifier groups
        if not tokens:
            return SplitIdentifierResult(
                opening_parenthesis,
                [],
                [],
                closing_parenthesis,
            )

        separators: list[Token] = []
        identifier_groups: list[list[Token]] = []
        last_identifier_group: list[Token] = []

        for token in tokens:
            if token.is_separator:
                separators.append(token)
                if last_identifier_group:
                    identifier_groups.append(last_identifier_group.copy())
                    last_identifier_group.clear()
            else:
                last_identifier_group.append(token)

        if last_identifier_group:
            identifier_groups.append(last_identifier_group.copy())

        # We expect to have one less separator than identifier groups
        # e.g.: (id INT, name TEXT)
        #              ^
        if len(separators) != len(identifier_groups) - 1:
            error_message = f"Unbalanced separators ({separators}) and identifier groups ({identifier_groups})"
            raise RuntimeError(error_message)

        return SplitIdentifierResult(
            opening_parenthesis,
            identifier_groups,
            separators,
            closing_parenthesis,
        )

    @staticmethod
    def _join_identifiers(split_result: SplitIdentifierResult) -> list[Token]:
        """Join identifier groups back into a list of tokens.

        Example:
        -------
        >>> split_result = SplitIdentifierResult(
            opening_parenthesis="(",
            identifier_groups=[
                ["id", "INT"],
                ["name", "TEXT"],
            ],
            separators=[","],
            closing_parenthesis=")",
        )
        >>> self._join_identifiers(split_result)
        ["(", "id", "INT", ",", "name", "TEXT", ")"]

        """
        tokens = [split_result.opening_parenthesis]

        for group, separator in itertools.zip_longest(
            split_result.identifier_groups,
            split_result.separators,
        ):
            tokens.extend(group)
            if separator:
                tokens.append(separator)

        return tokens


class SplitIdentifierResult(typing.NamedTuple):
    """Result of the `UnorderedTokenList._split_identifiers` method."""

    opening_parenthesis: Token
    identifier_groups: list[list[Token]]
    separators: list[Token]
    closing_parenthesis: Token
