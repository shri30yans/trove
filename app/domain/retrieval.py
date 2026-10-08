"""Retrieval vocabularies: similarity thresholds and paging limits.

Every value here is transcribed from a query in app/routes/search.py or app/vector_search.py.
tests/test_domain_retrieval.py asserts the SQL literals still equal these constants, so a
threshold cannot be changed in one place without the other failing.
"""

from __future__ import annotations

from enum import StrEnum

SEARCH_DEFAULT_LIMIT = 20
SEARCH_MIN_LIMIT = 1
SEARCH_MAX_LIMIT = 50
LIST_DEFAULT_LIMIT = 30
LIST_MIN_LIMIT = 1
LIST_MAX_LIMIT = 100

HNSW_EF_SEARCH = 120
HNSW_ITERATIVE_SCAN = "strict_order"
CANDIDATE_MULTIPLIER = 8
CANDIDATE_MIN = 80
CANDIDATE_MAX = 500

RELATED_CANDIDATE_LIMIT = 48
RELATED_MIN_SIMILARITY = 0.62
STRONG_RELATION_SIMILARITY = 0.82
RELATED_PAGE_SIZE = 12

RESURFACING_POOL = 500
RESURFACING_PER_MEMORY = 16
RESURFACING_MIN_SIMILARITY = 0.68
# One window answers both "old enough to resurface" and "recent enough to be the anchor".
RESURFACING_WINDOW_DAYS = 30
RESURFACING_REOPEN_DAYS = 21
RESURFACING_PAGE_SIZE = 8


class MatchType(StrEnum):
    """How a search hit was found; reported to the client as matchType."""

    TEXT = "text"
    MEANING = "meaning"
    TEXT_AND_MEANING = "text_and_meaning"


class RelationKind(StrEnum):
    """The strength label on a related Memory."""

    SIMILAR_IDEA = "similar_idea"
    SAME_TOPIC = "same_topic"


def parse_limit(raw: str | None, *, default: int, minimum: int, maximum: int) -> int:
    """Clamp a client-supplied limit; an unparseable value falls back to the default."""
    if raw is None or raw.strip() == "":
        return default
    try:
        requested = int(raw)
    except ValueError:
        return default
    return min(maximum, max(minimum, requested))


def candidate_limit_for(limit: int) -> int:
    """How many raw vector rows to fetch before collapsing asset hits onto their memory."""
    return min(CANDIDATE_MAX, max(CANDIDATE_MIN, limit * CANDIDATE_MULTIPLIER))


def match_type(lexical: float, semantic: float) -> MatchType:
    if lexical > 0 and semantic > 0:
        return MatchType.TEXT_AND_MEANING
    return MatchType.MEANING if semantic > 0 else MatchType.TEXT


def relation_for(similarity: float) -> tuple[RelationKind, str]:
    """Label and client-facing reason for one related Memory, decided by one comparison."""
    if similarity > STRONG_RELATION_SIMILARITY:
        return RelationKind.SIMILAR_IDEA, "Similar meaning or image"
    return RelationKind.SAME_TOPIC, "Shared topic or visual content"
