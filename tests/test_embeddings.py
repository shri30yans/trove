"""Gemini embedding response validation and pgvector serialization."""

import math

import pytest

from app.embedding import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_SPACE_ID,
    MAX_IMAGE_BYTES,
    MAX_TEXT_CHARS,
    MODEL_ID,
    MODEL_REVISION,
    MODELS,
    Embedding,
    PermanentEmbeddingError,
    _validated,
    vector_literal,
)


def _vector(value: float = 1.0, dimensions: int = EMBEDDING_DIMENSIONS) -> list[float]:
    return [value] * dimensions


def test_a_returning_vector_is_normalized_to_unit_length() -> None:
    normalized = _validated(_vector(2.0))
    assert len(normalized) == EMBEDDING_DIMENSIONS
    assert math.sqrt(sum(value * value for value in normalized)) == pytest.approx(1.0, abs=1e-6)
    assert normalized[0] == pytest.approx(1 / math.sqrt(EMBEDDING_DIMENSIONS), abs=1e-6)


@pytest.mark.parametrize("dimensions", [1, 256, 767, 769, 1536, 3072])
def test_a_vector_of_the_wrong_width_is_rejected(dimensions: int) -> None:
    with pytest.raises(PermanentEmbeddingError, match="768-dimensional"):
        _validated(_vector(dimensions=dimensions))


@pytest.mark.parametrize("poison", [math.nan, math.inf, -math.inf])
def test_a_non_finite_embedding_is_rejected(poison: float) -> None:
    broken = _vector()
    broken[7] = poison
    with pytest.raises(PermanentEmbeddingError, match="finite"):
        _validated(broken)


def test_a_zero_vector_cannot_be_normalized() -> None:
    with pytest.raises(PermanentEmbeddingError, match="zero vector"):
        _validated(_vector(0.0))


def test_the_embedding_space_pins_the_provider_model_and_dimension() -> None:
    assert MODEL_ID == "google/gemini-embedding-2"
    assert MODEL_REVISION == "provider-managed"
    assert EMBEDDING_SPACE_ID == "google/gemini-embedding-2-768d@provider-managed"
    assert MODELS.space_id == EMBEDDING_SPACE_ID
    assert MODELS.text_model == MODELS.image_model == MODEL_ID
    assert MODELS.text_revision == MODELS.image_revision == MODEL_REVISION


def test_input_budgets_remain_bounded() -> None:
    assert MAX_IMAGE_BYTES == 52_428_800
    assert MAX_TEXT_CHARS == 24_000


def test_vector_literal_is_pgvector_text_without_a_registered_codec() -> None:
    embedding = Embedding(
        modality="text",
        space_id=EMBEDDING_SPACE_ID,
        model_id=MODEL_ID,
        model_revision=MODEL_REVISION,
        vector=[0.0, 0.5, -0.25] + [0.0] * (EMBEDDING_DIMENSIONS - 3),
    )
    literal = vector_literal(embedding)
    assert literal.startswith("[0.0,0.5,-0.25,")
    assert literal.endswith("]")
    assert len(literal[1:-1].split(",")) == EMBEDDING_DIMENSIONS
    assert "e-" not in literal.lower().replace("-0.25", ""), "no scientific notation in a vector literal"


def test_vector_literal_round_trips_through_the_text_protocol() -> None:
    values = [1 / 3, -2.5, 0.0, 7.125]
    embedding = Embedding(
        "text", MODELS.space_id, MODEL_ID, MODEL_REVISION, values + [0.0] * (EMBEDDING_DIMENSIONS - 4)
    )
    parsed = [float(item) for item in vector_literal(embedding)[1:-1].split(",")]
    assert parsed[:4] == values[:4]
