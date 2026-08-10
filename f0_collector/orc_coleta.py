"""
PROPOSITO: Orquestrador F0 — PONTA DE LANCA. UNICO ponto MCP (dados + ordens).
SPEC: S2
ROADMAP: 1.6 + 5.1
FLOW:   F0 (dados+ordens) -> snapshot.json -> F1/F2/F3/F4/F5/dashboard
        F4 decide entrada/saida -> F0 executa create_order/close_position/amend_position
        F1/F2/F3/F5/dashboard leem snapshot, NUNCA chamam MCP direto.
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import time
from datetime import UTC as _UTC, datetime as _dt
from pathlib import Path
from typing import Any

from f0_collector.poller_orc_coleta import (
    SYMBOLS,
    poll_cycle,
    poll_tick,
)
from f0_collector.storage_orc_coleta import append_to_df, make_empty_df, save_parquet
from utils.config_loader import polling as _cfg_polling
from utils.logger import get_logger
from utils.mcp_client import (
    MCPConnectionError,
    MCPTimeoutError,
    amend_position,
    cancel_order,
    close_position,
    create_order,
    ensure_session_fresh,
    get_symbols,
    init_client,
)

logger = get_logger(__name__, "F0")

TICK_INTERVAL = _cfg_polling("tick_interval_s", 3)
CANDLE_INTERVAL = _cfg_polling("candle_interval_s", 60)
RECONNECT_MAX_RETRIES = 3

shutdown_flag = False


def _handle_signal(signum, frame):
    global shutdown_flag
    logger.info("Sinal recebido: %s. Encerrando...", signum)
    shutdown_flag = True


class Collector:
    def __init__(self, dry_run: bool = False, data_dir: str = "data"):
        self.dry_run = dry_run
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.df = make_empty_df()
        self.last_candle_poll = 0.0
        self.last_snapshot = 0.0
        self.consecutive_errors = 0
        self.start_time = time.monotonic()

    def _resolve_symbols(self, max_retries: int = 3) -> bool:
        """Resolve simbolos com retry (MCP intermitente)."""
        import time as _t
        for attempt in range(1, max_retries + 1):
            try:
                symbols = get_symbols()
                available = set()
                if isinstance(symbols, list):
                    for s in symbols:
                        if isinstance(s, dict):
                            available.add(s.get("symbolName", ""))
                for sym in SYMBOLS:
                    if sym not in available:
                        logger.error("Simbolo nao encontrado: %s", sym)
                if len(available) > 0:
                    logger.info("Simbolos resolvidos: %d (tentativa %d/%d)", len(available), attempt, max_retries)
                    return True
                logger.error("Tentativa %d/%d: lista vazia", attempt, max_retries)
            except Exception as e:
                logger.error("Tentativa %d/%d falhou: %s", attempt, max_retries, str(e)[:80])
            if attempt < max_retries:
                wait = 2 ** (attempt - 1)  # 1s, 2s, 4s backoff
                _t.sleep(wait)
        return False

    def run(self, hours: float = 0):
        logger.info("=== F0 COLECTOR INICIADO === dry_run=%s horas=%s", self.dry_run, hours or "infinito")

        # Inicializa MCP (handshake obrigatório)
        try:
            init_client()
        except Exception as e:
            logger.error("Falha ao inicializar MCP: %s", e)
            return

        if not self._resolve_symbols():
            logger.error("Falha ao resolver simbolos. Abortando.")
            return

        # S2.5 — semeia M_1 (200 velas/simbolo) para o VBT sair no 1o ciclo
        _warmup_m1()

        deadline = time.monotonic() + hours * 3600 if hours > 0 else float("inf")
        last_save = time.monotonic()

        while not shutdown_flag and time.monotonic() < deadline:
            try:
                now = time.monotonic()

                # SESSION LIFECYCLE: renova MCP a cada 5 min (expira em ~7-8 min server-side)
                ensure_session_fresh("config.yaml")

                # SPEC S2 "DOIS CAMINHOS": append_to_df() espera o dict-POR-SIMBOLO
                # do poll_cycle(). Antes recebia poll_candles(sym) (UMA barra), entao
                # candle_data.get(sym) falhava sempre e todo OHLC do parquet caia no
                # fallback de spot (open==close==bid, volume=0) -- 885 linhas sem uma
                # candle real. Fonte unica agora: o mesmo poll_cycle() do snapshot.
                cycle = poll_cycle() if now - self.last_candle_poll >= CANDLE_INTERVAL else {}
                for sym in SYMBOLS:
                    tick = poll_tick(sym)
                    if tick:
                        self.df = append_to_df(
                            self.df, tick,
                            cycle,
                            0.5, 0.0,
                        )

                if now - self.last_candle_poll >= CANDLE_INTERVAL:
                    self.last_candle_poll = now
                    # S36 MODO PRESENTE: a cada barra M1 fechada, reemite o score
                    # (score_live.json -> /metrics score_mercados). Opcional: falha
                    # NUNCA quebra o ciclo F0 (mesmo padrao take_snapshot/S27 VBT).
                    try:
                        from utils.signal_emitter_orc_score import emit_once
                        emit_once()
                    except Exception as e:
                        logger.error("Emissor S36 falhou (ciclo segue): %s", e)

                if now - last_save >= 3600:
                    save_parquet(self.df, str(self.data_dir))
                    last_save = now

                if now - self.last_snapshot >= TICK_INTERVAL:
                    # ROADMAP 1.6/1.7: publica status/snapshot.json a cada tick —
                    # F1..F5 e dashboard leem daqui (R-NO-MCP-BYPASS). Sem isso,
                    # take_snapshot() nunca era chamado em producao (so em teste).
                    try:
                        take_snapshot()
                    except Exception as e:
                        logger.error("Falha ao publicar snapshot: %s", e)
                    self.last_snapshot = now

                self.consecutive_errors = 0

            except (MCPConnectionError, MCPTimeoutError) as e:
                self.consecutive_errors += 1
                logger.error("Erro MCP (%d/%d): %s", self.consecutive_errors, RECONNECT_MAX_RETRIES, e)
                if self.consecutive_errors >= RECONNECT_MAX_RETRIES:
                    logger.error("Reconectando MCP (force)...")
                    init_client("config.yaml", force=True)
                    time.sleep(2)
                    self.consecutive_errors = 0
                else:
                    time.sleep(1)

            time.sleep(TICK_INTERVAL)

        save_parquet(self.df, str(self.data_dir))
        uptime = time.monotonic() - self.start_time
        logger.info("=== F0 COLECTOR ENCERRADO === uptime=%.0fs linhas=%d", uptime, len(self.df))


_PID_PATH = Path(__file__).resolve().parent.parent / "status" / "f0.pid"


def _write_pid_file() -> None:
    """Auto-registro: F0 grava o proprio PID, seja qual for quem o iniciou
    (boot .ps1 ou dashboard f0_start()) — evita cacada manual de PID (ROADMAP 1.8)."""
    _PID_PATH.parent.mkdir(parents=True, exist_ok=True)
    _PID_PATH.write_text(str(os.getpid()), encoding="utf-8")


def _remove_pid_file() -> None:
    _PID_PATH.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description="F0 Coletor — cTrader MCP")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--hours", type=float, default=0)
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--data-dir", default="data")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    # ROADMAP 1.7c: signal.signal so funciona na main thread. Registrar aqui
    # (nao no import do modulo) -- o dashboard importa get_snapshot()/take_snapshot()
    # de dentro de uma worker thread do FastAPI, e um registro a nivel de modulo
    # derrubava esse import (ValueError, silenciosamente engolido por
    # _get_snapshot_safe() -- fazia /health mentir "F0 offline" mesmo com F0 vivo).
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)
    _write_pid_file()
    try:
        init_client(args.config)
        collector = Collector(dry_run=args.dry_run, data_dir=args.data_dir)
        collector.run(hours=args.hours)
    finally:
        _remove_pid_file()


# ---------------------------------------------------------------------------
# Snapshot hub (ROADMAP 1.6) — F1/F4/F5/dashboard consomem daqui
# ---------------------------------------------------------------------------
import json as _json
from typing import Any as _Any

_SNAPSHOT_PATH = Path(__file__).resolve().parent.parent / "status" / "snapshot.json"


def take_snapshot() -> dict[str, _Any]:
    """Coleta 1 ciclo dos 5 ativos + balance + posicoes e persiste em snapshot.json.
    F1/F4/F5/dashboard leem este snapshot em vez de chamar MCP direto.
    ROADMAP 1.6 + 1.7: F0 como unico pull point de todos os dados MCP.
    """
    Path(_SNAPSHOT_PATH).parent.mkdir(parents=True, exist_ok=True)
    cycle = poll_cycle()

    # Balance e posicoes: F0 puxa 1x por ciclo (ROADMAP 1.7)
    balance_raw: dict[str, _Any] = {}
    positions: list[dict[str, _Any]] = []
    try:
        from utils.mcp_client import get_balance, get_positions, init_client
        config_path = Path(__file__).resolve().parent.parent / "config.yaml"
        if config_path.exists():
            init_client(str(config_path))
            balance_raw = get_balance()
            positions = get_positions()
    except Exception:
        logger.info("F0: balance/positions offline (MCP indisponivel)")

    # S25.11 / S39 - Trendbars removido. MTF deve ser calculado por resample()
    # local do M1, preservando o padrao ouro de nao sobrecarregar o MCP.
    trendbars: dict[str, dict[str, list[dict[str, _Any]]]] = {}

    snapshot = {
        "timestamp_utc": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "symbols": cycle,
        "balance": balance_raw,
        "positions": positions,
        "online": bool(balance_raw),
        "trendbars": trendbars,
    }
    # -- Escreve snapshot atomico --
    _SNAPSHOT_PATH.write_text(_json.dumps(snapshot, indent=2, default=str), encoding="utf-8")
    logger.info("Snapshot salvo: %d simbolos, balance=%s, positions=%d, trendbars=%d",
                len(cycle), "OK" if balance_raw else "OFFLINE", len(positions), len(trendbars))

    # -- S2.5: Persiste M_1 no Parquet (banco historico) --
    _persist_parquet(cycle, bool(balance_raw))

    return snapshot

WARMUP_BARS = 200  # S2.5: semeia M_1 no boot — VBT sai no 1o ciclo (min 50 barras)


def _persist_m1_rows(sym: str, rows: list[dict[str, Any]]) -> None:
    """Append + dedup de velas M_1 no parquet do simbolo e recomputa VBT.

    VBT calculado sobre o HISTORICO (ultimas 200 velas M_1 do parquet), nunca
    sobre a vela solta do ciclo — compute_indicators exige >= 50 barras.

    S39/C4: apos M1 VBT, resample M1->M5/M15 e persiste indicadores MTF.
    """
    import pandas as _pd

    from f0_collector.storage_orc_coleta import (
        append_rows as _append,
        make_empty_df as _empty,
    )

    if not rows:
        return
    data_dir = _SNAPSHOT_PATH.resolve().parent.parent / "data"
    try:
        year = _dt.fromtimestamp(int(rows[-1]["timestamp"]) / 1000, tz=_UTC).year
        m1_path = data_dir / f"m1_{sym}_{year}.parquet"
        df = _pd.read_parquet(m1_path) if m1_path.exists() else _empty()
        df["timestamp"] = _pd.to_numeric(df["timestamp"], errors="coerce")
        df = _append(df, rows)
        df = df.sort_values("timestamp").drop_duplicates(subset=["timestamp"], keep="last")
        df.to_parquet(m1_path, index=False)

        # S27 — VBT sobre o historico (min 50 barras); opcional, nao quebra o ciclo
        if len(df) >= 50:
            try:
                from utils.orc_vectorbt import compute_indicators
                from utils.storage_orc_vbt import save_indicators

                bars = df.tail(200)[["open", "high", "low", "close", "tick_volume", "timestamp"]]
                bars = bars.rename(columns={"tick_volume": "volume"}).to_dict(orient="records")
                ind = compute_indicators({sym: bars}).get(sym, {})
                if ind and not ind.get("error"):
                    save_indicators(sym, ind, ts=int(df["timestamp"].iloc[-1]) // 1000)

                # S39/C4 — MTF: resample M1->M5/M15 e persiste indicadores por timeframe
                try:
                    from utils.orc_vectorbt import compute_indicators_mtf
                    from utils.storage_orc_vbt import save_indicators_mtf

                    df_m1 = df.tail(200).copy()
                    mtf_ind = compute_indicators_mtf(df_m1, timeframes=("M5", "M15"))
                    m1_only = {k: v for k, v in mtf_ind.items() if k in ("M5", "M15")}
                    save_indicators_mtf(sym, m1_only, ts=int(df["timestamp"].iloc[-1]) // 1000)
                except Exception as e_mtf:
                    logger.error("VBT MTF persist %s falhou: %s", sym, e_mtf)

            except Exception as e:
                logger.error("VBT persist %s falhou: %s", sym, e)
    except Exception as e:
        logger.error("Parquet persist %s falhou: %s", sym, e)


def _candle_to_row(sym: str, candle: dict[str, Any]) -> dict[str, Any] | None:
    """Normaliza 1 candle (poll_cycle ou trendbars) para o schema M_1."""
    ts_raw = candle.get("timestamp", 0)
    if isinstance(ts_raw, str):
        ts_ms = int(_dt.fromisoformat(ts_raw.replace("Z", "+00:00")).timestamp() * 1000)
    elif float(ts_raw) < 1e10:  # segundos -> ms
        ts_ms = int(float(ts_raw) * 1000)
    else:
        ts_ms = int(float(ts_raw))
    if ts_ms <= 0:
        return None
    return {
        "timestamp": ts_ms,
        "symbol": sym,
        "open": candle.get("open", 0),
        "high": candle.get("high", 0),
        "low": candle.get("low", 0),
        "close": candle.get("close", 0),
        "tick_volume": candle.get("tick_volume", candle.get("tickVolume", 0)),
        "spread": candle.get("spread", 0),
        "bid": candle.get("bid", 0),
        "ask": candle.get("ask", 0),
        "dom_bid_wall": candle.get("dom_bid_wall", 0),
        "dom_ask_wall": candle.get("dom_ask_wall", 0),
        "sentiment_ratio": candle.get("sentiment_ratio", 0.0),
        "dxy_close": candle.get("dxy_close", 0.0),
    }


def _persist_parquet(cycle: dict[str, dict[str, Any]], _online: bool) -> None:
    """S2.5 — Append cada candle M_1 no Parquet acumulativo + indicadores VBT."""
    for sym, candle in cycle.items():
        if not isinstance(candle, dict):
            continue
        try:
            row = _candle_to_row(sym, candle)
            if row:
                _persist_m1_rows(sym, [row])
        except Exception as e:
            logger.error("Parquet persist %s falhou: %s", sym, e)


def _warmup_m1() -> None:
    """S2.5 — semeia o parquet M_1 no boot: ultimas N velas via get_trendbars.

    Sem isso o VBT so saia apos 50+ min de acumulo live. 1 req/simbolo,
    throttle natural do mcp_client. Falha nao bloqueia o F0.
    """
    from utils.mcp_client import get_trendbars

    for sym in SYMBOLS:
        try:
            result = get_trendbars(symbol=sym, timeframe="m1", count=WARMUP_BARS)
            bars = result if isinstance(result, list) else result.get("trendbars", result.get("bars", []))
            rows = [r for r in (_candle_to_row(sym, b) for b in bars if isinstance(b, dict)) if r]
            _persist_m1_rows(sym, rows)
            logger.info("Warmup M_1 %s: %d velas semeadas", sym, len(rows))
        except Exception as e:
            logger.error("Warmup M_1 %s falhou: %s", sym, e)


def get_snapshot() -> dict[str, _Any] | None:
    """Le snapshot mais recente do disco. Retorna None se nao existir."""
    if not _SNAPSHOT_PATH.exists():
        return None
    try:
        return _json.loads(_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None

# -- ORDER HUB (ROADMAP 5.1) — F4 decide, F0 executa --

def place_order(symbol: str, side: str, volume: float,
                sl_pips: int = 0, tp_pips: int = 0) -> dict[str, Any]:
    """Entrada: F4 decide, F0 encaminha ao MCP."""
    logger.info("F0: place_order %s %s vol=%s sl=%s tp=%s", symbol, side, volume, sl_pips, tp_pips)
    return create_order(symbol=symbol, side=side, volume=volume,
                        order_type="MARKET", sl=sl_pips, tp=tp_pips)


def exit_position(position_id: str, volume: float | None = None) -> dict[str, Any]:
    """Saida: F4 decide, F0 encaminha ao MCP."""
    logger.info("F0: exit_position %s vol=%s", position_id, volume)
    return close_position(position_id=position_id, volume=volume)


def move_stops(position_id: str, sl: float | None = None, tp: float | None = None) -> dict[str, Any]:
    """Trail/BE: F4 decide, F0 encaminha ao MCP."""
    logger.info("F0: move_stops %s sl=%s tp=%s", position_id, sl, tp)
    return amend_position(position_id=position_id, sl=sl, tp=tp)


def kill_pending(order_id: str) -> dict[str, Any]:
    """Kill switch: F4 decide, F0 encaminha ao MCP."""
    logger.info("F0: kill_pending %s", order_id)
    return cancel_order(order_id=order_id)


if __name__ == "__main__":
    main()
