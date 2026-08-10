"""PROPOSITO: Backfill 2 anos M_1 para os 7 simbolos cTrader V2.
SPEC: S2.5
ROADMAP: 1.3
R-USE: storage_orc_coleta.save_backfill_parquet() + mcp_client.get_trendbars()

v2.1 (2026-08-06): merge de gaps adjacentes (threshold 4h) — reduz chamadas MCP
  Ex: 162 gaps XAUUSD -> ~30 ranges. Respeita throttle 5 req/s.

Pipeline:
  1. Conecta MCP
  2. Para cada simbolo, pagina get_trendbars(sym, "M_1", from, to) PARA TRAS
     (o servidor devolve as N barras mais recentes da janela — S1.1):
     count=1000/pagina, span ~3000min (margem fds), cursor retrocede ate
     cobrir o range. Throttle 5 req/s.
  3. Acumula em DataFrame pandas
  4. Salva via storage_orc_coleta.save_backfill_parquet()
  5. Resultado: data/backfill/XAUUSD_M1.parquet (7 arquivos)

Tempo estimado: ~750 paginas/simbolo (2 anos M_1 / 1000 barras) x 7 simbolos
/ 5 req/s = ~17 min total (~2,5 min/simbolo).

Resume: se o arquivo ja existe, pula periodos ja cobertos (timestamp incremental).

Modo --gaps (S31): le status/gap_report.json (gerado pelo G23) e busca
APENAS as janelas lacunares, gravando direto no consolidado
data/consolidated/{SYM}_M1.parquet. Converge: cada run preenche so o que falta.
v2.1: funde gaps adjacentes (<4h) antes de paginar — reduz chamadas MCP em ~5x.
"""
from __future__ import annotations

import json
import logging
import math
import os
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from f0_collector.storage_orc_coleta import (
    append_rows,
    make_empty_df,
    save_backfill_parquet,
)
from utils.mcp_client import (
    ensure_session_fresh,
    get_balance,
    get_trendbars,
    init_client,
)

logger = logging.getLogger("backfill")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

SYMBOLS = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD"]
INDEX_SYMBOLS = ["DXYUSD", "VIXUSD"]
BACKFILL_YEARS = 2
WINDOW_DAYS = 30  # max 30d/janela do MCP
THROTTLE_RPS = 5  # req/s - respeita limite do servidor
OUTPUT_DIR = ROOT / "data" / "backfill"
PROGRESS_PATH = ROOT / "status" / "backfill_progress.json"
_PID_PATH = ROOT / "status" / "backfill.pid"

_PROGRESS: dict[str, Any] = {}


def _write_progress(**kw: Any) -> None:
    """Publica progresso em status/backfill_progress.json (S31-PROG).

    Dashboard (/backfill/status), S33 (orc_health_fases) e orc_metricas leem
    este arquivo — nenhum consumidor toca MCP nem o processo diretamente.
    """
    _PROGRESS.update(kw)
    _PROGRESS["updated_at"] = datetime.now(UTC).isoformat()
    try:
        PROGRESS_PATH.write_text(
            json.dumps(_PROGRESS, indent=2, default=str), encoding="utf-8"
        )
    except OSError as e:
        logger.error("progresso nao gravado: %s", e)


def _progress_start(mode: str) -> None:
    """Inicializa o contrato de progresso no inicio do run."""
    _PROGRESS.clear()
    _write_progress(
        state="running",
        mode=mode,
        started_at=datetime.now(UTC).isoformat(),
        current_symbol=None,
        symbols={s: {"windows_done": 0, "windows_total": 0, "bars": 0,
                     "state": "pending"} for s in SYMBOLS + INDEX_SYMBOLS},
        totals={"windows_done": 0, "windows_total": 0, "bars": 0, "pct": 0.0},
        elapsed_s=0.0,
        eta_s=None,
        last_error=None,
    )


def _progress_tick(t0: float) -> None:
    """Recalcula totais/pct/ETA a cada pagina.

    windows_total e ESTIMADO (paginas de 1000 barras) — done pode passar de
    total; pct e capado em 100 e eta nunca negativo.
    """
    syms = _PROGRESS.get("symbols", {})
    done = sum(s["windows_done"] for s in syms.values())
    total = sum(s["windows_total"] for s in syms.values())
    bars = sum(s["bars"] for s in syms.values())
    elapsed = time.monotonic() - t0
    eta = round(max(0.0, elapsed / done * (total - done)), 0) if done else None
    _write_progress(
        totals={"windows_done": done, "windows_total": total,
                "bars": bars, "pct": round(min(100.0, done / total * 100), 1) if total else 0.0},
        elapsed_s=round(elapsed, 1),
        eta_s=eta,
    )


def _build_windows(start: datetime, end: datetime) -> list[tuple[str, str]]:
    """Divide o periodo em janelas de WINDOW_DAYS."""
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    windows: list[tuple[str, str]] = []
    cursor = start
    while cursor < end:
        next_end = min(cursor + timedelta(days=WINDOW_DAYS), end)
        windows.append((cursor.strftime(fmt), next_end.strftime(fmt)))
        cursor = next_end
    return windows


def _fetch_window(symbol: str, from_ts: str, to_ts: str) -> list[dict[str, Any]]:
    """Busca uma janela de trendbars M_1. Retorna lista de dicts.

    mcp_client.get_trendbars() JA devolve a lista de barras (S1.1) —
    NAO e dict com chave "trendbars".

    v2.2: retry com backoff exponencial (3 tentativas, 2s->4s->8s).
    """
    import time as _time
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # v2.7: renova sessao antes de cada chamada MCP
            if not ensure_session_fresh(str(ROOT / "config.yaml")):
                logger.error("Sessao MCP nao renova em _fetch_window")
            result = get_trendbars(
                symbol, "M_1",
                count=1000,
                from_timestamp=from_ts,
                to_timestamp=to_ts,
            )
            return result if isinstance(result, list) else []
        except Exception as e:
            if attempt < max_retries - 1:
                wait = 2 ** (attempt + 1)  # 2s, 4s
                logger.info(
                    "Retry %d/%d para %s [%s -> %s] em %ds: %s",
                    attempt + 1, max_retries, symbol, from_ts[:10], to_ts[:10], wait, e,
                )
                _time.sleep(wait)
                # v2.8: no ultimo retry, force-reconnect
                if attempt == max_retries - 2:
                    logger.info("Force-reconnect no ultimo retry...")
                    import utils.mcp_client as mcp
                    mcp._mcp_initialized = False
                    mcp._mcp_session_id = ""
                    mcp._mcp_url = ""
                    init_client(str(ROOT / "config.yaml"), force=True)
            else:
                logger.error("Falha ao buscar %s [%s -> %s]: %s", symbol, from_ts[:10], to_ts[:10], e)
                return []


def _iter_pages(symbol: str, g_start: datetime, g_end: datetime):
    """Pagina um range PARA TRAS, em paginas de ate 1000 barras (S1.1:
    o servidor devolve as N barras mais recentes da janela [from, to]).

    Cada pagina pede count=1000 com span ~3000min (1000 barras M_1 x3 de
    margem p/ fds — mesmo heuristico do mcp_client). O cursor retrocede
    para (barra mais antiga recebida - 1min) ate cobrir g_start.

    Anti-loop: aborta o range se a pagina nao retroceder o cursor ou se
    houver 5 paginas vazias seguidas (ex.: inicio do historico do ativo).
    Throttle 1/THROTTLE_RPS por requisicao (respeita o servidor).
    """
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    span = timedelta(minutes=3000)
    to = g_end
    empty_streak = 0
    while to > g_start:
        frm = max(g_start, to - span)
        bars = _fetch_window(symbol, frm.strftime(fmt), to.strftime(fmt))
        # Throttle so se necessario: latencia de rede ja nos mantem <5 req/s
        ts_ms = [int(b["timestamp"]) for b in bars if b.get("timestamp")]
        if not ts_ms:
            empty_streak += 1
            if empty_streak > 5:
                logger.info(
                    "%s: %d paginas vazias seguidas - resto do range abortado "
                    "(provavel inicio do historico do ativo)", symbol, empty_streak,
                )
                return
            to = frm - timedelta(minutes=1)
            continue
        empty_streak = 0
        earliest = min(ts_ms)
        # Yield PRIMEIRO: a barra da borda (earliest == to) e dado legitimo.
        # A guarda so impede LOOP — se a pagina nao retrocede o cursor,
        # entrega o que veio e encerra o range (ex.: janela de pausa diaria
        # em que so existe a barra da reabertura).
        yield bars
        if earliest >= int(to.timestamp() * 1000):
            logger.info(
                "%s: pagina na borda do cursor (earliest==to) - range concluido", symbol,
            )
            return
        to = datetime.fromtimestamp(earliest / 1000, tz=UTC) - timedelta(minutes=1)


def _bars_to_rows(symbol: str, bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Converte trendbars MCP -> schema Parquet."""
    rows: list[dict[str, Any]] = []
    for b in bars:
        # MCP Remote retorna campos camelCase
        rows.append({
            "timestamp": b.get("timestamp", 0),
            "symbol": symbol,
            "open": b.get("open", 0),
            "high": b.get("high", 0),
            "low": b.get("low", 0),
            "close": b.get("close", 0),
            "tick_volume": b.get("tickVolume", b.get("tick_volume", 0)),
            "spread": 0,
            "bid": 0,
            "ask": 0,
            "dom_bid_wall": 0,
            "dom_ask_wall": 0,
            "sentiment_ratio": 0.0,
            "dxy_close": 0.0,
        })
    return rows


def backfill_symbol(symbol: str, t0: float | None = None) -> Path:
    """Backfill completo de um simbolo. Retorna path do Parquet salvo."""
    t0 = t0 or time.monotonic()
    end = datetime.now(UTC)
    start = end - timedelta(days=BACKFILL_YEARS * 365)

    # Resume: carrega existente se houver
    df = make_empty_df()
    existing = OUTPUT_DIR / f"{symbol}_M1.parquet"
    if existing.exists():
        try:
            df_existing = pd.read_parquet(existing)
            if "timestamp" in df_existing.columns:
                last_ts = df_existing["timestamp"].max()
                if isinstance(last_ts, (int, float)) and last_ts > 0:
                    start = datetime.fromtimestamp(last_ts / 1000, tz=UTC) + timedelta(seconds=1)
                    df = df_existing
                    logger.info("Resume %s: ja tem ate %s (%d linhas)", symbol, start.isoformat()[:10], len(df))
        except Exception:
            logger.info("Resume %s: arquivo ilegivel, recomecando do zero", symbol)

    total_bars = 0
    # Estimativa de paginas (1000 barras/pagina; ~72% dos minutos sao pregao)
    minutes_total = (end - start).total_seconds() / 60
    est_pages = max(1, math.ceil(minutes_total * 0.72 / 1000))

    sym_prog = _PROGRESS.get("symbols", {}).get(symbol)
    if sym_prog is not None:
        sym_prog["windows_total"] = est_pages
        sym_prog["state"] = "running"
    _write_progress(current_symbol=symbol, symbols=_PROGRESS.get("symbols", {}))

    for bars in _iter_pages(symbol, start, end):
        rows = _bars_to_rows(symbol, bars)
        df = append_rows(df, rows)
        total_bars += len(rows)

        if sym_prog is not None:
            sym_prog["windows_done"] += 1
            sym_prog["bars"] = total_bars
        _progress_tick(t0)

        if sym_prog is not None and sym_prog["windows_done"] % 100 == 0:
            logger.info("  %s: %d/~%d paginas, %d barras",
                        symbol, sym_prog["windows_done"], est_pages, total_bars)

    # Salva
    path = save_backfill_parquet(df, str(OUTPUT_DIR.parent), symbol)
    if sym_prog is not None:
        sym_prog["state"] = "done"
        _progress_tick(t0)
    logger.info("%s: CONCLUIDO - %d barras em %.0fs -> %s", symbol, total_bars, time.monotonic() - t0, path)
    return path


def _health_check_mcp(reinit: bool = True) -> bool:
    """Pinga o MCP com get_balance(). Se falhar, re-inicializa com force.

    v2.4: reconexao PROATIVA — se sessao tem >7 min, refaz handshake antes de expirar.
    Sessao cTrader MCP expira em ~8-10 min independente de atividade (server-side).
    """
    try:
        bal = get_balance()
        return bool(bal)
    except Exception:
        if reinit:
            logger.info("MCP inativo — re-inicializando sessao (force)...")
            config = ROOT / "config.yaml"
            if config.exists():
                try:
                    # Reseta estado global do mcp_client
                    import utils.mcp_client as mcp
                    mcp._mcp_initialized = False
                    mcp._mcp_session_id = ""
                    mcp._mcp_url = ""
                    init_client(str(config), force=True)
                    global _last_handshake
                    _last_handshake = time.monotonic()
                    logger.info("MCP re-conectado (force)")
                    return True
                except Exception as e2:
                    logger.info("Falha ao re-conectar MCP: %s", e2)
        return False


# Session freshness — delegado ao utils.mcp_client.ensure_session_fresh() (SSOT)
# SESSION_MAX_AGE=300s, get_session_age() para health check




def _update_gap_report_incremental(
    report_path: Path, symbol: str, current_idx: int, gap_ranges: list, total_ranges: int
) -> None:
    """Atualiza gap_report.json removendo ranges ja preenchidos.

    Apos processar `current_idx` ranges de `total_ranges`, reescreve o
    gap_report para o simbolo contendo apenas os ranges RESTANTES
    (current_idx+1 ate total_ranges). Se todos foram preenchidos,
    remove o simbolo do report.
    """
    if not report_path.exists():
        return

    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception:
        return

    remaining = current_idx  # ranges ja processados
    if remaining >= total_ranges:
        # Todos preenchidos — remove simbolo do report
        report["symbols"].pop(symbol, None)
    else:
        # Atualiza ranges do simbolo: so os nao preenchidos
        sym_data = report["symbols"].get(symbol, {})
        # Cada gap_range original foi merged em N ranges
        # Simplificacao: recalcula gaps restantes baseado nos ranges
        remaining_ranges = gap_ranges[current_idx:]  # ranges ainda nao processados
        new_gaps = []
        for g_start, g_end in remaining_ranges:
            new_gaps.append({
                "start_ms": int(g_start.timestamp() * 1000),
                "end_ms": int(g_end.timestamp() * 1000),
            })
        sym_data["gaps"] = new_gaps
        sym_data["gaps_count"] = len(new_gaps)
        sym_data["total_gaps"] = len(new_gaps)  # C2: recalcula total_gaps apos remocao
        report["symbols"][symbol] = sym_data

    report["updated_at"] = datetime.now(UTC).isoformat()
    report["_partial"] = True  # marca como checkpoint parcial
    report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")


def fill_gaps() -> int:
    """Modo --gaps (S31): preenche APENAS as lacunas do gap_report no consolidado.

    Unico ponto MCP do fluxo S31 (R-NO-MCP-BYPASS). Converge: cada run
    busca so as janelas que o G23 marcou como lacuna.

    v3.1: Ctrl+C -> salva parcial, resume, nao fecha.
    """
    import signal as _signal

    _interrupted = False
    _current_sym = ""

    def _on_ctrl_c(signum, frame):
        nonlocal _interrupted
        _interrupted = True
        print(f"\n[CTRL+C] Salvando parcial de {_current_sym}...", flush=True)

    _signal.signal(_signal.SIGINT, _on_ctrl_c)

    report_path = ROOT / "status" / "gap_report.json"
    if not report_path.exists():
        print("[ERR] gap_report.json ausente - rode antes:")
        print("      python gates/run_consolidate_parquet.py")
        return 1

    report = json.loads(report_path.read_text(encoding="utf-8"))
    symbols_report = report.get("symbols", {})

    config = ROOT / "config.yaml"
    if not config.exists():
        print("[FAIL] config.yaml nao encontrado. Execute da raiz do ctrader.")
        return 1
    init_client(str(config))
    logger.info("MCP conectado. Preenchendo lacunas...")
    print("[BACKFILL] Iniciando preenchimento...", flush=True)
    _last_handshake = time.monotonic()  # v2.4: track session age

    _progress_start("gaps")
    t0 = time.monotonic()
    _PID_PATH.write_text(str(os.getpid()), encoding="utf-8")

    consolidated_dir = ROOT / "data" / "consolidated"
    consolidated_dir.mkdir(parents=True, exist_ok=True)

    try:
        for sym in SYMBOLS + INDEX_SYMBOLS:
            gaps = symbols_report.get(sym, {}).get("gaps", [])
            sym_prog = _PROGRESS["symbols"][sym]
            if not gaps:
                sym_prog["state"] = "done"
                print(f"  [OK] {sym}: sem lacunas a preencher")
                continue

            # Pre-conta paginas estimadas de todas as lacunas do simbolo
            # (1 pagina = ate 1000 barras M_1; missing_minutes ja desconta fds)
            # v2.3: merge por threshold (26h) — NUNCA funde tudo em 1 range
            # pois re-baixaria dados ja existentes. Gaps proximos (<26h) viram
            # ranges maiores; gaps distantes ficam separados.
            merge_threshold_h = 26  # cobre fds + feriados
            merge_ms = merge_threshold_h * 3600 * 1000
            sorted_gaps = sorted(gaps, key=lambda g: g["start_ms"])
            merged_ranges: list[tuple[int, int]] = []
            for g in sorted_gaps:
                g_start = g["start_ms"]
                g_end = g["end_ms"]
                if merged_ranges and g_start - merged_ranges[-1][1] <= merge_ms:
                    merged_ranges[-1] = (merged_ranges[-1][0], max(merged_ranges[-1][1], g_end))
                else:
                    merged_ranges.append((g_start, g_end))
            if len(merged_ranges) < len(gaps):
                print(f"  [MERGE] {sym}: {len(gaps)} gaps -> {len(merged_ranges)} ranges "
                      f"(threshold={merge_threshold_h}h)")

            # Converte ranges para datetime e estima paginas
            gap_ranges: list[tuple[datetime, datetime]] = []
            est_pages = 0
            for ms_start, ms_end in merged_ranges:
                g_start = datetime.fromtimestamp(ms_start / 1000, tz=UTC)
                g_end = datetime.fromtimestamp(ms_end / 1000, tz=UTC) + timedelta(minutes=1)
                gap_ranges.append((g_start, g_end))
                range_minutes = (ms_end - ms_start) / 60_000
                est_pages += max(1, math.ceil(range_minutes / 1000))

            sym_prog["windows_total"] = est_pages
            sym_prog["state"] = "running"
            _write_progress(current_symbol=sym, symbols=_PROGRESS["symbols"])

            # Preflight por simbolo: handshake + ping + rate
            ensure_session_fresh(str(ROOT / "config.yaml"))
            _hs_start = time.monotonic()
            if not _health_check_mcp():
                logger.error("MCP health check falhou para %s — pulando", sym)
                sym_prog["state"] = "error"
                continue
            _hs_time = time.monotonic() - _hs_start
            print(f"  [PREFLIGHT] {sym}: HS={_hs_time:.1f}s | sessao renovada", flush=True)

            # Health check antes de cada simbolo
            if not _health_check_mcp():
                logger.error("MCP indisponivel — pulando %s", sym)
                sym_prog["state"] = "error"
                _write_progress(last_error=f"MCP offline em {sym}")
                continue

            cons_path = consolidated_dir / f"{sym}_M1.parquet"
            df = pd.read_parquet(cons_path) if cons_path.exists() else make_empty_df()

            # v2.5: indices (DXYUSD/VIXUSD) tem DatetimeIndex sem coluna 'timestamp'
            # Converte index -> coluna para evitar perda de dados no drop_duplicates
            if len(df) and "timestamp" not in df.columns and isinstance(df.index, pd.DatetimeIndex):
                df["timestamp"] = (df.index.astype("int64") // 1_000_000).astype("int64")
                df = df.reset_index(drop=True)

            # Guarda G23: ignora linhas-lixo (timestamp epoch 0) herdadas de runs antigos
            if len(df) and "timestamp" in df.columns:
                df = df[pd.to_numeric(df["timestamp"], errors="coerce").fillna(0) > 0]
                df = df.reset_index(drop=True)
            total_new = 0
            _last_hc = time.monotonic()
            total_ranges = len(gap_ranges)

            for rg_idx, (g_start, g_end) in enumerate(gap_ranges, 1):
                # v2.6: renova sessao MCP a cada range
                if not ensure_session_fresh(str(ROOT / "config.yaml")):
                    logger.error("Sessao MCP nao renova — salvando parcial de %s", sym)
                    break
                range_bars = 0
                g_start_str = g_start.strftime("%Y-%m-%d")
                g_end_str = g_end.strftime("%Y-%m-%d")
                for bars in _iter_pages(sym, g_start, g_end):
                    df = append_rows(df, _bars_to_rows(sym, bars))
                    total_new += len(bars)
                    range_bars += len(bars)
                    sym_prog["windows_done"] += 1
                    sym_prog["bars"] = total_new
                    _progress_tick(t0)
                    # Health check a cada 60s durante downloads longos
                    if time.monotonic() - _last_hc > 60:
                        if not _health_check_mcp():
                            logger.error("MCP caiu durante backfill de %s — salvando parcial", sym)
                            break
                        _last_hc = time.monotonic()
                # Progresso por range
                if range_bars > 0:
                    print(f"  [{rg_idx}/{total_ranges}] {g_start_str}->{g_end_str}: "
                          f"+{range_bars} barras OK", flush=True)

                # v3.0: salva parcial a cada 10 ranges (persistencia anti-Ctrl+C)
                if rg_idx % 10 == 0 and total_new > 0:
                    df_save = df.sort_values("timestamp").drop_duplicates(subset=["timestamp"], keep="last")
                    df_save.to_parquet(cons_path, index=False)
                    # v3.1: atualiza gap_report incremental — so ranges NAO preenchidos
                    _update_gap_report_incremental(report_path, sym, rg_idx, gap_ranges, total_ranges)
                    print(f"  [SAVE] range {rg_idx}/{total_ranges} -> {len(df_save):,} linhas no disco", flush=True)

            if total_new == 0:
                # Nao e erro: lacunas em periodo SEM PREGAO (pausa diaria
                # 21-22h UTC, feriados) — o servidor nao tem barras ali.
                # Se o MCP estivesse fora, TODOS os simbolos zerariam
                # (verificado no resumo final do run).
                sym_prog["state"] = "done"
                print(f"  [OK] {sym}: 0 barras novas — lacunas sem pregao (pausa/feriado)")
                continue

            df = df.sort_values("timestamp").drop_duplicates(subset=["timestamp"], keep="last")
            df = df.reset_index(drop=True)
            df.to_parquet(cons_path, index=False)
            sym_prog["state"] = "done"
            _progress_tick(t0)
            logger.info("%s: %d barras preenchidas em %d lacunas -> %s", sym, total_new, len(gaps), cons_path.name)
            print(f"  [OK] {sym}: +{total_new} barras ({len(gaps)} lacunas)")

        _write_progress(state="done", current_symbol=None, symbols=_PROGRESS["symbols"])
        print()
        print("[OK] Fill concluido - revalidar com:")
        print("     python gates/run_consolidate_parquet.py")
        return 0
    except Exception as e:
        _write_progress(state="error", last_error=str(e)[:200])
        raise
    finally:
        _PID_PATH.unlink(missing_ok=True)


def main() -> int:
    if "--gaps" in sys.argv:
        return fill_gaps()

    # Suporte a --symbol para backfill individual
    target_symbols = list(SYMBOLS + INDEX_SYMBOLS)
    if "--symbol" in sys.argv:
        idx = sys.argv.index("--symbol")
        if idx + 1 < len(sys.argv):
            target_symbols = [sys.argv[idx + 1]]
        else:
            print("[FAIL] --symbol requer um valor. Ex: --symbol DXYUSD")
            return 1

    print("=" * 60)
    print(f" BACKFILL M_1 - {len(target_symbols)} simbolo(s) x 2 anos")
    print(f" Throttle: {THROTTLE_RPS} req/s | Janela: {WINDOW_DAYS}d")
    print("=" * 60)

    # Init MCP
    config = ROOT / "config.yaml"
    if not config.exists():
        print("[FAIL] config.yaml nao encontrado. Execute da raiz do ctrader.")
        return 1
    init_client(str(config))
    logger.info("MCP conectado. Iniciando backfill...")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    _progress_start("full")
    _PID_PATH.write_text(str(os.getpid()), encoding="utf-8")
    t_start = time.monotonic()
    try:
        for sym in target_symbols:
            print(f"\n--- {sym} ---")
            try:
                backfill_symbol(sym, t0=t_start)
            except Exception as e:
                logger.error("%s: FALHA - %s", sym, e)
                _PROGRESS["symbols"][sym]["state"] = "error"
                _write_progress(last_error=f"{sym}: {str(e)[:150]}")
        _write_progress(state="done", current_symbol=None, symbols=_PROGRESS["symbols"])
    except Exception as e:
        _write_progress(state="error", last_error=str(e)[:200])
        raise
    finally:
        _PID_PATH.unlink(missing_ok=True)

    total_time = time.monotonic() - t_start
    print(f"\n{'='*60}")
    print(f" BACKFILL CONCLUIDO em {total_time/60:.0f}min")
    print(f" Arquivos: {OUTPUT_DIR}/")
    for sym in target_symbols:
        p = OUTPUT_DIR / f"{sym}_M1.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            print(f"  {sym}_M1.parquet: {len(df):,} linhas, "
                  f"{pd.Timestamp(df['timestamp'].min(), unit='ms').strftime('%Y-%m-%d')} -> "
                  f"{pd.Timestamp(df['timestamp'].max(), unit='ms').strftime('%Y-%m-%d')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
