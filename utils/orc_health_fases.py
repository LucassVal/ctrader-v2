"""
PROPOSITO: Validador por fase sempre ativo — saude das mecanicas por etapa
SPEC: S33
ROADMAP: S33
FLOW:   status/*.json + data/*.parquet + trades.db -> check_fases()
        -> /api/ctrader/health/fases -> sub-aba "Saude" de cada aba mestra (S22).
REGRAS: So leituras baratas (stat, 1 coluna de parquet, SELECT COUNT, JSON).
        Score pesado S29+S30 NUNCA roda aqui (S20 v2.1). Nao toca MCP
        (R-NO-MCP-BYPASS). Read-only (G19-compatible).
"""

from __future__ import annotations

import contextlib
import json
import logging
import sqlite3
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent.parent
_STATUS = _ROOT / "status"
_DATA = _ROOT / "data"

MIN_PONTOS_S29_S30 = 30   # minimo de pontos VBT p/ quality/patterns sairem do sem_dados
COBERTURA_ALVO_PCT = 90.0  # fill de 2 anos considerado completo (S31)


# ---------------------------------------------------------------------------
# helpers baratos
# ---------------------------------------------------------------------------


def _check(nome: str, ok: bool, detalhe: str) -> dict[str, Any]:
    return {"nome": nome, "ok": ok, "detalhe": detalhe}


def _age_s(path: Path) -> float | None:
    try:
        return (datetime.now(UTC) - datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)).total_seconds()
    except OSError:
        return None


def _json_ok(path: Path) -> tuple[bool, str]:
    if not path.exists():
        return False, "ausente"
    try:
        json.loads(path.read_text(encoding="utf-8"))
        age = _age_s(path)
        return True, f"presente ({age:.0f}s atras)" if age is not None else "presente"
    except (json.JSONDecodeError, OSError) as e:
        return False, f"ilegivel: {str(e)[:60]}"


def _pid_vivo(pid: int) -> bool:
    """tasklist e o caminho seguro no Windows — os.kill(pid, 0) mataria o processo."""
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=3,
        )
        return str(pid) in out.stdout
    except Exception:
        return False


def _parquet_rows(path: Path) -> int | None:
    """Conta linhas via metadata — sem carregar colunas."""
    try:
        import pyarrow.parquet as pq

        return pq.read_metadata(path).num_rows
    except Exception:
        return None


def _parquet_last_ts(path: Path) -> float | None:
    try:
        import pandas as pd

        ts = pd.read_parquet(path, columns=["timestamp"])["timestamp"]
        return float(pd.to_numeric(ts, errors="coerce").max())
    except Exception:
        return None


# ---------------------------------------------------------------------------
# checks por fase
# ---------------------------------------------------------------------------


def _f0_coleta() -> list[dict[str, Any]]:
    checks = []
    snap = _STATUS / "snapshot.json"
    age = _age_s(snap)
    checks.append(_check("snapshot fresco (<120s)", age is not None and age < 120,
                         f"{age:.0f}s" if age is not None else "snapshot ausente"))

    pid_file = _STATUS / "f0.pid"
    pid = None
    with contextlib.suppress(OSError, ValueError):
        pid = int(pid_file.read_text().strip())
    vivo = _pid_vivo(pid) if pid else False
    checks.append(_check("processo F0 vivo", vivo,
                         f"pid {pid} {'ativo' if vivo else 'morto'}" if pid else "f0.pid ausente"))

    # SESSION LIFECYCLE: verifica idade da sessao MCP
    try:
        from utils.mcp_client import SESSION_MAX_AGE, get_session_age
        sess_age = get_session_age()
        sess_fresh = sess_age < SESSION_MAX_AGE if sess_age > 0 else True  # 0 = nunca init
        checks.append(_check("sessao MCP fresca",
                             sess_fresh,
                             f"{sess_age:.0f}s (renova em {max(0, SESSION_MAX_AGE - sess_age):.0f}s)"))
    except Exception:
        checks.append(_check("sessao MCP fresca", False, "nao foi possivel verificar"))

    m1 = sorted(_DATA.glob("m1_XAUUSD_*.parquet"))
    if not m1:
        checks.append(_check("m1 recente (<10min)", False, "m1_XAUUSD ausente"))
    else:
        last = _parquet_last_ts(m1[-1])
        if last and last > 1e12:
            last /= 1000  # F0 persiste timestamp em milissegundos
        lag = datetime.now(UTC).timestamp() - last if last else None
        checks.append(_check("m1 recente (<10min)", lag is not None and lag < 600,
                             f"ultima vela {lag:.0f}s atras" if lag is not None else "timestamp ilegivel"))
    return checks


def _f1_f2() -> list[dict[str, Any]]:
    checks = []
    for nome in ("scores_raw.json", "fusion_output.json"):
        ok, det = _json_ok(_STATUS / nome)
        checks.append(_check(nome, ok, det))
    return checks


def _f3_ia() -> list[dict[str, Any]]:
    ok, det = _json_ok(_STATUS / "verdict.json")
    return [_check("verdict.json", ok, det)]


def _f4_execucao() -> list[dict[str, Any]]:
    db = _ROOT / "trades.db"
    if not db.exists():
        return [_check("trades.db queryavel", False, "ausente")]
    try:
        conn = sqlite3.connect(str(db))
        total = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
        conn.close()
        return [_check("trades.db queryavel", True, f"{total} trades registrados")]
    except sqlite3.Error as e:
        det = str(e)[:80]
        if "no such table" in det:
            det = "tabela trades ausente — F4 ainda nao registrou trades"
        return [_check("trades.db queryavel", False, det)]


def _f5_mar() -> list[dict[str, Any]]:
    ok, det = _json_ok(_STATUS / "custom_rules.json")
    return [_check("custom_rules.json", ok, det)]


def _vector_s27() -> list[dict[str, Any]]:
    """R-USE orc_metricas.vector_metrics — indicadores VBT por simbolo."""
    from utils.orc_metricas import vector_metrics

    vm = vector_metrics()
    checks = []
    for sym, m in vm.items():
        count = m.get("indicators_count", "0/16")
        ok = m.get("status") == "ok" and count.endswith("/16") and not count.startswith("0/")
        checks.append(_check(f"{sym} indicadores", ok,
                             f"{count} calculados" if ok else f"{count} — {m.get('status')}"))
    return checks


def _s29_s30() -> list[dict[str, Any]]:
    """Pontos VBT suficientes p/ quality (S29) e patterns (S30)."""
    checks = []
    for sym in ("XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD"):
        path = _DATA / f"vbt_{sym}.parquet"
        rows = _parquet_rows(path) if path.exists() else None
        if rows is None:
            checks.append(_check(f"{sym} pontos VBT", False, "parquet ausente/ilegivel"))
        elif rows < MIN_PONTOS_S29_S30:
            checks.append(_check(f"{sym} pontos VBT", False,
                                 f"aquecendo: {rows}/{MIN_PONTOS_S29_S30}"))
        else:
            checks.append(_check(f"{sym} pontos VBT", True, f"{rows} pontos"))
    return checks


def _s31_backfill() -> list[dict[str, Any]]:
    from utils.backfill_supervisor_orc_dashboard import backfill_status
    from utils.orc_metricas import _read_gap_coverage

    checks = []

    # Progresso ao vivo (S31-PROG): o que esta puxando, %, ETA — sem tocar MCP
    bf = backfill_status()
    prog = bf.get("progress") or {}
    totals = prog.get("totals") or {}
    if bf["running"]:
        checks.append(_check(
            "fill em andamento", True,
            f"{prog.get('current_symbol') or '?'} — {totals.get('pct', 0)}% "
            f"({totals.get('windows_done', 0)}/{totals.get('windows_total', 0)} janelas, "
            f"{totals.get('bars', 0):,} barras, ETA {round((prog.get('eta_s') or 0) / 60)}min)"))
    elif prog.get("state") == "done":
        checks.append(_check("fill em andamento", True,
                             f"ultimo run concluido ({totals.get('bars', 0):,} barras)"))
    else:
        checks.append(_check("fill em andamento", False, "nunca rodou — disparar /backfill/start"))

    report = _STATUS / "gap_report.json"
    existe = report.exists()
    checks.append(_check("gap_report presente", existe,
                         "presente" if existe else "backfill nunca rodou"))
    coverage = _read_gap_coverage()
    if coverage:
        min_cov = min(coverage.values())
        detalhe = " ".join(f"{s} {c:.0f}%" for s, c in sorted(coverage.items()))
        checks.append(_check(f"cobertura 2 anos (>={COBERTURA_ALVO_PCT:.0f}%)",
                             min_cov >= COBERTURA_ALVO_PCT,
                             detalhe if min_cov >= COBERTURA_ALVO_PCT else f"{detalhe} — fill pendente"))
    else:
        checks.append(_check(f"cobertura 2 anos (>={COBERTURA_ALVO_PCT:.0f}%)", False,
                             "sem coverage — fill pendente"))
    return checks


def _s32_score() -> list[dict[str, Any]]:
    try:
        from f2_fusao.orc_score import combined_score

        ok = callable(combined_score)
        return [_check("orc_score importavel", ok,
                       "orquestrador pronto; score pesado on-demand (regra de custo)")]
    except Exception as e:
        return [_check("orc_score importavel", False, str(e)[:80])]


# ---------------------------------------------------------------------------
# orquestrador
# ---------------------------------------------------------------------------

_FASES: dict[str, Any] = {
    "f0_coleta": _f0_coleta,
    "f1_f2_analise": _f1_f2,
    "f3_ia": _f3_ia,
    "f4_execucao": _f4_execucao,
    "f5_mar": _f5_mar,
    "vector_s27": _vector_s27,
    "s29_s30": _s29_s30,
    "s31_backfill": _s31_backfill,
    "s32_score": _s32_score,
}


def check_fases(somente: list[str] | None = None) -> dict[str, Any]:
    """Varre as fases e devolve veredito por etapa. Read-only e barato (S33)."""
    fases: dict[str, Any] = {}
    for fase_id, fn in _FASES.items():
        if somente and fase_id not in somente:
            continue
        try:
            checks = fn()
        except Exception as e:
            logger.error("check_fases %s falhou: %s", fase_id, e)
            checks = [_check("excecao no check", False, str(e)[:80])]
        n_ok = sum(1 for c in checks if c["ok"])
        fases[fase_id] = {
            "ok": n_ok == len(checks),
            "checks": checks,
            "resumo": f"{n_ok}/{len(checks)} checks OK",
        }
    n_fases_ok = sum(1 for f in fases.values() if f["ok"])
    return {
        "fases": fases,
        "fases_ok": f"{n_fases_ok}/{len(fases)}",
        "gerado_em": datetime.now(UTC).isoformat(),
    }
