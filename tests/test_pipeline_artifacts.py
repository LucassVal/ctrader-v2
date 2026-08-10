"""PROPOSITO: H3.1 — Harness persistencia de artefatos do pipeline
SPEC: S2, S3, S4, S5, S7
ROADMAP: 3.1-3.4 — Escrita atomica, R49 idempotente, path ancorado.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils._artifacts import (
    artifact_path,
    read_json,
    save_custom_rules,
    save_fusion_output,
    save_scores_raw,
    save_verdict,
    write_atomic,
)


def test_write_atomic_creates_file() -> None:
    """write_atomic cria arquivo JSON valido."""
    data = {"test": "hello", "n": 42}
    path = save_scores_raw(data)
    assert path.exists(), f"Arquivo nao criado: {path}"
    content = json.loads(path.read_text())
    assert content == data


def test_read_json_roundtrip() -> None:
    """read_json le o que write_atomic escreveu."""
    data = {"scores": {"macro": 75.0, "vol": 60.0}}
    write_atomic(data, "test_roundtrip.json")
    result = read_json("test_roundtrip.json")
    assert result == data


def test_write_atomic_overwrites() -> None:
    """write_atomic sobrescreve sem duplicar (R49)."""
    data1 = {"v": 1}
    data2 = {"v": 2}
    save_scores_raw(data1)
    save_scores_raw(data2)
    result = read_json("scores_raw.json")
    assert result == data2, f"Esperado {data2}, obtido {result}"


def test_artifact_path_ancorado() -> None:
    """artifact_path retorna path dentro de status/."""
    p = artifact_path("test.json")
    assert "status" in str(p), f"Path nao ancorado em status/: {p}"


def test_all_artifact_functions() -> None:
    """Todas as funcoes de save produzem arquivos validos."""
    for fn, data in [
        (save_fusion_output, {"fusion_score": 85, "components": {}}),
        (save_verdict, {"approved": True, "score": 88}),
        (save_custom_rules, {"weights": {"macro": 0.3, "tec": 0.5}}),
    ]:
        path = fn(data)
        assert path.exists(), f"{fn.__name__} nao criou arquivo"
        assert json.loads(path.read_text()) == data
