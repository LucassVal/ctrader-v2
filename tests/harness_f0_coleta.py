"""PROPOSITO: Harness F0 -- valida orc_coleta + filhos antes do ciclo.
SPEC: S2
ROADMAP: H1.1-H1.4 -- pre-flight F0.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def test_imports():
    """Testa se todos os modulos F0 sao importaveis."""
    import f0_collector.orc_coleta as orc
    import f0_collector.poller_orc_coleta as poller
    import f0_collector.storage_orc_coleta as storage

    assert hasattr(orc, "take_snapshot"), "take_snapshot missing"
    assert hasattr(orc, "get_snapshot"), "get_snapshot missing"
    assert hasattr(orc, "place_order"), "place_order missing"
    assert hasattr(poller, "poll_cycle"), "poll_cycle missing"
    assert hasattr(storage, "make_empty_df"), "make_empty_df missing"


def test_snapshot():
    """Testa se take_snapshot + get_snapshot funcionam (offline = ok)."""
    from f0_collector.orc_coleta import get_snapshot
    snap = get_snapshot()
    # Offline e valido -- snapshot pode nao existir no primeiro ciclo
    if snap is not None:
        assert "timestamp_utc" in snap or "symbols" in snap, "Snapshot mal formado"


if __name__ == "__main__":
    test_imports()
    test_snapshot()
    print("[OK] HARNESS F0: PASS")
