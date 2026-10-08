"""Retrieval constants must own the numbers the queries use, and the queries must still use them."""

from __future__ import annotations

import pathlib
import re

import pytest

from app.domain.retrieval import (
    CANDIDATE_MAX,
    CANDIDATE_MIN,
    RELATED_CANDIDATE_LIMIT,
    RELATED_MIN_SIMILARITY,
    RELATED_PAGE_SIZE,
    RESURFACING_MIN_SIMILARITY,
    RESURFACING_PAGE_SIZE,
    STRONG_RELATION_SIMILARITY,
    MatchType,
    RelationKind,
    candidate_limit_for,
    match_type,
    parse_limit,
    relation_for,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
APP_ROOT = REPO_ROOT / "app"

# The literals that used to be written into SQL by hand. Owned by app/domain/retrieval.py now.
RETIREMENT_CANDIDATES = {
    "0.62": "RELATED_MIN_SIMILARITY",
    "0.82": "STRONG_RELATION_SIMILARITY",
    "0.68": "RESURFACING_MIN_SIMILARITY",
    "hnsw.ef_search = ": "HNSW_EF_SEARCH",
}


def test_search_uses_unweighted_rank_aggregation() -> None:
    sql = (APP_ROOT / "routes" / "search.py").read_text(encoding="utf-8")
    assert "row_number() OVER (ORDER BY lexical_score DESC" in sql
    assert "row_number() OVER (ORDER BY semantic_score DESC" in sql
    assert "1.0 / lexical_rank" in sql
    assert "1.0 / semantic_rank" in sql
    assert "LEXICAL_WEIGHT" not in sql
    assert "SEMANTIC_WEIGHT" not in sql


def test_the_similarity_bands_are_ordered() -> None:
    assert RELATED_MIN_SIMILARITY < RESURFACING_MIN_SIMILARITY < STRONG_RELATION_SIMILARITY
    assert 0 < RELATED_MIN_SIMILARITY < 1


def test_the_retrieval_limits_are_wide_enough_to_rank() -> None:
    assert RELATED_CANDIDATE_LIMIT > RELATED_PAGE_SIZE
    assert CANDIDATE_MAX >= RELATED_CANDIDATE_LIMIT
    assert RESURFACING_PAGE_SIZE > 0


@pytest.mark.parametrize("value", ["5", " 5 ", "0", "-3", "9999", "abc", "", None, "3.5"])
def test_parse_limit_always_returns_a_usable_page_size(value: str | None) -> None:
    limit = parse_limit(value, default=20, minimum=1, maximum=50)
    assert 1 <= limit <= 50
    assert isinstance(limit, int)


def test_parse_limit_clamps_a_request_and_falls_back_on_junk() -> None:
    assert parse_limit("5", default=20, minimum=1, maximum=50) == 5
    assert parse_limit("0", default=20, minimum=1, maximum=50) == 1
    assert parse_limit("500", default=20, minimum=1, maximum=50) == 50
    assert parse_limit("abc", default=20, minimum=1, maximum=50) == 20
    assert parse_limit("", default=20, minimum=1, maximum=50) == 20
    assert parse_limit(None, default=20, minimum=1, maximum=50) == 20


@pytest.mark.parametrize("limit", [1, 8, 20, 50])
def test_the_vector_candidate_pool_scales_with_the_page_and_stays_bounded(limit: int) -> None:
    candidates = candidate_limit_for(limit)
    assert CANDIDATE_MIN <= candidates <= CANDIDATE_MAX
    assert candidates >= limit


def test_the_candidate_pool_grows_eightfold_until_it_hits_the_ceiling() -> None:
    assert candidate_limit_for(1) == CANDIDATE_MIN
    assert candidate_limit_for(20) == 20 * 8
    assert candidate_limit_for(50) == 400
    assert candidate_limit_for(80) == CANDIDATE_MAX


def test_match_type_reports_which_halves_of_the_blend_answered() -> None:
    assert match_type(1.2, 0.4) is MatchType.TEXT_AND_MEANING
    assert match_type(1.2, 0.0) is MatchType.TEXT
    assert match_type(0.0, 0.4) is MatchType.MEANING
    assert match_type(0.0, 0.0) is MatchType.TEXT


def test_a_weak_semantic_signal_still_counts_as_a_meaning_match() -> None:
    assert match_type(0.0, 1e-9) is MatchType.MEANING


@pytest.mark.parametrize("similarity", [0.62, 0.7, 0.82])
def test_a_shared_topic_below_the_boundary_is_labelled_as_such(similarity: float) -> None:
    relation, reason = relation_for(similarity)
    assert relation is RelationKind.SAME_TOPIC
    assert reason == "Shared topic or visual content"


def test_only_strong_similarity_is_called_a_similar_idea() -> None:
    relation, reason = relation_for(0.95)
    assert relation is RelationKind.SIMILAR_IDEA
    assert reason == "Similar meaning or image"


def test_the_relation_boundary_is_exclusive() -> None:
    assert relation_for(STRONG_RELATION_SIMILARITY)[0] is RelationKind.SAME_TOPIC
    assert relation_for(STRONG_RELATION_SIMILARITY + 0.001)[0] is RelationKind.SIMILAR_IDEA


@pytest.mark.parametrize(("literal", "owner"), sorted(RETIREMENT_CANDIDATES.items()))
def test_a_threshold_is_no_longer_written_into_python_or_sql(literal: str, owner: str) -> None:
    """A magic number that reappears in a query is a second owner of the same rule."""
    offenders = []
    for path in sorted(APP_ROOT.rglob("*.py")):
        if path.parent.name == "domain":
            continue
        text = path.read_text(encoding="utf-8")
        if re.search(rf"(?<![\w.]){re.escape(literal)}(?![\w.])", text):
            offenders.append(path.name)
    assert offenders == [], f"{literal} belongs to {owner}, found bare in {offenders}"
