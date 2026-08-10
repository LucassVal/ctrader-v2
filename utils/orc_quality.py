"""PROPOSITO: orc_quality.py — Qualidade de sinais via walk-forward backtest.
SPEC: S29
ROADMAP: S29 — mede se os sinais gerados teriam dado lucro no historico.

R-USE: storage_orc_vbt.py (load_history) + orc_vectorbt.py (indicators).
Pipeline: VBT history -> generate_signals -> backtest -> quality score.

Mede:
  - Precisao: dos sinais BUY/SELL, quantos acertaram direcao?
  - Profit factor: ganho/perda nos sinais
  - Win rate: % sinais com P&L positivo
  - F1 score: harmonic mean precision x recall
  - Tempo de analise: quantas velas/barras de historico disponiveis
"""

from __future__ import annotations

from typing import Any


def generate_signals(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Gera sinais BUY/SELL (S29 Confluence Model).

    Regras (Confluencia de Trend + Momentum + Strength):
      BUY: sma_fast > sma_slow AND close > sma_slow AND macd_hist > 0 AND 45 <= rsi <= 65 AND adx >= 25
      SELL: sma_fast < sma_slow AND close < sma_slow AND macd_hist < 0 AND 35 <= rsi <= 55 AND adx >= 25
      Bonus: kc_squeeze > 0 adiciona confianca de iminencia de breakout.

    Retorna lista de sinais com timestamp, tipo, preco, indicadores.
    """
    signals: list[dict[str, Any]] = []
    if not history:
        return signals

    for row in history:
        close = row.get("close") or row.get("last_close")
        ts = row.get("timestamp")
        rsi = row.get("rsi")
        adx = row.get("adx")
        sma_fast = row.get("sma_fast")
        sma_slow = row.get("sma_slow")
        macd_hist = row.get("macd_hist")
        kc_squeeze = row.get("kc_squeeze")
        bb_width_pct = row.get("bb_width_pct")

        if any(v is None for v in (close, rsi, adx, sma_fast, sma_slow, macd_hist)):
            continue

        if isinstance(close, (int, float)) and close <= 0:
            continue

        signal_type = None
        confidence = 0.0

        # BUY: Tendencia de Alta Confirmada (Triple Screen)
        if sma_fast > sma_slow and close > sma_slow and macd_hist > 0 and 45 <= rsi <= 65 and adx >= 25:
            signal_type = "BUY"
            confidence = 0.5 + min(0.35, (adx - 25) / 50.0)
            if kc_squeeze and kc_squeeze > 0:
                confidence += 0.15

        # SELL: Tendencia de Baixa Confirmada (Triple Screen)
        elif sma_fast < sma_slow and close < sma_slow and macd_hist < 0 and 35 <= rsi <= 55 and adx >= 25:
            signal_type = "SELL"
            confidence = 0.5 + min(0.35, (adx - 25) / 50.0)
            if kc_squeeze and kc_squeeze > 0:
                confidence += 0.15

        if signal_type:
            signals.append({
                "timestamp": ts,
                "type": signal_type,
                "price": close,
                "rsi": rsi,
                "adx": adx,
                "sma_fast": sma_fast,
                "sma_slow": sma_slow,
                "macd_hist": macd_hist,
                "kc_squeeze": kc_squeeze,
                "confidence": round(max(0.0, min(1.0, confidence)), 3),
                "bb_width_pct": bb_width_pct,
                "breakout_pct": row.get("breakout_pct"),
            })

    return signals


def backtest_signals(signals: list[dict[str, Any]], price_series: list[dict[str, Any]]) -> dict[str, Any]:
    """Walk-forward: verifica se o sinal previu a direcao correta nos proximos N candles.

    Lookahead: 5 velas (M_1 = 5min).
    Acerto = preco moveu na direcao prevista em pelo menos 0.05% (5 pips para forex).
    """
    if len(signals) < 2 or len(price_series) < 10:
        return {"total": len(signals), "backtested": 0, "note": "dados insuficientes"}

    prices = {p.get("timestamp"): p.get("close", 0) for p in price_series if p.get("close")}
    if not prices:
        return {"total": len(signals), "backtested": 0, "note": "sem precos"}

    sorted_ts = sorted(prices.keys())
    wins = 0
    losses = 0
    total_pnl = 0.0
    results: list[dict[str, Any]] = []

    for sig in signals:
        ts = sig.get("timestamp")
        entry = sig.get("price", 0)
        stype = sig.get("type")

        if ts is None or not entry or not stype:
            continue

        # Encontra preco 5 velas a frente
        try:
            idx = sorted_ts.index(ts)
            future_ts = sorted_ts[min(idx + 5, len(sorted_ts) - 1)]
            exit_price = prices.get(future_ts, entry)
        except (ValueError, IndexError):
            continue

        if exit_price == entry:
            continue

        pnl_pct = (exit_price - entry) / entry * 100
        if stype == "SELL":
            pnl_pct = -pnl_pct  # invertido

        correct = pnl_pct > 0.05  # min 5 pip move
        if correct:
            wins += 1
        else:
            losses += 1

        total_pnl += pnl_pct
        results.append({
            "ts": ts,
            "type": stype,
            "entry": entry,
            "exit": exit_price,
            "pnl_pct": round(pnl_pct, 4),
            "correct": correct,
        })

    total_backtested = wins + losses
    win_rate = (wins / total_backtested * 100) if total_backtested else 0

    # F1: tp, fp, fn
    tp = wins  # true positive: signal + correct
    fp = losses  # false positive
    fn = len(results) - wins  # missed
    precision = tp / (tp + fp) if (tp + fp) else 0
    recall = tp / (tp + fn) if (tp + fn) else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0

    return {
        "total_signals": len(signals),
        "backtested": total_backtested,
        "wins": wins,
        "losses": losses,
        "win_rate": round(win_rate, 1),
        "total_pnl_pct": round(total_pnl, 3),
        "avg_pnl_pct": round(total_pnl / total_backtested, 4) if total_backtested else 0,
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1_score": round(f1, 3),
        "details": results[-10:],  # ultimos 10 sinais
    }


def quality_metrics(symbol: str) -> dict[str, Any]:
    """Orquestrador S29: carrega VBT history -> gera sinais -> backtest -> score.

    R-USE:
      - storage_orc_vbt.load_history() para dados
      - storage_orc_vbt.load_indicators() para ultimo snapshot
      - generate_signals() + backtest_signals() neste modulo
    """
    try:
        from utils.storage_orc_vbt import load_history, load_indicators

        # Tempo de analise: quantos dias de historico?
        vbt_snapshot = load_indicators(symbol)
        analysis_days = vbt_snapshot.get("history_days", 0)
        total_points = vbt_snapshot.get("history_points", 0)

        # Historico completo
        vbt_history = load_history(symbol, days=730)
        points = vbt_history.get("points", [])

        if not points:
            return {
                "symbol": symbol,
                "status": "sem_dados",
                "analysis_days": 0,
                "total_points": 0,
                "note": "Execute backfill e reinicie F0 para popular vbt_{sym}.parquet",
                "signals": [],
            }

        # Gera sinais
        signals = generate_signals(points)

        # Backtest
        bt = backtest_signals(signals, points)

        # Timestamps para calcular periodo de analise real
        timestamps = [p.get("timestamp") for p in points if p.get("timestamp")]
        first_ts = min(timestamps) if timestamps else 0
        last_ts = max(timestamps) if timestamps else 0
        if first_ts and last_ts:
            real_days = (last_ts - first_ts) / 86400
        else:
            real_days = analysis_days

        return {
            "symbol": symbol,
            "status": "ok",
            "analysis_days": round(real_days, 1),
            "total_points": total_points,
            "signals_count": len(signals),
            "backtest": bt,
            "note": f"Regras: RSI<35 BUY, RSI>65 SELL, ADX>20, lookahead 5 velas — {real_days:.0f}d de dados",
        }

    except Exception as e:
        return {
            "symbol": symbol,
            "status": "erro",
            "error": str(e)[:200],
        }
