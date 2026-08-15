"""PROPOSITO: Gate de regressao — engessa DAILY_CLOSE_UTC e filtros de calendario.
SPEC: S31
ROADMAP: S31 / G23 v2.2

CONTEXTO DO BUG (2026-08-14):
  DAILY_CLOSE_UTC definia (21, 22) para forex majors. O mercado real fecha
  de ~21:59 a ~23:00 UTC (rollover). O filtro calculava 1.6% overlap e NAO
  filtrava esses gaps, causando loop infinito de backfill.

  FIX: expandir para (21, 23). Este gate IMPEDE que alguem reverta.

CENARIOS:
  F1: DAILY_CLOSE_UTC deve cobrir rollover inteiro (21-23h)
  F2: Filtro de calendario deve aceitar gap 21:59-23:00 como fechamento
  F3: Filtro de calendario NAO deve aceitar gap 10:00-12:00 (pregao)
  F4: Feriados devem ser reconhecidos como fechamento
  F5: Gap genuino durante pregao NAO e filtrado
  F6: SCRIPT_VERSION >= 2.2 (cache invalidado)
  F7: scan_gaps_anchored com rollover = 0 gaps
"""
from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from gates.run_consolidate_parquet import (  # noqa: E402
    DAILY_CLOSE_UTC,
    FOREX_HOLIDAYS_FIXED,
    GAP_MIN_MINUTES_INDEX,
    SCRIPT_VERSION,
    _is_weekend_or_daily_close,
    _precompute_closed_intervals,
    scan_gaps_anchored,
)

# TODOS os 7 simbolos devem ter entrada em DAILY_CLOSE_UTC
REQUIRED_SYMBOLS = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "DXYUSD", "VIXUSD"]
FOREX_SYMBOLS = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD"]
INDEX_SYMBOLS = ["DXYUSD", "VIXUSD"]


def test_f1_daily_close_covers_rollover():
    """Todos os 7 simbolos devem ter entrada em DAILY_CLOSE_UTC com cobertura adequada."""
    for sym in REQUIRED_SYMBOLS:
        assert sym in DAILY_CLOSE_UTC, (
            f"[GATE-FAIL] {sym} AUSENTE em DAILY_CLOSE_UTC — "
            f"adicionar entrada para evitar gaps fantasma"
        )
        h1, h2 = DAILY_CLOSE_UTC[sym]
        # Forex majors: h2 >= 23 (mesmo dia)
        # Indices: h2 < h1 (dia seguinte, ex: 20->1 = 5h de janela)
        if sym in FOREX_SYMBOLS:
            assert h2 >= 23, (
                f"[GATE-FAIL] {sym}: DAILY_CLOSE_UTC = ({h1}, {h2}) — "
                f"h2 deve ser >= 23 para forex. NUNCA reverter."
            )
        else:
            # Indices: h2 < h1 e valido (wrap-around)
            assert h1 <= 21, (
                f"[GATE-FAIL] {sym}: h1={h1} > 21 — inicio deve ser <= 21h"
            )
            # Cobertura minima: deve cobrir pelo menos 3h de rollover
            if h2 < h1:
                coverage_h = (24 - h1) + h2  # wrap-around
            else:
                coverage_h = h2 - h1
            assert coverage_h >= 3, (
                f"[GATE-FAIL] {sym}: cobertura {coverage_h}h < 3h minimo"
            )
        assert h1 <= 21, (
            f"[GATE-FAIL] {sym}: h1={h1} > 21 — inicio do fechamento deve ser <= 21h"
        )
    print(f"  [PASS] F1: DAILY_CLOSE_UTC cobre rollover para {len(REQUIRED_SYMBOLS)} simbolos")


def test_f2_rollover_gap_filtered():
    """Gap 21:59->23:00 DEVE ser filtrado para TODOS os 7 simbolos."""
    for sym in REQUIRED_SYMBOLS:
        # Gap tipico de rollover: 21:59 -> 23:00 UTC
        a_ms = int(datetime(2025, 6, 10, 21, 59, tzinfo=UTC).timestamp() * 1000)
        b_ms = int(datetime(2025, 6, 10, 23, 0, tzinfo=UTC).timestamp() * 1000)
        closed = _precompute_closed_intervals(a_ms - 60_000, b_ms + 60_000, sym)
        result = _is_weekend_or_daily_close(a_ms, b_ms, sym, closed)
        assert result is True, (
            f"[GATE-FAIL] {sym}: gap 21:59-23:00 NAO filtrado — "
            f"verificar DAILY_CLOSE_UTC[{sym}]"
        )
    print("  [PASS] F2: rollover 21:59-23:00 filtrado para todos os 7 simbolos")


def test_f3_weekday_gap_not_filtered():
    """Gap durante pregao (10:00-12:00) NAO deve ser filtrado."""
    a_ms = int(datetime(2025, 6, 10, 10, 0, tzinfo=UTC).timestamp() * 1000)
    b_ms = int(datetime(2025, 6, 10, 12, 0, tzinfo=UTC).timestamp() * 1000)
    closed = _precompute_closed_intervals(a_ms - 60_000, b_ms + 60_000, "XAUUSD")
    result = _is_weekend_or_daily_close(a_ms, b_ms, "XAUUSD", closed)
    assert result is False, (
        "[GATE-FAIL] gap 10:00-12:00 (pregao ativo) esta sendo filtrado — "
        "filtro de calendario agressivo demais!"
    )
    print("  [PASS] F3: gap durante pregao NAO filtrado")


def test_f4_holidays_present():
    """Lista de feriados deve existir e ter entradas minimas."""
    assert len(FOREX_HOLIDAYS_FIXED) >= 4, (
        f"[GATE-FAIL] FOREX_HOLIDAYS_FIXED tem {len(FOREX_HOLIDAYS_FIXED)} entradas — "
        f"minimo 4 (Natal, Ano Novo, Vespera Natal, Vespera Ano Novo)"
    )
    months_days = [(m, d) for m, d, _, _ in FOREX_HOLIDAYS_FIXED]
    assert (12, 25) in months_days, "[GATE-FAIL] Natal (12/25) ausente em FOREX_HOLIDAYS_FIXED"
    assert (1, 1) in months_days, "[GATE-FAIL] Ano Novo (1/1) ausente em FOREX_HOLIDAYS_FIXED"
    print(f"  [PASS] F4: {len(FOREX_HOLIDAYS_FIXED)} feriados configurados")


def test_f5_holiday_gap_filtered():
    """Gap no dia de Natal deve ser filtrado como calendario."""
    # 25/dez 10:00 -> 25/dez 20:00 (mercado fechado o dia inteiro)
    a_ms = int(datetime(2025, 12, 25, 10, 0, tzinfo=UTC).timestamp() * 1000)
    b_ms = int(datetime(2025, 12, 25, 20, 0, tzinfo=UTC).timestamp() * 1000)
    closed = _precompute_closed_intervals(a_ms - 86_400_000, b_ms + 86_400_000, "XAUUSD")
    result = _is_weekend_or_daily_close(a_ms, b_ms, "XAUUSD", closed)
    assert result is True, (
        "[GATE-FAIL] gap no Natal (25/dez) NAO filtrado — "
        "verificar FOREX_HOLIDAYS_FIXED"
    )
    print("  [PASS] F5: gap de Natal filtrado")


def test_f6_script_version():
    """SCRIPT_VERSION deve ser >= 2.3 (DXY/VIX fix)."""
    version_num = float(SCRIPT_VERSION)
    assert version_num >= 2.3, (
        f"[GATE-FAIL] SCRIPT_VERSION={SCRIPT_VERSION} < 2.3 — "
        f"cache de DXY/VIX nao foi invalidado!"
    )
    print(f"  [PASS] F6: SCRIPT_VERSION={SCRIPT_VERSION} >= 2.3")


def test_f7_scan_rollover_not_detected():
    """scan_gaps_anchored com dados ate 21:59 e apos 23:00 NAO deve gerar gap."""
    # Simula 24h de dados M1 com buraco de 22:00 a 22:59 (rollover)
    base = datetime(2025, 6, 10, 0, 0, tzinfo=UTC)
    ts = []
    for minute_offset in range(24 * 60):
        t = base + timedelta(minutes=minute_offset)
        # Pula 22:00-22:59 (rollover)
        if 22 <= t.hour < 23:
            continue
        ts.append(int(t.timestamp() * 1000))

    window_start = ts[0]
    now_ms = ts[-1] + 60_000
    closed = _precompute_closed_intervals(window_start, now_ms, "XAUUSD")
    gaps = scan_gaps_anchored(ts, window_start, now_ms,
                              symbol="XAUUSD", closed_intervals=closed)
    # Nenhum gap deve ser detectado (o buraco 22:00-22:59 e rollover)
    assert len(gaps) == 0, (
        f"[GATE-FAIL] {len(gaps)} gap(s) detectado(s) no rollover 22:00-23:00 — "
        f"filtro de calendario falhou. Gaps: {gaps}"
    )
    print("  [PASS] F7: scan_gaps_anchored nao detecta rollover como gap")


def test_f8_dxy_rollover_filtered():
    """DXYUSD gap 20:55->00:59 (3h rollover) DEVE ser filtrado."""
    # Pre-DST: gap 20:55 -> 23:59 (3h)
    a_ms = int(datetime(2025, 10, 28, 20, 55, tzinfo=UTC).timestamp() * 1000)
    b_ms = int(datetime(2025, 10, 28, 23, 59, tzinfo=UTC).timestamp() * 1000)
    closed = _precompute_closed_intervals(a_ms - 86_400_000, b_ms + 86_400_000, "DXYUSD")
    result = _is_weekend_or_daily_close(a_ms, b_ms, "DXYUSD", closed)
    assert result is True, (
        "[GATE-FAIL] DXYUSD gap 20:55-23:59 NAO filtrado — "
        "DAILY_CLOSE_UTC[DXYUSD] deve ser (20, 1) para cobrir DST-dual"
    )
    # Pos-DST: gap 21:55 -> 00:59 (3h, cruza meia-noite)
    a_ms2 = int(datetime(2025, 11, 4, 21, 55, tzinfo=UTC).timestamp() * 1000)
    b_ms2 = int(datetime(2025, 11, 5, 0, 59, tzinfo=UTC).timestamp() * 1000)
    closed2 = _precompute_closed_intervals(a_ms2 - 86_400_000, b_ms2 + 86_400_000, "DXYUSD")
    result2 = _is_weekend_or_daily_close(a_ms2, b_ms2, "DXYUSD", closed2)
    assert result2 is True, (
        "[GATE-FAIL] DXYUSD gap 21:55-00:59 (DST) NAO filtrado — "
        "DAILY_CLOSE_UTC[DXYUSD] deve cobrir wrap-around"
    )
    print("  [PASS] F8: DXYUSD rollover filtrado (pre-DST + pos-DST)")


def test_f9_vixusd_has_entry():
    """VIXUSD DEVE ter entrada em DAILY_CLOSE_UTC e GAP_MIN_MINUTES_INDEX."""
    assert "VIXUSD" in DAILY_CLOSE_UTC, (
        "[GATE-FAIL] VIXUSD AUSENTE em DAILY_CLOSE_UTC"
    )
    assert "VIXUSD" in GAP_MIN_MINUTES_INDEX, (
        "[GATE-FAIL] VIXUSD AUSENTE em GAP_MIN_MINUTES_INDEX — "
        "indice esparso precisa de threshold > 5min"
    )
    assert GAP_MIN_MINUTES_INDEX["VIXUSD"] >= 30, (
        f"[GATE-FAIL] VIXUSD threshold={GAP_MIN_MINUTES_INDEX['VIXUSD']} < 30 — "
        f"indice esparso gera micro-gaps naturais"
    )
    print(f"  [PASS] F9: VIXUSD configurado (threshold={GAP_MIN_MINUTES_INDEX['VIXUSD']}min)")


# ============================================================
# MAIN
# ============================================================

def main():
    print("=" * 60)
    print(" GATE F — REGRESSAO DAILY_CLOSE_UTC (engessamento v2.4)")
    print(" BUG v2.1: (21,22) forex -> loop infinito")
    print(" BUG v2.2: DXY/VIX sem cobertura -> gaps fantasma")
    print(" FIX v2.3: (21,23) forex + (20,1) indices + threshold 30min")
    print(" FIX v2.4: janela backfill por ativo (indices=295 dias)")
    print("=" * 60)

    tests = [
        ("F1", "DAILY_CLOSE_UTC 7 simbolos", test_f1_daily_close_covers_rollover),
        ("F2", "Rollover 21:59-23:00 filtrado", test_f2_rollover_gap_filtered),
        ("F3", "Gap pregao NAO filtrado", test_f3_weekday_gap_not_filtered),
        ("F4", "Feriados presentes", test_f4_holidays_present),
        ("F5", "Gap Natal filtrado", test_f5_holiday_gap_filtered),
        ("F6", "SCRIPT_VERSION >= 2.4", test_f6_script_version),
        ("F7", "scan_gaps rollover = 0", test_f7_scan_rollover_not_detected),
        ("F8", "DXYUSD rollover DST-dual", test_f8_dxy_rollover_filtered),
        ("F9", "VIXUSD config completo", test_f9_vixusd_has_entry),
    ]

    results = []
    for test_id, desc, func in tests:
        try:
            func()
            results.append((test_id, "PASS", desc))
        except AssertionError as e:
            print(f"  [FAIL] {test_id}: {e}")
            results.append((test_id, "FAIL", str(e)[:120]))
        except Exception as e:
            print(f"  [ERR] {test_id}: {e}")
            results.append((test_id, "ERR", str(e)[:120]))

    print(f"\n{'=' * 60}")
    passed = sum(1 for _, s, _ in results if s == "PASS")
    failed = sum(1 for _, s, _ in results if s != "PASS")
    for test_id, status, desc in results:
        icon = "OK" if status == "PASS" else "XX"
        print(f"  [{icon}] {test_id}: {desc}")

    print(f"\n  {passed}/{len(results)} gates passaram", end="")
    if failed:
        print(f" | {failed} FALHARAM")
    else:
        print()
    print(f"{'=' * 60}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
