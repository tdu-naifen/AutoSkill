"""Tests for skill_pipeline.embedder (require model download)."""

import numpy as np
import pytest


@pytest.mark.slow
def test_embed_text_shape():
    from skill_pipeline.embedder import embed_text
    vec = embed_text("hello world")
    assert vec.shape == (384,)
    assert vec.dtype == np.float32


@pytest.mark.slow
def test_embed_texts_shape():
    from skill_pipeline.embedder import embed_texts
    vecs = embed_texts(["hello", "world", "foo"])
    assert vecs.shape == (3, 384)


@pytest.mark.slow
def test_embeddings_normalized():
    from skill_pipeline.embedder import embed_text
    vec = embed_text("some text for normalization check")
    norm = np.linalg.norm(vec)
    assert abs(norm - 1.0) < 1e-3


@pytest.mark.slow
def test_get_model_caching():
    from skill_pipeline.embedder import get_model
    m1 = get_model()
    m2 = get_model()
    assert m1 is m2
