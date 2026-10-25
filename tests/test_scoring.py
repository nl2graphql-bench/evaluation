"""Tests for rgeval.score_pair.

These also pin the graphql-core upper bound: from 3.3 a node's `directives` is
None when absent where 3.2 returned [], and pipeline/normalizeAST.py iterates it
directly. With graphql-core 3.3 installed, every case below returns False,
including a query compared against itself.
"""
import pytest

from rgeval import score_pair

SCHEMA = """
type Query { city(id: Int!): City }
type City { id: Int! name: String population: Float }
"""
GOLD = "query { city(id: 1) { name population } }"


def test_identical_query_scores():
    assert score_pair(SCHEMA, GOLD, GOLD) is True


def test_field_order_does_not_matter():
    assert score_pair(SCHEMA, GOLD, "query { city(id: 1) { population name } }") is True


def test_alias_does_not_matter():
    assert score_pair(SCHEMA, GOLD, "query { city(id: 1) { n: name population } }") is True


def test_different_argument_does_not_score():
    assert score_pair(SCHEMA, GOLD, "query { city(id: 2) { name population } }") is False


def test_missing_field_does_not_score():
    assert score_pair(SCHEMA, GOLD, "query { city(id: 1) { name } }") is False


def test_unparseable_prediction_returns_false_not_raises():
    assert score_pair(SCHEMA, GOLD, "not a query at all {{{") is False


def test_field_absent_from_schema_does_not_score():
    assert score_pair(SCHEMA, GOLD, "query { city(id: 1) { nope } }") is False


def test_empty_prediction_does_not_score():
    assert score_pair(SCHEMA, GOLD, "") is False


@pytest.mark.parametrize("fenced", [
    "```graphql\nquery { city(id: 1) { name population } }\n```",
    "```\nquery { city(id: 1) { name population } }\n```",
])
def test_strip_markdown_removes_fences(fenced):
    from rgeval.scoring import strip_markdown
    assert strip_markdown(fenced) == GOLD.strip()
