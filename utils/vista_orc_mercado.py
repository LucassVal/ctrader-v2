"""PROPOSITO: vista_orc_mercado.py — Vista de mercado MTF por simbolo (S39).
SPEC: S39 (vista_mercado.md)
ROADMAP: S39 — drill-down das abas de mercado: o que o sistema analisa agora.

SAT de orc_mercado (R8 naming). Engine de regime em matrix_orc_vista (split DDD G12).
NUNCA toca MCP (R-NO-MCP-BYPASS):
consolidado G23 + artefatos status/ (pattern_library, score_live, signals_log).
Custo: leituras baratas + resample da cauda (10d) — NUNCA scan/score pesado.

MTF por resample do M1 (padrao vectorbt pesquisado 2026-07-30): mesma base
cientifica unica, zero lookahead (so barras fechadas). Regime = ADX + slope
EMA20 por TF; correlacao multi-janela (achado S35: janela unica insuficiente).
"""
from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from utils.logger import get_logger

logger = get_logger(__name__, "VISTA")

BASE_DIR = Path(__file__).resolve().parent.parent
CONS_DIR = BASE_DIR / "data" / "consolidated"
STATUS_DIR = BASE_DIR / "status"
SIGNALS_LOG = BASE_DIR / "data" / "signals_log.parquet"

SYMBOLS = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD"]
TAIL_DAYS = 10          # cobre janela de correlacao 1 semana + warmup
TF_RULES = {"m5": "5min", "m15": "15min", "h1": "1h"}
CORR_WINDOWS = {"b200": 200, "d1": 1440, "sem1": 10080}

_cache: dict[str, tuple[float, float, pd.DataFrame]] = {}


def _load_tail(symbol: str, days: int = TAIL_DAYS) -> pd.DataFrame | None:
    """Cauda OHLC do consolidado (cache por mtime — drill-down poll 15s)."""
    path = CONS_DIR / f"{symbol}_M1.parquet"
    try:
        if not path.exists():
            return None
        mtime = path.stat().st_mtime
    except OSError:
        return None
    hit = _cache.get(symbol)
    if hit and hit[0] == mtime and hit[1] > time.monotonic():
        return hit[2]
    try:
        df = pd.read_parquet(path, columns=["timestamp", "open", "high", "low", "close"])
    except Exception as e:
        logger.error("%s: consolidado ilegivel: %s", symbol, e)
        return None
    cutoff = (datetime.now(UTC).timestamp() - days * 86400) * 1000
    df = df[pd.to_numeric(df["timestamp"], errors="coerce") >= cutoff]
    df = df.sort_values("timestamp").reset_index(drop=True)
    if df.empty:
        return None
    _cache[symbol] = (mtime, time.monotonic() + 300, df)
    return df


def _calibracao_symbol(symbol: str) -> dict[str, Any] | None:
    """Hit-rate do simbolo — R-USE orc_calibracao.calibration_summary (S36)."""
    if not SIGNALS_LOG.exists():
        return None
    try:
        from utils.orc_calibracao import calibration_summary
        df = pd.read_parquet(SIGNALS_LOG)
        df = df[df["symbol"] == symbol]
        if df.empty:
            return None
        return calibration_summary(df)
    except Exception as e:
        logger.error("%s: calibracao falhou: %s", symbol, e)
        return None


def _padroes_top(symbol: str, top: int = 3) -> list[dict[str, Any]]:
    """Top padroes por ocorrencias — R-USE pattern_library (S34)."""
    path = STATUS_DIR / "pattern_library.json"
    try:
        if not path.exists():
            return []
        lib = json.loads(path.read_text(encoding="utf-8"))
        pats = lib.get("symbols", {}).get(symbol, {}).get("patterns", [])
        return [{
            "signal_15m": p.get("signal_15m"),
            "signal_5m": "BULLISH" if (p.get("outcome_5m") or {}).get("bullish_pct", 0) > (p.get("outcome_5m") or {}).get("bearish_pct", 0) else "BEARISH",
            "confidence": p.get("confidence"),
            "occurrences": p.get("occurrences"),
            "avg_pips_net_15m": (p.get("outcome_15m") or {}).get("avg_pips_net"),
            "hit_15m": (p.get("outcome_15m") or {}).get("bullish_pct")
            if p.get("signal_15m") == "BULLISH" else (p.get("outcome_15m") or {}).get("bearish_pct"),
            "avg_pips_net_5m": (p.get("outcome_5m") or {}).get("avg_pips_net"),
            "hit_5m": max((p.get("outcome_5m") or {}).get("bullish_pct", 0), (p.get("outcome_5m") or {}).get("bearish_pct", 0)),
        } for p in pats[:top]]
    except (json.JSONDecodeError, OSError) as e:
        logger.error("pattern_library ilegivel: %s", e)
        return []


def _correlacao_multi(symbol: str) -> dict[str, Any] | None:
    """Correlacao de returns log M1 vs pares — 3 janelas (S35: unica falha)."""
    base = _load_tail(symbol)
    if base is None:
        return None
    b = base.set_index("timestamp")["close"].astype("float64")
    ret_b = np.log(b / b.shift(1)).dropna()
    out: dict[str, Any] = {"janelas": {}, "peers_fortes": []}
    for peer in SYMBOLS:
        if peer == symbol:
            continue
        dfp = _load_tail(peer)
        if dfp is None:
            continue
        p = dfp.set_index("timestamp")["close"].astype("float64")
        ret_p = np.log(p / p.shift(1)).dropna()
        joined = pd.concat([ret_b, ret_p], axis=1, keys=["a", "b"]).dropna()
        for wname, wlen in CORR_WINDOWS.items():
            j = joined.tail(wlen)
            if len(j) < 50:
                continue
            r = float(j["a"].corr(j["b"]))
            out["janelas"].setdefault(wname, {})[peer] = round(r, 2)
            if wname == "sem1" and abs(r) >= 0.5:
                out["peers_fortes"].append({"peer": peer, "r": round(r, 2)})
    return out if out["janelas"] else None


def _score_live_symbol(symbol: str) -> dict[str, Any] | None:
    path = STATUS_DIR / "score_live.json"
    try:
        if not path.exists():
            return None
        age_s = round(time.time() - path.stat().st_mtime)
        data = json.loads(path.read_text(encoding="utf-8"))
        s = (data.get("symbols") or {}).get(symbol)
        if not s:
            return None
        return {**s, "age_s": age_s, "stale": age_s > 600}
    except (json.JSONDecodeError, OSError) as e:
        logger.error("score_live ilegivel: %s", e)
        return None


def market_detail(symbol: str) -> dict[str, Any]:
    """Contrato S39: tudo que o sistema analisa no simbolo, agora."""
    from utils import matrix_orc_vista as mv
    df = _load_tail(symbol)
    regime: dict[str, Any] = {}
    if df is not None:
        regime["m1"] = mv.regime_tf(df, None)
        for tf, rule in TF_RULES.items():
            regime[tf] = mv.regime_tf(df, rule)

    direcoes = {tf: r["regime"] for tf, r in regime.items() if r}
    dir_m1 = direcoes.get("m1")
    acordo = sum(1 for tf, d in direcoes.items()
                 if tf != "m1" and d == dir_m1 and dir_m1 in ("TREND_UP", "TREND_DOWN"))

    return {
        "symbol": symbol,
        "gerado_em": datetime.now(UTC).isoformat(),
        "sessao_atual": mv.sessao_atual(),
        "regime_mtf": regime,
        "concordancia": {
            "direcao_m1": dir_m1,
            "tfs_de_acordo": acordo,
            "total_tfs": max(len(direcoes) - 1, 0),
        },
        "calibracao": _calibracao_symbol(symbol),
        "padroes_top": _padroes_top(symbol),
        "score_live": _score_live_symbol(symbol),
        "correlacao": _correlacao_multi(symbol),
    }
