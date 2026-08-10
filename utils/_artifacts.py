"""PROPOSITO: Persistencia atomica de artefatos do pipeline
SPEC: S2, S3, S4, S5, S7
ROADMAP: 3.1-3.4 — Infra compartilhada para todas as fases.
R49 idempotente, escrita atomica (tempfile + os.rename), path ancorado em ROOT.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

# Root do app cTrader (ancora para paths relativos)
_APP_ROOT = Path(__file__).resolve().parent.parent


def artifact_path(name: str) -> Path:
    """Retorna path absoluto para artefato, ancorado no ROOT do app."""
    return _APP_ROOT / "status" / name


def write_atomic(data: dict[str, Any] | list[Any], name: str) -> Path:
    """Escrita atomica: tempfile + os.rename. Nao corrompe em crash."""
    target = artifact_path(name)
    target.parent.mkdir(parents=True, exist_ok=True)
    # R49: le estado atual antes de escrever
    # existing = read_json(name) if target.exists() else None  # R49: leitura pre-escrita (reservado)
    # Escrita atomica
    fd, tmp_path = tempfile.mkstemp(suffix=".json", dir=str(target.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str, ensure_ascii=True)
        os.replace(tmp_path, target)  # atomico no mesmo filesystem
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise
    return target


def read_json(name: str) -> dict[str, Any] | list[Any] | None:
    """Le artefato JSON. Retorna None se nao existir."""
    target = artifact_path(name)
    if not target.exists():
        return None
    with open(target, encoding="utf-8") as f:
        return json.load(f)


# -- Artefatos do pipeline (nomes canonicos) --

def save_df_master(df: pd.DataFrame) -> Path:
    """3.1: Persiste df_master.parquet."""
    target = _APP_ROOT / "data" / "df_master.parquet"
    target.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(target, index=False)
    return target


def save_scores_raw(scores: dict[str, Any]) -> Path:
    """3.2: Persiste scores_raw.json (F1 output)."""
    return write_atomic(scores, "scores_raw.json")


def save_fusion_output(fusion: dict[str, Any]) -> Path:
    """3.3: Persiste fusion_output.json (F2 output)."""
    return write_atomic(fusion, "fusion_output.json")


def save_verdict(verdict: dict[str, Any]) -> Path:
    """3.3: Persiste verdict.json (F3 output)."""
    return write_atomic(verdict, "verdict.json")


def save_custom_rules(rules: dict[str, Any]) -> Path:
    """3.4: Persiste custom_rules.json (F5 output)."""
    return write_atomic(rules, "custom_rules.json")
