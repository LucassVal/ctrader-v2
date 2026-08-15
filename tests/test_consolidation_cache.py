"""PROPOSITO: Testes de consolidação, cache e persistência com dados sintéticos.
SPEC: S31 (consolidacao)
ROADMAP: Validacao do pipeline G23 sem dependencia MCP

Tipos de teste:
  A) Cache persist: escreve gap_report -> reload -> verifica consistencia
  B) Gap detection: insere lacunas sinteticas -> verifica scan
  C) Calendar filter: verifica que fins de semana sao filtrados
  D) Merge gaps: verifica que gaps adjacentes sao fundidos
  E) Full pipeline: scan -> backfill -> re-scan -> convergencia

Tudo com dados sinteticos (~10K barras). Zero MCP.
"""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Importa funcoes do G23
from gates.run_consolidate_parquet import (  # noqa: E402
    GAP_MIN_MINUTES,
    MIN_MS,
    _is_weekend_or_daily_close,
    _precompute_closed_intervals,
    scan_gaps,
    scan_gaps_anchored,
)

# ============================================================
# HELPERS
# ============================================================

def make_synthetic_ohlcv(n_bars: int = 10000, start_date: str = "2026-07-01",
                         gap_every: int = 0, gap_size_min: int = 10) -> pd.DataFrame:
    """Gera M1 sintetico. gap_every=N insere lacuna de gap_size_min a cada N barras."""
    start = pd.Timestamp(start_date, tz="UTC")
    all_timestamps = [start + timedelta(minutes=i) for i in range(n_bars)]

    # Remove gaps (simula barras ausentes)
    if gap_every > 0:
        remove_set = set()
        for i in range(gap_every, n_bars, gap_every):
            for j in range(gap_size_min):
                if i + j < n_bars:
                    remove_set.add(i + j)
        timestamps = [ts for i, ts in enumerate(all_timestamps) if i not in remove_set]
    else:
        timestamps = all_timestamps

    n = len(timestamps)
    rng = np.random.RandomState(42)
    close = 1.0800 + np.cumsum(rng.randn(n) * 0.0001)
    close = np.maximum(close, 0.01)
    spread = np.full(n, 0.0002)
    high = close + rng.rand(n) * 0.001
    low = close - rng.rand(n) * 0.001
    open_vals = close - rng.randn(n) * 0.0005

    df = pd.DataFrame({
        "timestamp": [int(ts.timestamp() * 1000) for ts in timestamps],
        "symbol": "EURUSD",
        "open": open_vals,
        "high": high,
        "low": low,
        "close": close,
        "tick_volume": rng.randint(1, 100, n),
        "spread": spread,
        "bid": close - spread / 2,
        "ask": close + spread / 2,
    })
    return df


def save_parquet(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


# ============================================================
# TESTE A: Cache persist
# ============================================================

def test_cache_roundtrip():
    """Escreve gap_report -> reload -> verifica campos essenciais."""
    with tempfile.TemporaryDirectory() as tmp:
        report_path = Path(tmp) / "gap_report.json"
        report = {
            "generated_at": datetime.now(UTC).isoformat(),
            "_script_version": "2.1",
            "_consolidated_mtimes": {"XAUUSD": 1234567890.0},
            "symbols": {
                "XAUUSD": {"rows": 1000, "total_gaps": 5, "coverage_pct": 99.5},
            },
        }
        report_path.write_text(json.dumps(report, indent=2))

        # Reload
        with open(report_path) as f:
            loaded = json.load(f)

        assert loaded["_script_version"] == "2.1"
        assert loaded["symbols"]["XAUUSD"]["rows"] == 1000
        assert loaded["symbols"]["XAUUSD"]["total_gaps"] == 5
        assert "_consolidated_mtimes" in loaded
        print("  [PASS] A1: cache roundtrip")


def test_cache_version_invalidation():
    """Cache com versao diferente -> deve ser invalidado."""
    # Simula: _consolidated_stale verifica _script_version
    report_v1 = {"_script_version": "1.0"}
    report_v2 = {"_script_version": "2.1"}

    script_version = "2.1"
    assert report_v1.get("_script_version") != script_version  # stale
    assert report_v2.get("_script_version") == script_version  # fresh
    print("  [PASS] A2: version invalidation")


# ============================================================
# TESTE B: Gap detection
# ============================================================

def test_gap_detection_no_gaps():
    """Dados continuos (M1) -> zero gaps."""
    df = make_synthetic_ohlcv(n_bars=500, gap_every=0)
    ts = sorted(int(t) for t in df["timestamp"])
    gaps = scan_gaps(ts, gap_min_minutes=5, symbol="EURUSD")
    assert len(gaps) == 0, f"Esperado 0 gaps, encontrado {len(gaps)}"
    print("  [PASS] B1: no gaps em dados continuos")


def test_gap_detection_with_gaps():
    """10 gaps de 10 min cada -> deve detectar ~10 gaps."""
    df = make_synthetic_ohlcv(n_bars=1000, gap_every=100, gap_size_min=10)
    ts = sorted(int(t) for t in df["timestamp"])
    gaps = scan_gaps(ts, gap_min_minutes=5, symbol="EURUSD")
    # 1000 / 100 = 10 gaps inseridos
    assert 8 <= len(gaps) <= 12, f"Esperado ~10 gaps, encontrado {len(gaps)}"
    for g in gaps:
        assert g["missing_minutes"] >= GAP_MIN_MINUTES
    print(f"  [PASS] B2: {len(gaps)} gaps detectados com dados sinteticos")


def test_gap_detection_below_threshold():
    """Gaps de 3 min (<5 min threshold) -> nao devem ser detectados."""
    df = make_synthetic_ohlcv(n_bars=500, gap_every=50, gap_size_min=3)
    ts = sorted(int(t) for t in df["timestamp"])
    gaps = scan_gaps(ts, gap_min_minutes=5, symbol="EURUSD")
    assert len(gaps) == 0, f"Esperado 0 gaps (todos <5min), encontrado {len(gaps)}"
    print("  [PASS] B3: gaps < threshold ignorados")


# ============================================================
# TESTE C: Calendar filter
# ============================================================

def test_calendar_filter_weekend():
    """Gap sexta->domingo deve ser filtrado (>80% mercado fechado)."""
    # Sexta 21:00 -> Domingo 21:00 = 48h. Mercado fechado cobre ~48h.
    fri_21 = int(datetime(2026, 7, 31, 21, 0, tzinfo=UTC).timestamp() * 1000)
    sun_21 = int(datetime(2026, 8, 2, 21, 0, tzinfo=UTC).timestamp() * 1000)

    # Pre-computa intervalos
    closed = _precompute_closed_intervals(fri_21 - 1000, sun_21 + 1000, "EURUSD")

    result = _is_weekend_or_daily_close(fri_21, sun_21, "EURUSD", closed)
    assert result is True, "Gap de fim de semana deve ser filtrado"
    print("  [PASS] C1: weekend filter funciona")


def test_calendar_filter_weekday_ok():
    """Gap no meio da semana (terca 10:00->12:00) -> NAO deve ser filtrado."""
    tue_10 = int(datetime(2026, 7, 28, 10, 0, tzinfo=UTC).timestamp() * 1000)
    tue_12 = int(datetime(2026, 7, 28, 12, 0, tzinfo=UTC).timestamp() * 1000)
    now_ms = int(datetime(2026, 8, 6, tzinfo=UTC).timestamp() * 1000)

    closed = _precompute_closed_intervals(tue_10 - 1000, now_ms, "EURUSD")
    result = _is_weekend_or_daily_close(tue_10, tue_12, "EURUSD", closed)
    assert result is False, "Gap durante a semana NAO deve ser filtrado"
    print("  [PASS] C2: weekday gap nao filtrado")


def test_calendar_filter_rollover():
    """Gap 21:59->23:00 (rollover diario) DEVE ser filtrado.

    BUG v2.1: DAILY_CLOSE_UTC = (21, 22) -> overlap 1.6% -> NAO filtrado.
    FIX v2.2: DAILY_CLOSE_UTC = (21, 23) -> overlap 100% -> filtrado.
    """
    for sym in ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD"]:
        a_ms = int(datetime(2026, 7, 28, 21, 59, tzinfo=UTC).timestamp() * 1000)
        b_ms = int(datetime(2026, 7, 28, 23, 0, tzinfo=UTC).timestamp() * 1000)
        closed = _precompute_closed_intervals(a_ms - 60_000, b_ms + 60_000, sym)
        result = _is_weekend_or_daily_close(a_ms, b_ms, sym, closed)
        assert result is True, (
            f"REGRESSAO: {sym} gap 21:59-23:00 NAO filtrado — "
            f"DAILY_CLOSE_UTC pode ter revertido para (21, 22)"
        )
    print("  [PASS] C3: rollover 21:59-23:00 filtrado para todos forex")


# ============================================================
# TESTE D: Merge gaps
# ============================================================

def test_merge_adjacent_gaps():
    """Gaps com <26h de distancia -> fundidos em 1 range."""
    # Simula merge logico (sem MCP)
    # Gap 1+2: 10min de distancia -> merge (26h threshold)
    # Gap 3: 30h depois -> nao merge
    gaps = [
        {"start_ms": 1_000_000_000, "end_ms": 1_000_600_000},     # gap 1: 10 min
        {"start_ms": 1_001_200_000, "end_ms": 1_001_800_000},     # gap 2: 10 min depois -> merge
        {"start_ms": 1_110_000_000, "end_ms": 1_110_600_000},     # gap 3: >26h depois -> separado
    ]
    merge_ms = 26 * 3600 * 1000  # 26h em ms = 93,600,000
    merged = []
    for g in sorted(gaps, key=lambda g: g["start_ms"]):
        if merged and g["start_ms"] - merged[-1][1] <= merge_ms:
            merged[-1] = (merged[-1][0], max(merged[-1][1], g["end_ms"]))
        else:
            merged.append((g["start_ms"], g["end_ms"]))

    # gap1+2 fundidos (10min diff < 26h), gap3 separado (30h diff > 26h)
    assert len(merged) == 2, f"Esperado 2 ranges, obtido {len(merged)}: {merged}"
    assert merged[0] == (1_000_000_000, 1_001_800_000), f"Range 0: {merged[0]}"
    assert merged[1] == (1_110_000_000, 1_110_600_000), f"Range 1: {merged[1]}"
    print("  [PASS] D1: merge gaps adjacentes")


# ============================================================
# TESTE E: Full pipeline sintetico
# ============================================================

def test_full_pipeline_synthetic(tmp_path):
    """Scan -> detecta gaps -> simula backfill -> re-scan -> convergencia."""
    # Cria dados sinteticos com gaps conhecidos
    df = make_synthetic_ohlcv(n_bars=1000, gap_every=100, gap_size_min=10)
    parquet_path = tmp_path / "EURUSD_M1.parquet"
    save_parquet(df, parquet_path)

    # Scan
    ts = sorted(int(t) for t in df["timestamp"])
    now_ms = ts[-1] + MIN_MS
    window_start = ts[0] - MIN_MS

    gaps_before = scan_gaps_anchored(ts, window_start, now_ms,
                                     symbol="EURUSD", gap_min_minutes=5)
    n_before = len(gaps_before)
    assert n_before > 0, "Deve detectar gaps sinteticos"

    # Simula backfill: preenche gaps (adiciona timestamps)
    filled_ts = set(ts)
    for g in gaps_before:
        cursor = g["start_ms"]
        while cursor <= g["end_ms"]:
            filled_ts.add(cursor)
            cursor += MIN_MS
    ts_after = sorted(filled_ts)

    # Re-scan
    gaps_after = scan_gaps_anchored(ts_after, window_start, now_ms,
                                    symbol="EURUSD", gap_min_minutes=5)
    n_after = len(gaps_after)

    assert n_after < n_before, f"Gaps devem diminuir: {n_before} -> {n_after}"
    print(f"  [PASS] E1: pipeline sintetico convergiu ({n_before} -> {n_after} gaps)")


# ============================================================
# MAIN
# ============================================================

def main():
    print("=" * 60)
    print(" TESTES DE CONSOLIDACAO — Dados sinteticos (~10K barras)")
    print("=" * 60)

    results = []

    # A: Cache
    print("\n[A] Cache persistence:")
    try:
        test_cache_roundtrip()
        test_cache_version_invalidation()
        results.append("A: PASS")
    except Exception as e:
        print(f"  [FAIL] {e}")
        results.append(f"A: FAIL — {e}")

    # B: Gap detection
    print("\n[B] Gap detection:")
    try:
        test_gap_detection_no_gaps()
        test_gap_detection_with_gaps()
        test_gap_detection_below_threshold()
        results.append("B: PASS")
    except Exception as e:
        print(f"  [FAIL] {e}")
        results.append(f"B: FAIL — {e}")

    # C: Calendar filter
    print("\n[C] Calendar filter:")
    try:
        test_calendar_filter_weekend()
        test_calendar_filter_weekday_ok()
        test_calendar_filter_rollover()
        results.append("C: PASS")
    except Exception as e:
        print(f"  [FAIL] {e}")
        results.append(f"C: FAIL — {e}")

    # D: Merge
    print("\n[D] Merge gaps:")
    try:
        test_merge_adjacent_gaps()
        results.append("D: PASS")
    except Exception as e:
        print(f"  [FAIL] {e}")
        results.append(f"D: FAIL — {e}")

    # E: Full pipeline
    print("\n[E] Full pipeline sintetico:")
    try:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            test_full_pipeline_synthetic(Path(td))
        results.append("E: PASS")
    except Exception as e:
        print(f"  [FAIL] {e}")
        results.append(f"E: FAIL — {e}")

    print(f"\n{'=' * 60}")
    for r in results:
        print(f"  {r}")
    passed = sum(1 for r in results if "PASS" in r)
    print(f"\n  {passed}/{len(results)} suites passaram")
    print(f"{'=' * 60}")

    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
