"""PROPOSITO: S32 — score combinado S29 (regras) + S30 (padroes).
SPEC: S32 / S39 (MTF — combined_score_mtf)
ROADMAP: S32, C4

Orquestrador unico do score: tira a regra de combinacao do router
(ctrader_v2.py vira proxy). NAO toca MCP, NAO le parquet — so orquestra.
Pesos definidos na spec S32: quality(f1) x 0.33 + patterns(conf) x 0.67.

combined_score_mtf (S39/C4): score por timeframe (M1, M5, M15) via
resample local do parquet M1 — sem MCP, sem get_trendbars.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

QUALITY_WEIGHT = 0.33
PATTERN_WEIGHT = 0.67
FULL_HISTORY_DAYS = 730  # 2 anos — cobertura total (S31)

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"


def combined_score(symbol: str) -> dict[str, Any]:
    """Combina F1 do backtest de regras (S29) com confianca de padroes (S30).

    Fallback: sem padroes (confidence=0), usa apenas quality_f1.
    """
    try:
        from utils.orc_pattern import pattern_analysis
        from utils.orc_quality import quality_metrics
    except ImportError as e:
        print(f"[ERRO] orc_score: import falhou — {e}", file=__import__("sys").stderr)
        return {"symbol": symbol, "status": "erro", "error": f"import: {e}"[:200]}

    quality = quality_metrics(symbol)
    patterns = pattern_analysis(symbol)

    q_f1 = quality.get("backtest", {}).get("f1_score", 0)
    p_conf = patterns.get("outcome", {}).get("confidence", 0)

    if p_conf > 0:
        combined = round(q_f1 * QUALITY_WEIGHT + p_conf * PATTERN_WEIGHT, 3)
        signal = patterns.get("outcome", {}).get("signal", "NEUTRAL")
        rule = f"quality(f1)x{QUALITY_WEIGHT} + patterns(conf)x{PATTERN_WEIGHT}"
    else:
        combined = round(q_f1, 3)
        signal = "NEUTRAL"
        rule = "apenas quality (sem padroes)"

    # Confianca progressiva (S31): cobertura AUDITADA do G23 (gap_report
    # reconciliado) — NAO a janela de analise (5000 pontos M_1 ≈ 3,5d).
    # O score escala com o banco conciliado real. Fallback: janela de
    # analise (comportamento antigo) se o gap_report nao existe.
    data_days = max(
        float(quality.get("analysis_days", 0) or 0),
        float(patterns.get("analysis_days", 0) or 0),
    )
    coverage_source = "janela_analise"
    try:
        from utils.orc_metricas import _read_gap_coverage
        cov_pct = float(_read_gap_coverage().get(symbol, 0.0))
        if cov_pct > 0:
            coverage = round(min(1.0, cov_pct / 100), 3)
            coverage_source = "g23_gap_report"
        else:
            coverage = round(min(1.0, data_days / FULL_HISTORY_DAYS), 3)
    except Exception:
        coverage = round(min(1.0, data_days / FULL_HISTORY_DAYS), 3)
    adjusted = round(combined * coverage, 3)

    # -- WIRE Lab -> Analise: bonus do Bloco1 (S42) --
    lab_weight = 0.0
    lab_source = "offline"
    try:
        _lab_path = Path(__file__).resolve().parent.parent / "status" / "bloco1_best.json"
        if _lab_path.exists():
            import json as _json
            _lab = _json.loads(_lab_path.read_text())
            signals = _lab.get("signals_validated", {})
            if signals.get("total", 0) > 100:
                lab_weight = 0.15
                lab_source = f"bloco1_{_lab.get('tf','M5')}"  # noqa: F841
    except Exception:
        pass

    adjusted_lab = round(adjusted * (1.0 + lab_weight), 3)  # noqa: F841

    return {
        "symbol": symbol,
        "status": "ok",
        "combined_confidence": combined,
        "adjusted_confidence": adjusted,
        "data_days": round(data_days, 1),
        "coverage_pct": round(coverage * 100, 1),
        "coverage_source": coverage_source,
        "signal": signal,
        "quality_f1": q_f1,
        "pattern_confidence": p_conf,
        "rule": rule,
        "details": {
            "quality": quality,
            "patterns": patterns,
        },
    }


def _score_from_indicators(
    indicators: dict[str, Any],
    close: float,
) -> dict[str, Any]:
    """Calcula score simplificado a partir de indicadores de 1 timeframe.

    Regras (S29 Confluence Model adaptado):
      BULLISH: sma_fast > sma_slow AND macd_hist > 0 AND 45 <= rsi <= 65 AND adx >= 20
      BEARISH: sma_fast < sma_slow AND macd_hist < 0 AND 35 <= rsi <= 55 AND adx >= 20
      NEUTRAL: caso contrario

    Score baseado na forca dos indicadores (0-100).
    """
    rsi = indicators.get("rsi")
    adx = indicators.get("adx")
    sma_fast = indicators.get("sma_fast")
    sma_slow = indicators.get("sma_slow")
    macd_hist = indicators.get("macd_hist")
    breakout_pct = indicators.get("breakout_pct", 50)

    signal = "NEUTRAL"
    score = 50.0  # base neutra

    if any(v is None for v in (rsi, adx, sma_fast, sma_slow, macd_hist)):
        return {"signal": "NEUTRAL", "score": 50.0, "indicators": indicators}

    # BULLISH confluence
    if sma_fast > sma_slow and macd_hist > 0 and 45 <= rsi <= 65 and adx >= 20:
        signal = "BULLISH"
        # Score: ADX strength (0-35) + RSI posicionamento (0-20) + breakout bonus (0-15) + base (30)
        base = 50.0
        adx_bonus = min(35.0, (adx - 20) / 30.0 * 35.0)
        rsi_bonus = min(20.0, (rsi - 45) / 20.0 * 20.0)
        breakout_bonus = min(15.0, max(0, (breakout_pct - 50) / 50.0 * 15.0))
        score = base + adx_bonus + rsi_bonus + breakout_bonus

    # BEARISH confluence
    elif sma_fast < sma_slow and macd_hist < 0 and 35 <= rsi <= 55 and adx >= 20:
        signal = "BEARISH"
        base = 50.0
        adx_bonus = min(35.0, (adx - 20) / 30.0 * 35.0)
        rsi_bonus = min(20.0, (55 - rsi) / 20.0 * 20.0)
        breakout_bonus = min(15.0, max(0, (50 - breakout_pct) / 50.0 * 15.0))
        score = base + adx_bonus + rsi_bonus + breakout_bonus

    # Clamp 0-100
    score = max(0.0, min(100.0, score))

    return {
        "signal": signal,
        "score": round(score, 1),
        "indicators": {k: indicators.get(k) for k in ("rsi", "adx", "sma_fast", "sma_slow",
                         "macd_hist", "atr", "breakout_pct", "kc_squeeze", "last_close")},
    }


def _load_m1_parquet(symbol: str) -> pd.DataFrame:
    """Carrega os dados M1 mais recentes do parquet para 1 simbolo.

    Procura data/m1_{SYM}_{ANO}.parquet — pega as ultimas 200 velas.
    """
    # sem imports de datetime — usa pandas internamente

    candidates = sorted(DATA_DIR.glob(f"m1_{symbol}_*.parquet"), reverse=True)
    if not candidates:
        raise FileNotFoundError(f"Nenhum parquet M1 para {symbol}")

    dfs = []
    for path in candidates[:2]:
        try:
            df = pd.read_parquet(path)
            dfs.append(df)
        except Exception:
            continue

    if not dfs:
        raise FileNotFoundError(f"Parquet M1 {symbol} ilegivel")

    df = pd.concat(dfs, ignore_index=True)
    df = df.sort_values("timestamp").drop_duplicates(subset=["timestamp"], keep="last")
    return df.tail(200)


def combined_score_mtf(symbol: str) -> dict[str, Any]:
    """Score M1(completo: S29+S30) + M5/M15(simplificado: indicadores puros).

    S39/C4: MTF via resample local do parquet M1 — SEM get_trendbars MCP.

    Args:
        symbol: par forex (XAUUSD, EURUSD, etc.)

    Returns:
        {M1: {score, signal, ...}, M5: {...}, M15: {...}, status: "ok"/"erro"}
    """
    result: dict[str, Any] = {"symbol": symbol, "status": "ok"}

    # -- M1: score completo (quality + patterns) --
    try:
        result["M1"] = combined_score(symbol)
    except Exception as e:
        result["M1"] = {"status": "erro", "error": str(e)[:100]}

    # -- M5/M15: score simplificado via resample + indicadores --
    try:
        df_m1 = _load_m1_parquet(symbol)

        from utils.orc_vectorbt import compute_indicators_mtf
        mtf_indicators = compute_indicators_mtf(df_m1, timeframes=("M5", "M15"))

        for tf in ("M5", "M15"):
            indicators = mtf_indicators.get(tf, {})
            if indicators and not indicators.get("error"):
                close = indicators.get("last_close", 0)
                score_info = _score_from_indicators(indicators, close)
                result[tf] = {
                    "status": "ok",
                    "signal": score_info["signal"],
                    "score": score_info["score"],
                    "quality_f1": None,
                    "pattern_conf": None,
                    "coverage_pct": 100.0,
                    "note": "score simplificado via resample M1->M5/M15 (indicadores puros)",
                    "indicators": score_info["indicators"],
                }
            else:
                result[tf] = {"status": "erro", "error": indicators.get("error", "sem dados")}

    except FileNotFoundError as e:
        result["M5"] = {"status": "erro", "error": str(e)[:100]}
        result["M15"] = {"status": "erro", "error": str(e)[:100]}
    except Exception as e:
        result["M5"] = {"status": "erro", "error": str(e)[:100]}
        result["M15"] = {"status": "erro", "error": str(e)[:100]}

    return result
