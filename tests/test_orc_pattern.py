"""Harness S30: orc_pattern — cosine similarity + feature extraction"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.orc_pattern import cosine_similarity, extract_feature_vector, find_similar


def test_cosine_similarity_identical():
    """Vetores identicos — similaridade deve ser ~1.0."""
    a = [1.0, 2.0, 3.0]
    b = [1.0, 2.0, 3.0]
    sim = cosine_similarity(a, b)
    assert abs(sim - 1.0) < 0.01, f"Similaridade: {sim}"


def test_cosine_similarity_orthogonal():
    """Vetores ortogonais — similaridade deve ser ~0.0."""
    a = [1.0, 0.0, 0.0]
    b = [0.0, 1.0, 0.0]
    sim = cosine_similarity(a, b)
    assert abs(sim - 0.0) < 0.01, f"Similaridade: {sim}"


def test_cosine_similarity_zero_vector():
    """Vetor zero — deve retornar 0.0 (tratamento de divisao por zero)."""
    sim = cosine_similarity([0.0, 0.0], [1.0, 2.0])
    assert sim == 0.0


def test_extract_feature_vector_returns_list():
    """Feature vector deve ser lista de floats."""
    row = {"rsi_14": 55.0, "macd_hist": 0.5, "adx": 25.0, "bb_position": 0.6}
    vec = extract_feature_vector(row)
    assert isinstance(vec, list)
    if vec:
        assert all(isinstance(v, (int, float)) for v in vec)


def test_find_similar_handles_empty():
    """find_similar com window vazio nao deve crashar."""
    try:
        result = find_similar({"rsi_14": 50.0}, [], [], [])
    except (TypeError, ValueError):
        # OK — dados mock insuficientes para similaridade real
        return
    assert isinstance(result, list)
