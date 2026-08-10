"""
PROPOSITO: Orquestrador de Mercado — enriquece dados brutos do snapshot F0 com
           indicadores padronizados: pip, spread %, forca relativa, lote minimo.
SPEC: S2 (F0 collector) + S25 (R-USE alternatives)
ROADMAP: 2.0
FLOW:   snapshot.json -> orc_mercado.normalize_markets() -> /vector/markets -> React
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

# -- PIP SPECS — hardcoded porque get_symbols() do MCP nao retorna pipSize --
# pip_value: 1 pip em unidades da cotacao (ex: EURUSD bid=114018, 1 pip = 10)
# min_lot: volume minimo (0.01 = micro lote padrao forex)
# price_divisor: para exibir preco real (bid / divisor)
PIP_SPECS: dict[str, dict[str, Any]] = {
    "EURUSD": {"pip_value": 10, "pip_size": 0.0001, "min_lot": 0.01, "price_divisor": 100000, "desc": "Euro/Dolar"},
    "GBPUSD": {"pip_value": 10, "pip_size": 0.0001, "min_lot": 0.01, "price_divisor": 100000, "desc": "Libra/Dolar"},
    "USDJPY": {"pip_value": 1000, "pip_size": 0.01, "min_lot": 0.01, "price_divisor": 1000, "desc": "Dolar/Iene"},
    "AUDUSD": {"pip_value": 10, "pip_size": 0.0001, "min_lot": 0.01, "price_divisor": 100000, "desc": "Dolar Australiano"},
    "XAUUSD": {"pip_value": 1000, "pip_size": 0.1, "min_lot": 0.01, "price_divisor": 100000, "desc": "Ouro/Dolar"},
}


def _read_snapshot() -> dict[str, Any]:
    """Le o snapshot publicado pelo F0. Retorna {} se indisponivel."""
    try:
        import json
        snap_path = Path(__file__).resolve().parent.parent / "status" / "snapshot.json"
        if snap_path.exists():
            return json.loads(snap_path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def normalize_markets(snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
    """Enriquece dados brutos do snapshot com indicadores de mercado padronizados.
    Retorna dict com: online, strength_rank, markets (dict por simbolo).
    Se snapshot=None, usa DataSource (cache 5s) — backward compat."""
    if snapshot is None:
        from utils.data_source import get_markets_raw, is_online
        if not is_online():
            return {"online": False, "strength_rank": [], "markets": {}}
        raw_symbols = get_markets_raw()
        online = True
    else:
        if not snapshot or not snapshot.get("online"):
            return {"online": False, "strength_rank": [], "markets": {}}
        raw_symbols = snapshot.get("symbols", {})
        online = bool(snapshot.get("online"))
    if not raw_symbols:
        return {"online": False, "strength_rank": [], "markets": {}}

    markets: dict[str, dict[str, Any]] = {}
    strengths: list[tuple[str, float]] = []

    for sym, data in raw_symbols.items():
        spec = PIP_SPECS.get(sym, {"pip_value": 1, "min_lot": 0.01, "price_divisor": 1, "desc": ""})
        pip_val = spec["pip_value"]
        divisor = spec["price_divisor"]

        bid_raw = data.get("bid", 0)
        ask_raw = data.get("ask", 0)
        spread_raw = data.get("spread", 0)
        open_raw = data.get("open", 0)
        high_raw = data.get("high", 0)
        low_raw = data.get("low", 0)
        close_raw = data.get("close", 0)
        volume = data.get("tick_volume", 0)

        # -- Precos formatados (reais) --
        bid = round(bid_raw / divisor, 5) if divisor > 1 else bid_raw
        ask = round(ask_raw / divisor, 5) if divisor > 1 else ask_raw

        # -- Spread em pips e % --
        spread_pips = round(spread_raw / pip_val, 1) if pip_val > 0 else 0
        spread_pct = round(spread_raw / bid_raw * 100, 4) if bid_raw > 0 else 0

        # -- Movimento M_1 em pips --
        pip_move = round((close_raw - open_raw) / pip_val, 1) if pip_val > 0 else 0

        # -- Range M_1 em pips --
        range_pips = round((high_raw - low_raw) / pip_val, 1) if pip_val > 0 else 0

        # -- Forca relativa (% change do open) --
        change_pct = round((close_raw - open_raw) / open_raw * 100, 4) if open_raw > 0 else 0
        strengths.append((sym, change_pct))

        markets[sym] = {
            "symbol": sym,
            "desc": spec["desc"],
            "bid": bid,
            "ask": ask,
            "spread_pips": spread_pips,
            "spread_pct": spread_pct,
            "pip_move": pip_move,
            "range_pips": range_pips,
            "volume": volume,
            "change_pct": change_pct,
            "min_lot": spec["min_lot"],
            "open": round(open_raw / divisor, 5) if divisor > 1 else open_raw,
            "high": round(high_raw / divisor, 5) if divisor > 1 else high_raw,
            "low": round(low_raw / divisor, 5) if divisor > 1 else low_raw,
            "close": round(close_raw / divisor, 5) if divisor > 1 else close_raw,
            # S25.11 — multi-timeframe (preenchido via trendbars)
            "change_5m": 0.0,
            "range_5m": 0.0,
            "change_15m": 0.0,
            "range_15m": 0.0,
            "change_1h": 0.0,
            "range_1h": 0.0,
            "change_6h": 0.0,
            "range_6h": 0.0,
            # S25.10 — volatilidade/lateralidade
            "vol_pct": 0.0,
            "lat_pct": 0.0,
        }

    # -- Multi-timeframe via trendbars (S25.11) --
    _enrich_multi_timeframe(markets, snapshot)

    # -- Volatilidade e lateralidade --
    for sym, mkt in markets.items():
        rng = mkt.get("range_pips", 0)
        chg = abs(mkt.get("pip_move", 0))
        close = mkt.get("close", 1)
        spec = PIP_SPECS.get(sym, {"pip_value": 1, "price_divisor": 1})
        pip_val = spec["pip_value"]
        divisor = spec["price_divisor"]
        # range em unidades de preco (converte pips -> $)
        range_price = (rng * pip_val / divisor) / close * 100
        mkt["vol_pct"] = round(range_price, 4)
        mkt["lat_pct"] = round((1 - chg / max(rng, 0.01)) * 100, 1) if rng > 0 else 50.0

    # -- Ranking de forca relativa --
    strengths.sort(key=lambda x: x[1], reverse=True)
    strength_rank = [{"symbol": s, "change_pct": v, "direction": "up" if v > 0 else "down"} for s, v in strengths]

    return {
        "online": online,
        "strength_rank": strength_rank,
        "markets": markets,
    }


def _enrich_multi_timeframe(markets: dict[str, dict[str, Any]], snapshot: dict[str, Any] | None = None) -> None:
    """S39 — MTF por resample do M1 consolidado.
    Evita bypassar o padrao ouro e remove a dependencia pesada do get_trendbars."""
    try:
        import pandas as pd

        from utils.vista_orc_mercado import _load_tail
    except ImportError:
        return

    for sym in list(markets.keys()):
        spec = PIP_SPECS.get(sym, {"pip_value": 1, "price_divisor": 1})
        pip_val = spec["pip_value"]

        try:
            df_raw = _load_tail(sym, days=2)
            if df_raw is None or df_raw.empty:
                continue

            df = df_raw.copy()
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            df.set_index("timestamp", inplace=True)

            # Map of desired timeframes and their pandas resample rules + tail count
            # m15: 4 bars (1h), h1: 2 bars (2h), h4: 2 bars (8h)
            rules = {
                "5m": ("5min", 12),
                "15m": ("15min", 4),
                "1h": ("1h", 2),
                "6h": ("4h", 2)
            }

            for key, (rule, count) in rules.items():
                resampled = df.resample(rule).agg({
                    "open": "first",
                    "high": "max",
                    "low": "min",
                    "close": "last"
                }).dropna()

                bars = resampled.tail(count)
                if len(bars) >= 2:
                    o = bars.iloc[0]["open"]
                    c = bars.iloc[-1]["close"]
                    h = float(bars["high"].max())
                    lo = float(bars["low"].min())

                    markets[sym][f"change_{key}"] = round((c - o) / pip_val, 1)
                    markets[sym][f"range_{key}"] = round((h - lo) / pip_val, 1)
                    if key in ("1h", "6h"):
                        markets[sym][f"candles_{key}"] = len(bars)

        except Exception:
            continue
