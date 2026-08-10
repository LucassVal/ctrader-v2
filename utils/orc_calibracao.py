"""PROPOSITO: orc_calibracao.py — Quality Track Record: previsao x acerto (S36).
SPEC: S36 (orc_calibracao.md)
ROADMAP: S36 — signals_log.parquet + reconciliador + calibration.json.

Orquestrador da calibracao. NAO toca MCP — so le/grava parquet + status/.
- append_signals(rows): append dedup em data/signals_log.parquet
- reconcile(): fecha outcomes de sinais com ts+60min < now (lookahead M1,
  LIQUIDO de spread — S34 sec.4b) e grava status/calibration.json
- calibration_summary(df): hit-rate por faixa (min 30), Brier 5/15/60, drift,
  replay x live

CLI: python -m utils.orc_calibracao --reconcile
"""
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from utils.logger import get_logger

logger = get_logger(__name__, "CALIB")

BASE_DIR = Path(__file__).resolve().parent.parent
SIGNALS_LOG = BASE_DIR / "data" / "signals_log.parquet"
CALIBRATION_JSON = BASE_DIR / "status" / "calibration.json"
CONSOLIDATED_DIR = BASE_DIR / "data" / "consolidated"

SPREAD_PIPS: dict[str, float] = {
    "XAUUSD": 3.5, "EURUSD": 1.0, "GBPUSD": 1.2, "USDJPY": 1.0, "AUDUSD": 1.2,
}
LOOKAHEADS = (5, 15, 60)
SCORE_BINS = (0, 50, 70, 85, 100)
MIN_SAMPLES = 30

COLUMNS = [
    "ts", "symbol", "origem", "strategy_id", "sinal", "score", "quality_f1",
    "coverage_pct", "close_entrada",
    "outcome_5m_pips", "outcome_15m_pips", "outcome_60m_pips",
    "acerto_5m", "acerto_15m", "acerto_60m",
]


def append_signals(rows: list[dict[str, Any]]) -> int:
    """Append em signals_log.parquet com dedup por (symbol, origem, ts)."""
    if not rows:
        return 0
    df_new = pd.DataFrame(rows)
    for col in COLUMNS:
        if col not in df_new.columns:
            df_new[col] = None
    df_new = df_new[COLUMNS]
    df_new["ts"] = pd.to_datetime(df_new["ts"], utc=True)

    old_len = 0
    if SIGNALS_LOG.exists():
        try:
            df_old = pd.read_parquet(SIGNALS_LOG)
            old_len = len(df_old)
            df = pd.concat([df_old, df_new], ignore_index=True)
        except Exception as e:
            logger.error("signals_log ilegivel, recriando: %s", e)
            df = df_new
    else:
        df = df_new
    df = df.drop_duplicates(subset=["symbol", "origem", "ts"], keep="first")
    df = df.sort_values("ts").reset_index(drop=True)
    SIGNALS_LOG.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(SIGNALS_LOG, index=False)
    added = len(df) - old_len
    logger.info("signals_log: %d linhas totais (%+d)", len(df), added)
    return max(added, 0)


def purge_signals(origem: str, symbols: list[str]) -> int:
    """Remove linhas de uma origem para os simbolos dados (S34 v1.2).

    Re-scan do replay SUBSTITUI as linhas antigas — sem purge, o dedup
    keep=first do append manteria scores velhos para sempre. Linhas de
    outras origens (live) NUNCA passam por aqui.
    """
    if not SIGNALS_LOG.exists():
        return 0
    try:
        df = pd.read_parquet(SIGNALS_LOG)
    except Exception as e:
        logger.error("signals_log ilegivel no purge: %s", e)
        return 0
    mask = (df["origem"] == origem) & (df["symbol"].isin(symbols))
    removed = int(mask.sum())
    if removed:
        df = df[~mask].reset_index(drop=True)
        df.to_parquet(SIGNALS_LOG, index=False)
    logger.info("purge origem=%s symbols=%s: -%d linhas", origem, symbols, removed)
    return removed


def _load_closes(symbol: str) -> tuple[np.ndarray, np.ndarray] | None:
    path = CONSOLIDATED_DIR / f"{symbol}_M1.parquet"
    if not path.exists():
        return None
    try:
        df = pd.read_parquet(path, columns=["timestamp", "close"])
    except Exception as e:
        logger.error("%s: consolidado ilegivel: %s", symbol, e)
        return None
    ts = pd.to_numeric(df["timestamp"], errors="coerce").to_numpy()
    close = pd.to_numeric(df["close"], errors="coerce").to_numpy()
    order = np.argsort(ts)
    return ts[order], close[order]


def reconcile() -> dict[str, Any]:
    """Fecha outcomes de sinais pendentes (ts + 60min < now) e grava calibration.json."""
    result: dict[str, Any] = {"reconciled": 0, "status": "ok"}
    if not SIGNALS_LOG.exists():
        result["status"] = "sem_log"
        _write_calibration(pd.DataFrame(columns=COLUMNS))
        return result

    df = pd.read_parquet(SIGNALS_LOG)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    now = datetime.now(UTC)
    pend = df["outcome_60m_pips"].isna() & (df["ts"] < now - pd.Timedelta(minutes=60))
    if pend.any():
        from utils.orc_mercado import PIP_SPECS
        for sym, grp in df[pend].groupby("symbol"):
            loaded = _load_closes(sym)
            if loaded is None:
                continue
            ts_ms, closes = loaded
            ts_s = ts_ms / 1000.0
            spec = PIP_SPECS.get(sym, {})
            # R21: closes brutos cTrader — pip em unidade bruta (S34 v1.2 fix)
            pip_raw = spec.get("pip_size", 0.0001) * spec.get("price_divisor", 1)
            spread = SPREAD_PIPS.get(sym, 1.0)
            for idx in grp.index:
                row = df.loc[idx]
                entry_ts = row["ts"].timestamp()
                # barra de emissao = ultima barra fechada <= ts (side=right)
                pos = int(np.searchsorted(ts_s, entry_ts, side="right")) - 1
                if pos < 0:
                    continue
                entry_close = closes[pos]
                if entry_close <= 0:
                    continue
                bullish = row["sinal"] == "BULLISH"
                direction = 1.0 if bullish else -1.0
                for la in LOOKAHEADS:
                    tgt = pos + la
                    if tgt >= len(closes):
                        continue
                    # R21: spread na direcao do sinal — short paga tambem
                    pips = direction * (closes[tgt] - entry_close) / pip_raw - spread
                    pips = float(pips)
                    df.loc[idx, f"outcome_{la}m_pips"] = round(pips, 2)
                    df.loc[idx, f"acerto_{la}m"] = bool(pips > 0)
                result["reconciled"] += 1
        df.to_parquet(SIGNALS_LOG, index=False)
        logger.info("reconcile: %d sinais fechados", result["reconciled"])

    _write_calibration(df)
    return result


def calibration_summary(df: pd.DataFrame) -> dict[str, Any]:
    """Hit-rate por faixa (min 30 amostras), Brier por horizonte, drift, replay x live."""
    done = df.dropna(subset=["outcome_15m_pips"]) if len(df) else df
    out: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "total_signals": len(df),
        "reconciled_signals": len(done),
        "por_origem": {},
        "hit_rate_por_faixa": {},
        "brier": {},
        "drift": {},
    }
    if not len(done):
        return out

    for origem, grp in done.groupby("origem"):
        out["por_origem"][origem] = {
            "signals": len(grp),
            "hit_rate_15m": round(float(grp["acerto_15m"].mean()) * 100, 1)
            if grp["acerto_15m"].notna().any() else None,
        }

    done = done.copy()
    done["faixa"] = pd.cut(done["score"], bins=SCORE_BINS,
                           labels=["0-50", "50-70", "70-85", "85-100"])
    for faixa, grp in done.groupby("faixa", observed=True):
        n = len(grp)
        if n < MIN_SAMPLES:
            out["hit_rate_por_faixa"][str(faixa)] = {"n": n, "status": "amostra_insuficiente"}
            continue
        out["hit_rate_por_faixa"][str(faixa)] = {
            "n": n,
            "hit_5m": round(float(grp["acerto_5m"].mean()) * 100, 1),
            "hit_15m": round(float(grp["acerto_15m"].mean()) * 100, 1),
            "hit_60m": round(float(grp["acerto_60m"].mean()) * 100, 1),
        }

    for la in LOOKAHEADS:
        col = f"acerto_{la}m"
        ok = done.dropna(subset=[col, "score"])
        if len(ok) >= MIN_SAMPLES:
            prob = ok["score"] / 100.0
            out["brier"][f"{la}m"] = round(float(np.mean((prob - ok[col].astype(float)) ** 2)), 4)

    done["semana"] = done["ts"].dt.to_period("W").astype(str)
    drift = []
    for sem, grp in list(done.groupby("semana"))[-8:]:
        acc = grp.loc[grp["acerto_15m"] == True, "score"]  # noqa: E712
        err = grp.loc[grp["acerto_15m"] == False, "score"]  # noqa: E712
        if len(acc) >= 5 and len(err) >= 5:
            drift.append({"semana": sem,
                          "score_medio_acertos": round(float(acc.mean()), 1),
                          "score_medio_erros": round(float(err.mean()), 1)})
    out["drift"] = {"semanas": drift,
                    "alerta": bool(len(drift) >= 2 and
                                   abs(drift[-1]["score_medio_acertos"] -
                                       drift[-1]["score_medio_erros"]) < 5)}
    return out


def _write_calibration(df: pd.DataFrame) -> None:
    CALIBRATION_JSON.parent.mkdir(parents=True, exist_ok=True)
    payload = calibration_summary(df)
    CALIBRATION_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                                encoding="utf-8")
    logger.info("calibration.json gravado (%d sinais)", payload.get("total_signals", 0))


def main() -> None:
    ap = argparse.ArgumentParser(description="S36 orc_calibracao")
    ap.add_argument("--reconcile", action="store_true", help="fecha outcomes pendentes")
    args = ap.parse_args()
    if args.reconcile:
        r = reconcile()
        print(f"[CALIB] reconciliados: {r['reconciled']} ({r['status']})")
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
