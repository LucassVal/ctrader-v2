"""PROPOSITO: storage_orc_consolidated.py — Indicadores computados do consolidado G23.
SPEC: S31 (fallback S31-VBT)
ROADMAP: S31-VBT — enquanto o vbt_{SYM}.parquet so acumula snapshots do F0
vivo (~1 dia), o Vector le o consolidado de 2 anos e computa os MESMOS
indicadores. SAT de storage_orc_vbt (R-USE f1_analyzer.indicators_orc_analise
— mesmo codigo do vivo/replay). NUNCA toca MCP (R-NO-MCP-BYPASS).

Contrato: consolidated_indicator_points(symbol, days, max_points) ->
{history_days, history_points, points, source} | None
Cache em-processo TTL 300s chaveado por (symbol, days, max_points) + mtime.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from utils.logger import get_logger

logger = get_logger(__name__, "VBT-C")

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

_CONS_TTL_S = 300  # indicadores 2 anos sao pesados (~1s) — cache por processo
_CONS_CACHE: dict[tuple[str, int, int], tuple[float, float, dict[str, Any]]] = {}


def consolidated_indicator_points(
    symbol: str, days: int, max_points: int = 5000, full_families: bool = False,
) -> dict[str, Any] | None:
    """Computa indicadores sobre o consolidado M_1 (G23) de um simbolo.

    Retorna ate max_points pontos M_1 recentes + span REAL do historico
    (history_days — alimenta a confianca progressiva do score). None se o
    consolidado nao existe, e ilegivel ou nao cobre o periodo.

    S39: full_families=True computa as 10 familias avancadas (Stoch, SMA,
    Donchian, HMA, Keltner, CCI, PSAR, WPR, Aroon, ZLEMA) na CAUDA
    (max_points + WARMUP_BARS) via families_orc_vectorbt e funde no ultimo
    ponto — load_indicators.latest sai 16/16. Default False = caminho do
    scan INALTERADO (lean, 850k pontos sem custo extra).
    """
    cons = DATA_DIR / "consolidated" / f"{symbol}_M1.parquet"
    if not cons.exists():
        logger.info("%s: consolidado ausente (backfill pendente)", symbol)
        return None
    try:
        mtime = cons.stat().st_mtime
    except OSError as e:
        logger.error("%s: stat consolidado falhou: %s", symbol, e)
        return None
    key = (symbol, days, max_points, full_families)
    hit = _CONS_CACHE.get(key)
    if hit and hit[0] > time.monotonic() and hit[1] == mtime:
        return hit[2]

    try:
        df = pd.read_parquet(cons)
    except Exception as e:
        logger.error("%s: consolidado ilegivel: %s", symbol, e)
        return None
    if df.empty or "timestamp" not in df.columns:
        logger.error("%s: consolidado vazio ou sem coluna timestamp", symbol)
        return None

    ts = pd.to_numeric(df["timestamp"], errors="coerce")
    mask = ts > 0
    cutoff_ms = (datetime.now(UTC) - timedelta(days=days)).timestamp() * 1000
    mask &= ts >= cutoff_ms
    if not mask.any():
        logger.info("%s: consolidado sem barras nos ultimos %d dias", symbol, days)
        return None
    df = df[mask].copy()
    ts = ts[mask]
    order = ts.argsort()
    df = df.iloc[order]
    ts = ts.iloc[order]

    close = pd.to_numeric(df["close"], errors="coerce")
    high = pd.to_numeric(df["high"], errors="coerce")
    low = pd.to_numeric(df["low"], errors="coerce")
    vol = (pd.to_numeric(df["tick_volume"], errors="coerce").fillna(0)
           if "tick_volume" in df.columns else pd.Series(0, index=df.index))

    from f1_analyzer import indicators_orc_analise as ind
    bb = ind.bbands(close)
    md = ind.macd(close)
    out = pd.DataFrame({
        "timestamp": (ts // 1000).astype("int64"),
        "close": close,
        "rsi": ind.rsi(close),
        "macd": md["line"],
        "macd_signal": md["signal"],
        "macd_hist": md["histogram"],
        "bb_upper": bb["upper"],
        "bb_middle": bb["middle"],
        "bb_lower": bb["lower"],
        "bb_width_pct": bb["bandwidth"] * 100,
        "atr": ind.atr(high, low, close),
        "adx": ind.adx(high, low, close),
        "obv": ind.obv(close, vol),
    })

    history_days = round(float(ts.iloc[-1] - ts.iloc[0]) / 86_400_000, 1)
    points = out.tail(max_points).to_dict(orient="records")
    for p in points:
        for k, v in p.items():
            if isinstance(v, float) and pd.isna(v):
                p[k] = None

    if full_families and points:
        # S39: 10 familias avancadas na cauda (warmup + max_points) — R-USE
        # families_orc_vectorbt; fundidas no ultimo ponto (16/16 no latest)
        try:
            from utils.families_orc_vectorbt import WARMUP_BARS, latest_families
            # high/low/close da cauda — do df original alinhado (out nao tem high/low)
            df_tail = df.tail(max_points + WARMUP_BARS)
            fams = latest_families(
                pd.to_numeric(df_tail["high"], errors="coerce").ffill().to_numpy(dtype="float64"),
                pd.to_numeric(df_tail["low"], errors="coerce").ffill().to_numpy(dtype="float64"),
                pd.to_numeric(df_tail["close"], errors="coerce").ffill().to_numpy(dtype="float64"),
            )
            points[-1].update(fams)
        except Exception as e:
            logger.error("%s: full_families falhou (latest parcial): %s", symbol, e)

    payload = {
        "history_days": history_days,
        "history_points": len(out),
        "points": points,
        "source": "consolidated_g23",
    }
    _CONS_CACHE[key] = (time.monotonic() + _CONS_TTL_S, mtime, payload)
    return payload
