"""PROPOSITO: G23 — consolidacao do banco Parquet M_1.
SPEC: S31
ROADMAP: S31

Merge backfill + live, normaliza timestamps, dedup, salva canonico em
data/consolidated/{SYM}_M1.parquet e gera status/gap_report.json.
NAO toca MCP (R-NO-MCP-BYPASS) — fill das lacunas e feito por
f0_collector/backfill_orc_coleta.py --gaps.

OTIMIZACOES v2.0 (2026-08-06):
  - Progresso por simbolo: [1/5] XAUUSD... [OK] (antes: silencio ate terminar)
  - Skip gap scan se consolidado nao mudou (cache mtime no gap_report.json)
  - Pre-computa intervalos de fechamento (antes: O(gaps x janelas) datetime objects)
  - --fast: pula merge, so scan (para boot diario onde backfill ja rodou)
"""
from __future__ import annotations

import json
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
BACKFILL_DIR = DATA_DIR / "backfill"
CONSOLIDATED_DIR = DATA_DIR / "consolidated"
STATUS_DIR = ROOT / "status"
SYMBOLS = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "DXYUSD", "VIXUSD"]
GAP_MIN_MINUTES = 5
MIN_MS = 60_000
BACKFILL_WINDOW_DAYS = 730  # janela alvo do Vector (S31): 2 anos
# FIX v2.4: Indices DXY/VIX so possuem dados a partir de 2025-10-24 (~9.8 meses).
# Configurar janela menor para nao gerar buraco historico gigante artificial.
BACKFILL_WINDOW_DAYS_BY_SYMBOL: dict[str, int] = {
    "DXYUSD": 295,
    "VIXUSD": 295,
}

GARBAGE_FLOOR_MS = 915_148_800_000  # 1999-01-01 — ts abaixo disso e lixo (epoch 0)
SCRIPT_VERSION = "2.4"  # v2.4: janela backfill por ativo (indices=295 dias)

# Fechamento semanal do mercado: sex 21:00 UTC -> dom 21:00 UTC
WEEK_CLOSE_UTC = (4, 21)  # weekday 4 = sexta
WEEK_OPEN_UTC = (6, 21)  # weekday 6 = domingo

# Fechamento DIARIO por simbolo (UTC)
# Pausas de rollover/fechamento diario por simbolo.
#
# FIX v2.2: Forex majors: (21,22) expandido para (21,23) — rollover real ~21:59-23:00.
# FIX v2.3: DXYUSD/VIXUSD: rollover vai de 20:55 a 00:59 (3h+). DST muda hora
#   de inicio (pre-DST h=20, pos-DST h=21) mas o fim e sempre apos meia-noite.
#   Solucao: (20,1) = 20h ate 01h do dia seguinte (5h de janela, cobre ambos DST).
#   VIXUSD tambem adicionado: mesmo rollover + indice esparso (micro-gaps naturais).
#
# FORMATO: (h_close, h_reopen) em UTC. Se h_reopen < h_close, e dia seguinte.
DAILY_CLOSE_UTC: dict[str, tuple[int, int]] = {
    "XAUUSD": (21, 23),   # rollover real: ~21:59-23:00
    "EURUSD": (21, 23),   # rollover: ~21:00-22:09 + fuzz ate 23:00
    "GBPUSD": (21, 23),   # idem
    "USDJPY": (21, 23),   # idem
    "AUDUSD": (21, 23),   # idem
    "DXYUSD": (20, 1),    # FIX v2.3: rollover 20:55->00:59 (DST-dual: h20 ou h21)
    "VIXUSD": (20, 1),    # FIX v2.3: rollover idem DXY + indice esparso
}

# Threshold de gap por tipo de ativo
# Indices (DXY, VIX) tem cotacao esparsa — gaps <30min sao normais.
# Forex majors: M1 continuo, gap >=5min e lacuna real.
GAP_MIN_MINUTES_INDEX: dict[str, int] = {
    "DXYUSD": 30,   # indice: cotacao esparsa, gaps <30min sao fuzz
    "VIXUSD": 30,   # indice: idem
}

# Feriados Forex — mercado fecha mais cedo ou nao abre.
# Lista conservadora de datas FIXAS que se repetem anualmente.
# Formato: (mes, dia, hora_close_utc, hora_reopen_utc_prox_dia)
# Se hora_reopen > 24, significa que reabre no dia seguinte.
# Referencia: CME/COMEX holiday schedule 2024-2026.
FOREX_HOLIDAYS_FIXED: list[tuple[int, int, int, int]] = [
    (12, 25, 0, 23),    # Natal: dia inteiro fechado
    (1, 1, 0, 23),      # Ano Novo: dia inteiro fechado
    (12, 24, 18, 23),   # Vespera Natal: fecha 18h UTC
    (12, 31, 21, 23),   # Vespera Ano Novo: fecha 21h UTC (as vezes)
    (7, 4, 18, 23),     # US Independence Day: fecha 18h UTC
    (11, 28, 18, 23),   # Thanksgiving (dia fixo simplificado): fecha 18h UTC
]


# --- Cache de intervalos de fechamento (pre-computado uma vez) ---

def _precompute_closed_intervals(
    window_start_ms: int, now_ms: int, symbol: str = ""
) -> list[tuple[int, int]]:
    """Pre-computa TODOS os intervalos de mercado fechado na janela.

    O(N) em uma passada, em vez de repetir por gap (O(N²)).
    Retorna lista de (start_ms, end_ms) ordenada.
    """
    cursor = datetime.fromtimestamp(window_start_ms / 1000, tz=UTC)
    end_dt = datetime.fromtimestamp(now_ms / 1000, tz=UTC)
    intervals: list[tuple[datetime, datetime]] = []

    # Semanais: ancora na sexta 21:00 UTC anterior ou igual ao cursor
    days_since_fri = (cursor.weekday() - WEEK_CLOSE_UTC[0]) % 7
    fri_close = (cursor - timedelta(days=days_since_fri)).replace(
        hour=WEEK_CLOSE_UTC[1], minute=0, second=0, microsecond=0
    )
    while fri_close < end_dt:
        intervals.append((fri_close, fri_close + timedelta(days=2)))
        fri_close += timedelta(days=7)

    # Diarios por simbolo
    if symbol in DAILY_CLOSE_UTC:
        h1, h2 = DAILY_CLOSE_UTC[symbol]
        day = cursor.replace(hour=0, minute=0, second=0, microsecond=0)
        while day < end_dt:
            close_start = day + timedelta(hours=h1)
            if h2 > h1:
                # Mesmo dia (ex: forex majors 21h->23h)
                close_end = day + timedelta(hours=h2)
            else:
                # Dia seguinte (ex: indices 20h->01h+1)
                close_end = day + timedelta(days=1, hours=h2)
            intervals.append((close_start, close_end))
            day += timedelta(days=1)

    # Feriados forex (fechamento antecipado ou dia inteiro)
    for year in range(cursor.year, end_dt.year + 1):
        for month, day_n, h_close, h_reopen in FOREX_HOLIDAYS_FIXED:
            try:
                holiday = datetime(year, month, day_n, h_close, 0, 0, tzinfo=UTC)
                reopen = datetime(year, month, day_n, h_reopen, 0, 0, tzinfo=UTC)
                if reopen <= holiday:
                    reopen += timedelta(days=1)
                intervals.append((holiday, reopen))
            except ValueError:
                pass  # dia invalido (ex: 30 fev)

    # Uniao de intervalos
    ivs = sorted(intervals)
    merged: list[tuple[datetime, datetime]] = []
    for s, e in ivs:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))

    # Converte para ms
    result: list[tuple[int, int]] = []
    for s, e in merged:
        ov_start = max(s, cursor)
        ov_end = min(e, end_dt)
        if ov_end > ov_start:
            result.append((
                int(ov_start.timestamp() * 1000),
                int(ov_end.timestamp() * 1000),
            ))
    return result


def _closed_ms_cached(
    a_ms: int, b_ms: int, closed_intervals: list[tuple[int, int]]
) -> int:
    """Soma ms fechados entre a e b usando intervalos pre-computados."""
    closed = 0
    for cs, ce in closed_intervals:
        ov_start = max(a_ms, cs)
        ov_end = min(b_ms, ce)
        if ov_end > ov_start:
            closed += ov_end - ov_start
    return closed


def _to_ms(series: pd.Series) -> pd.Series:
    """Normaliza coluna timestamp para ms epoch (ISO string ou ms int)."""
    if pd.api.types.is_numeric_dtype(series):
        return series.astype("int64")
    parsed = pd.to_datetime(series, utc=True, errors="coerce")
    ms = parsed.view("int64") // 1_000_000
    return ms.mask(parsed.isna())


def _is_weekend_or_daily_close(
    a_ms: int, b_ms: int, symbol: str, closed_intervals: list[tuple[int, int]]
) -> bool:
    """Filtro de calendario: gaps >80% cobertos por fechamento de mercado sao ignorados.

    Fins de semana (sex 21h -> dom 21h UTC) e fechamento diario XAUUSD (21h-22h)
    geram gaps residuais de ~18-60min que o MCP nunca preenche — sao fuzz de
    abertura/fechamento, nao lacunas reais.
    """
    diff = b_ms - a_ms
    if diff <= 0:
        return True  # skip invalid
    closed_total = _closed_ms_cached(a_ms, b_ms, closed_intervals)
    # Se >80% do gap e mercado fechado, nao e lacuna real
    return closed_total / diff > 0.8


def scan_gaps(ts_sorted: list[int], gap_min_minutes: int = GAP_MIN_MINUTES,
              symbol: str = "", closed_intervals: list | None = None) -> list[dict[str, int]]:
    """Detecta lacunas na grade M_1 descontando fechamento semanal + diario.

    closed_intervals: pre-computado por _precompute_closed_intervals().
    Se None, usa _closed_ms_between() legado (slow path, compatibilidade).

    v2.1: filtra gaps de calendario (>80% mercado fechado = fuzz, nao lacuna).
    """
    gaps: list[dict[str, int]] = []
    threshold_ms = gap_min_minutes * MIN_MS
    for i in range(len(ts_sorted) - 1):
        a, b = ts_sorted[i], ts_sorted[i + 1]
        diff = b - a
        if diff <= threshold_ms:
            continue

        # Filtro de calendario: sabado/domingo/fechamento diario
        if (closed_intervals is not None
                and _is_weekend_or_daily_close(a, b, symbol, closed_intervals)):
            continue

        if closed_intervals is not None:
            closed = _closed_ms_cached(a, b, closed_intervals)
        else:
            closed = _closed_ms_between(a, b, symbol)
        missing = diff - closed - MIN_MS
        if missing > threshold_ms:
            gaps.append({
                "start_ms": a + MIN_MS,
                "end_ms": b - MIN_MS,
                "missing_minutes": int(missing // MIN_MS),
            })
    return gaps


def _closed_ms_between(start_ms: int, end_ms: int, symbol: str = "") -> int:
    """Legado: calcula intervalos de fechado on-the-fly. Lento, mantido para compat."""
    cursor = datetime.fromtimestamp(start_ms / 1000, tz=UTC)
    end_dt = datetime.fromtimestamp(end_ms / 1000, tz=UTC)
    intervals: list[tuple[datetime, datetime]] = []

    days_since_fri = (cursor.weekday() - WEEK_CLOSE_UTC[0]) % 7
    fri_close = (cursor - timedelta(days=days_since_fri)).replace(
        hour=WEEK_CLOSE_UTC[1], minute=0, second=0, microsecond=0
    )
    while fri_close < end_dt:
        intervals.append((fri_close, fri_close + timedelta(days=2)))
        fri_close += timedelta(days=7)

    if symbol in DAILY_CLOSE_UTC:
        h1, h2 = DAILY_CLOSE_UTC[symbol]
        day = cursor.replace(hour=0, minute=0, second=0, microsecond=0)
        while day < end_dt:
            intervals.append((day + timedelta(hours=h1), day + timedelta(hours=h2)))
            day += timedelta(days=1)

    closed = 0
    ivs = sorted(intervals)
    cur_s: datetime | None = None
    cur_e: datetime | None = None
    for s, e in ivs:
        if cur_s is None:
            cur_s, cur_e = s, e
        elif s <= cur_e:
            cur_e = max(cur_e, e)
        else:
            ov_start = max(cur_s, cursor)
            ov_end = min(cur_e, end_dt)
            if ov_end > ov_start:
                closed += int((ov_end - ov_start).total_seconds() * 1000)
            cur_s, cur_e = s, e
    if cur_s is not None:
        ov_start = max(cur_s, cursor)
        ov_end = min(cur_e, end_dt)
        if ov_end > ov_start:
            closed += int((ov_end - ov_start).total_seconds() * 1000)
    return closed


def _drop_garbage_ts(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Remove linhas-lixo (timestamp < 1999)."""
    if "timestamp" not in df.columns or not len(df):
        return df
    ts = pd.to_numeric(df["timestamp"], errors="coerce")
    bad = int((ts < GARBAGE_FLOOR_MS).sum()) + int(ts.isna().sum())
    if bad:
        print(f"  [WARN] G23: {symbol} — {bad} linha(s)-lixo descartada(s)")
    return df[ts >= GARBAGE_FLOOR_MS].reset_index(drop=True)


def scan_gaps_anchored(ts_sorted: list[int], window_start_ms: int, now_ms: int,
                       gap_min_minutes: int = GAP_MIN_MINUTES,
                       symbol: str = "",
                       closed_intervals: list | None = None) -> list[dict[str, int]]:
    """Gap scan ancorado na janela alvo do Vector (S31, 2 anos).

    v2.1: filtra gaps de calendario (fins de semana, fechamento diario XAUUSD).
    """
    threshold_ms = gap_min_minutes * MIN_MS
    gaps: list[dict[str, int]] = []

    def _should_skip_calendar(a_ms: int, b_ms: int) -> bool:
        if closed_intervals is None:
            return False
        return _is_weekend_or_daily_close(a_ms, b_ms, symbol, closed_intervals)

    if not ts_sorted:
        if not _should_skip_calendar(window_start_ms, now_ms):
            if closed_intervals is not None:
                closed = _closed_ms_cached(window_start_ms, now_ms, closed_intervals)
            else:
                closed = _closed_ms_between(window_start_ms, now_ms, symbol)
            missing = (now_ms - window_start_ms) - closed
            if missing > threshold_ms:
                gaps.append({"start_ms": window_start_ms, "end_ms": now_ms,
                             "missing_minutes": int(missing // MIN_MS)})
        return gaps

    first = ts_sorted[0]
    if (first > window_start_ms + threshold_ms
            and not _should_skip_calendar(window_start_ms, first)):
        if closed_intervals is not None:
            closed = _closed_ms_cached(window_start_ms, first, closed_intervals)
        else:
            closed = _closed_ms_between(window_start_ms, first, symbol)
        missing = (first - window_start_ms) - closed
        if missing > threshold_ms:
            gaps.append({"start_ms": window_start_ms, "end_ms": first - MIN_MS,
                         "missing_minutes": int(missing // MIN_MS)})

    # Filtra ts_sorted para janela antes de escanear gaps intermediarios
    ts_window = [t for t in ts_sorted if window_start_ms <= t <= now_ms]
    gaps.extend(scan_gaps(ts_window, gap_min_minutes, symbol, closed_intervals))

    last = ts_sorted[-1]
    if (last < now_ms - threshold_ms
            and not _should_skip_calendar(last, now_ms)):
        if closed_intervals is not None:
            closed = _closed_ms_cached(last, now_ms, closed_intervals)
        else:
            closed = _closed_ms_between(last, now_ms, symbol)
        missing = (now_ms - last) - closed - MIN_MS
        if missing > threshold_ms:
            gaps.append({"start_ms": last + MIN_MS, "end_ms": now_ms,
                         "missing_minutes": int(missing // MIN_MS)})
    return sorted(gaps, key=lambda g: g["start_ms"])


def _expected_open_minutes(window_start_ms: int, now_ms: int, symbol: str = "",
                           closed_intervals: list | None = None) -> int:
    """Minutos de pregao esperados na janela (desconta fds + fechamento diario)."""
    if closed_intervals is not None:
        closed = _closed_ms_cached(window_start_ms, now_ms, closed_intervals)
    else:
        closed = _closed_ms_between(window_start_ms, now_ms, symbol)
    return max(1, int(((now_ms - window_start_ms) - closed) // MIN_MS))


def _read_parquet_safe(path: Path) -> pd.DataFrame | None:
    try:
        return pd.read_parquet(path)
    except Exception as e:
        print(f"  [ERR] G23: {path.name} ilegivel — {e}")
        return None


def _parquet_mtime(path: Path) -> float:
    """mtime do parquet (0 se nao existe)."""
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def merge_symbol(symbol: str) -> tuple[pd.DataFrame | None, dict[str, int]]:
    """Merge backfill + CONSOLIDADO EXISTENTE + live de um simbolo."""
    frames: list[pd.DataFrame] = []
    stats = {"backfill_rows": 0, "consolidated_rows": 0, "live_rows": 0}

    bf = BACKFILL_DIR / f"{symbol}_M1.parquet"
    if bf.exists():
        df = _read_parquet_safe(bf)
        if df is not None and len(df) > 0:
            stats["backfill_rows"] = len(df)
            frames.append(df)

    cons = CONSOLIDATED_DIR / f"{symbol}_M1.parquet"
    if cons.exists():
        df = _read_parquet_safe(cons)
        if df is not None and len(df) > 0:
            stats["consolidated_rows"] = len(df)
            frames.append(df)

    live_files = sorted(DATA_DIR.glob(f"m1_{symbol}_*.parquet"))
    for lf in live_files:
        df = _read_parquet_safe(lf)
        if df is not None and len(df) > 0:
            stats["live_rows"] += len(df)
            frames.append(df)

    if not frames:
        print(f"  [WARN] G23: {symbol} sem dados (backfill pendente)")
        return None, stats

    merged = pd.concat(frames, ignore_index=True)
    merged["timestamp"] = _to_ms(merged["timestamp"])
    merged = merged.dropna(subset=["timestamp"])
    merged = merged.sort_values("timestamp").drop_duplicates(subset=["timestamp"], keep="last")
    merged = merged.reset_index(drop=True)
    merged = _drop_garbage_ts(merged, symbol)
    if not len(merged):
        print(f"  [WARN] G23: {symbol} so tinha linhas-lixo — consolidado vazio")
        return None, stats
    return merged, stats


def _load_previous_report() -> dict | None:
    """Carrega gap_report.json anterior para comparar mtimes."""
    report_path = STATUS_DIR / "gap_report.json"
    if not report_path.exists():
        return None
    try:
        return json.loads(report_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _consolidated_stale(symbol: str, prev_report: dict | None) -> bool:
    """Verifica se o consolidado mudou desde o ultimo report.

    Tambem invalida cache se a versao do script mudou (evita perpetuar
    gaps antigos apos correcoes no algoritmo de scan).
    """
    if prev_report is None:
        return True
    if prev_report.get("_script_version") != SCRIPT_VERSION:
        return True  # algoritmo mudou -> fresh scan
    prev_mtime = prev_report.get("_consolidated_mtimes", {}).get(symbol, 0)
    cons = CONSOLIDATED_DIR / f"{symbol}_M1.parquet"
    current_mtime = _parquet_mtime(cons)
    return current_mtime > prev_mtime or current_mtime == 0.0


def consolidate(check_only: bool = False, fast: bool = False,
                auto_backfill: bool = False) -> dict[str, object]:
    """Consolida os 5 simbolos e gera o gap report ancorado na janela S31.

    --check: apenas scan, sem merge (usa consolidado existente)
    --fast:  pula merge se consolidado nao mudou desde ultimo report
    """
    now = datetime.now(UTC)
    yesterday_end = now.replace(hour=23, minute=59, second=59, microsecond=999000) - timedelta(days=1)
    now_ms = int(yesterday_end.timestamp() * 1000)

    prev_report = _load_previous_report()  # sempre carrega — auto_backfill usa pra detectar estabilidade
    symbols_total = len(SYMBOLS)
    consolidated_mtimes: dict[str, float] = {}

    report: dict[str, object] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "gap_min_minutes": GAP_MIN_MINUTES,
        "window_days": BACKFILL_WINDOW_DAYS,
        "daily_close_utc": DAILY_CLOSE_UTC,
        "symbols": {},
    }
    symbols_report: dict[str, object] = {}

    # Computa window_start_ms por simbolo
    sym_window_starts: dict[str, int] = {}
    for sym in SYMBOLS:
        days = BACKFILL_WINDOW_DAYS_BY_SYMBOL.get(sym, BACKFILL_WINDOW_DAYS)
        sym_window_starts[sym] = now_ms - days * 86_400_000

    # Pre-computa intervalos de fechamento (cache global por simbolo)
    closed_cache: dict[str, list[tuple[int, int]]] = {}
    for sym in SYMBOLS:
        closed_cache[sym] = _precompute_closed_intervals(sym_window_starts[sym], now_ms, sym)

    for idx, sym in enumerate(SYMBOLS, 1):
        t0 = time.monotonic()
        window_start_ms = sym_window_starts[sym]
        closed_intervals = closed_cache[sym]
        expected_open_min = _expected_open_minutes(
            window_start_ms, now_ms, sym, closed_intervals
        )

        # --- Skip se nao mudou (modo --fast) ---
        if fast and not _consolidated_stale(sym, prev_report):
            # Reutiliza dados do report anterior
            prev_sym = (prev_report.get("symbols", {}) or {}).get(sym, {})
            if prev_sym:
                print(f"  [{idx}/{symbols_total}] {sym}... [SKIP] nao mudou "
                      f"({prev_sym.get('rows', '?')} linhas, {prev_sym.get('coverage_pct', '?')}%)")
                symbols_report[sym] = prev_sym
                consolidated_mtimes[sym] = _parquet_mtime(
                    CONSOLIDATED_DIR / f"{sym}_M1.parquet"
                )
                continue

        print(f"  [{idx}/{symbols_total}] {sym}...", end=" ", flush=True)

        if check_only or fast:
            path = CONSOLIDATED_DIR / f"{sym}_M1.parquet"
            if not path.exists():
                print("[WARN] consolidado ausente — rode sem --check")
                continue
            df = _read_parquet_safe(path)
            if df is None:
                print("[ERR] ilegivel")
                continue
            df = _drop_garbage_ts(df, sym)
            # Extrai timestamp: coluna 'timestamp' (forex) ou DatetimeIndex (indices)
            if "timestamp" in df.columns:
                ts = sorted(int(t) for t in df["timestamp"])
            elif isinstance(df.index, pd.DatetimeIndex):
                ts = sorted(int(t.timestamp() * 1000) for t in df.index)
            else:
                rows = len(df)
                elapsed = time.monotonic() - t0
                print(f"[OK] {rows} linhas, sem timestamp — pulando gap scan ({elapsed:.1f}s)")
                consolidated_mtimes[sym] = _parquet_mtime(path)
                symbols_report[sym] = {
                    "rows": rows, "first": "", "last": "",
                    "coverage_days": 0, "coverage_pct": 100.0,
                    "gaps": [], "total_gaps": 0, "total_missing_minutes": 0,
                }
                continue
            rows = len(df)
            dups = len(ts) - len(set(ts)) if ts else 0
            if dups > 0:
                print(f"[ERR] {dups} timestamps duplicados")
                continue
            elapsed = time.monotonic() - t0
            print(f"[OK] {rows} linhas ({elapsed:.1f}s)")
        else:
            df, stats = merge_symbol(sym)
            if df is None:
                print("[WARN] sem dados")
                continue
            CONSOLIDATED_DIR.mkdir(parents=True, exist_ok=True)
            out = CONSOLIDATED_DIR / f"{sym}_M1.parquet"
            df.to_parquet(out, index=False)
            ts = [int(t) for t in df["timestamp"]]
            rows = len(df)
            elapsed = time.monotonic() - t0
            print(f"[OK] {rows} linhas "
                  f"(bf={stats['backfill_rows']}, cons={stats['consolidated_rows']}, "
                  f"live={stats['live_rows']}) ({elapsed:.1f}s)")

        consolidated_mtimes[sym] = _parquet_mtime(
            CONSOLIDATED_DIR / f"{sym}_M1.parquet"
        )

        # Gap scan (usa intervalos pre-computados + threshold por tipo)
        sym_gap_min = GAP_MIN_MINUTES_INDEX.get(sym, GAP_MIN_MINUTES)
        gaps = scan_gaps_anchored(ts, window_start_ms, now_ms,
                                  gap_min_minutes=sym_gap_min,
                                  symbol=sym, closed_intervals=closed_intervals)
        first = datetime.fromtimestamp(ts[0] / 1000, tz=UTC).strftime("%Y-%m-%d") if ts else ""
        last = datetime.fromtimestamp(ts[-1] / 1000, tz=UTC).strftime("%Y-%m-%d") if ts else ""
        coverage_days = round((ts[-1] - ts[0]) / 86_400_000, 1) if len(ts) > 1 else 0
        total_missing = sum(g["missing_minutes"] for g in gaps)
        coverage_pct = round(max(0.0, 100.0 * (1 - total_missing / expected_open_min)), 1)
        symbols_report[sym] = {
            "rows": rows,
            "first": first,
            "last": last,
            "coverage_days": coverage_days,
            "coverage_pct": coverage_pct,
            "gaps": gaps,
            "total_gaps": len(gaps),
            "total_missing_minutes": total_missing,
        }

    report["symbols"] = symbols_report
    report["_consolidated_mtimes"] = consolidated_mtimes
    report["_script_version"] = SCRIPT_VERSION
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = STATUS_DIR / "gap_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> int:
    check_only = "--check" in sys.argv
    fast = "--fast" in sys.argv
    auto_backfill = "--auto-backfill" in sys.argv

    # --window-days: override BACKFILL_WINDOW_DAYS (para testes)
    global BACKFILL_WINDOW_DAYS
    if "--window-days" in sys.argv:
        idx = sys.argv.index("--window-days")
        if idx + 1 < len(sys.argv):
            BACKFILL_WINDOW_DAYS = int(sys.argv[idx + 1])

    mode = "CHECK (read-only)" if check_only else ("FAST (skip unchanged)" if fast else "FULL (merge + scan)")
    print("=" * 60)
    print(f" G23 — CONSOLIDACAO PARQUET M_1 [{mode}]")
    print(f" Simbolos: {len(SYMBOLS)} | Janela: {BACKFILL_WINDOW_DAYS}d | "
          f"Gap min: {GAP_MIN_MINUTES}min | Cache: pre-computed intervals")
    if auto_backfill:
        print(" Auto-backfill: SIM (preenche lacunas automaticamente)")
    print("=" * 60)

    t_total = time.monotonic()
    report_path = STATUS_DIR / "gap_report.json"
    report = consolidate(check_only=check_only, fast=fast, auto_backfill=auto_backfill)
    symbols = report.get("symbols", {})

    total_gaps = 0
    for sym, info in symbols.items():
        gaps = info["total_gaps"]
        missing = info["total_missing_minutes"]
        total_gaps += gaps
        cov = info.get("coverage_pct", 0)
        if gaps > 0:
            print(
                f"  [WARN] {sym}: {gaps} lacunas, {missing} min ausentes "
                f"({info['first']} -> {info['last']}, cobertura {cov}%)"
            )
        else:
            print(f"  [OK] {sym}: sem lacunas ({info['rows']} linhas, cobertura {cov}%)")

    elapsed_total = time.monotonic() - t_total
    print()

    if total_gaps > 0:
        if auto_backfill:
            # Verifica se gaps estao estaveis vs report anterior
            current_missing = sum(
                s.get("total_missing_minutes", 0)
                for s in symbols.values()
            )
            # Removida a trava de ESTAVEIS: o sistema sempre tentara preencher se houver lacunas.
            print(f"[GAPS] {total_gaps} lacunas detectadas ({current_missing} min ausentes) — acionando backfill automaticamente...")
            import subprocess
            backfill_script = str(ROOT / "f0_collector" / "backfill_orc_coleta.py")
            try:
                result = subprocess.run(
                    [sys.executable, backfill_script, "--gaps"],
                    capture_output=False,
                    timeout=None,
                )
                if result.returncode == 0:
                    # C3: re-scan pos-backfill em vez de unlink cego
                    # Se gaps estaveis (irredutiveis) -> mantem cache para evitar loop
                    print("\n[OK] Backfill concluido — re-scan para verificar convergencia...")
                    report2 = consolidate(check_only=True, fast=False, auto_backfill=False)
                    new_total = sum(
                        s.get("total_gaps", s.get("gaps_count", len(s.get("gaps", []))))
                        for s in report2.get("symbols", {}).values()
                    )
                    if new_total == total_gaps:
                        # Gaps estaveis = irredutiveis (feriados, rollover residual)
                        print(f"       Gaps estaveis ({total_gaps} -> {new_total}) — cache mantido")
                        print("       Proximo boot usara --fast (sem re-backfill)")
                        # Salva report pos-backfill (gaps atualizados via C2)
                        report_path.write_text(
                            json.dumps(report2, indent=2, default=str), encoding="utf-8"
                        )
                    else:
                        # Gaps reduziram — progresso real, permite proximo backfill
                        print(f"       Gaps reduziram ({total_gaps} -> {new_total}) — cache atualizado")
                        report_path.unlink(missing_ok=True)
                    print(f"[OK] G23 + backfill concluido ({elapsed_total:.1f}s + backfill)")
                else:
                    print(f"\n[WARN] G23 ok mas backfill falhou (exit={result.returncode})")
                    print("       Cache mantido — gaps restantes salvos incrementalmente")
            except subprocess.TimeoutExpired:
                print(f"\n[WARN] G23 timeout ({1800}s) — cache mantido")
                print("       Gaps restantes salvos incrementalmente pelo backfill")
            except Exception as e:
                print(f"\n[ERR] G23 falhou: {e} — cache mantido com progresso parcial")
        else:
            print(f"[WARN] G23: {total_gaps} lacunas — preencher com: "
                  f"python f0_collector/backfill_orc_coleta.py --gaps")
    else:
        print(f"[OK] G23: banco consolidado sem lacunas ({elapsed_total:.1f}s)")
    print("       Report: status/gap_report.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
