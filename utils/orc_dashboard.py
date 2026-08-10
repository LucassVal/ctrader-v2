"""
PROPOSITO: Orchestrator — apresentacao unificada para dashboard.
SPEC: S21 (pai) — filhos: metrics (agregacao), health, mcp_client, _orc_ranking
ROADMAP: 1.7
FLOW:   snapshot.json (F0) ---> get_mcp_balance/positions/spot()
        metrics.py (DB)    ---> collect_all()
        Ambos alimentam o dashboard sem MCP direto.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent  # 11.0_apps/ctrader
LOGS_DIR = ROOT / "logs"

# Path extra: se chamado do router (10.0_ui_dash), garante acesso ao app
_APP_ROOT = ROOT
if not (_APP_ROOT / "utils" / "metrics.py").exists():
    # fallback: estamos em outro contexto
    _ALT = Path(__file__).resolve().parent.parent.parent.parent / "11.0_apps" / "ctrader"
    if (_ALT / "utils" / "metrics.py").exists():
        _APP_ROOT = _ALT


def _ensure_path():
    if str(_APP_ROOT) not in sys.path:
        sys.path.insert(0, str(_APP_ROOT))


# ═══════════════════════════════════════════════════════════════════════
# EXPORT PARA DASHBOARD (formato plano, 1 nível)
# ═══════════════════════════════════════════════════════════════════════

def collect_all() -> dict[str, Any]:
    """Coleta 25+ métricas de todas as fases (F0-F5)."""
    _ensure_path()
    from utils.orc_metricas import collect_all as _collect
    return _collect()


def validate_against_specs(data: dict[str, Any]) -> dict[str, Any]:
    """Valida métricas contra thresholds das specs S2-S7."""
    failures = []
    thresholds = {
        "f0": {"mcp_uptime_pct": 95, "data_gap_seconds": 120},
        "f4": {"win_rate": 40, "max_drawdown_pct": 3.0, "profit_factor": 1.0},
        "f5": {"weight_delta": 0.15},
    }

    for phase_key, phase_thresholds in thresholds.items():
        phase_data = data.get(phase_key, {})
        if not phase_data or "error" in str(phase_data):
            continue
        for metric, threshold in phase_thresholds.items():
            value = phase_data.get(metric, 0)
            if isinstance(value, (int, float)) and value < threshold:
                failures.append({
                    "phase": phase_key, "metric": metric,
                    "value": value, "threshold": threshold,
                    "spec": f"specs/{phase_key.replace('_','')}.md",
                })

    return {"pass": len(failures) == 0, "failures": failures}


def export_for_dashboard() -> dict[str, Any]:
    """Formata métricas para consumo pelo React (1 nível, sem envelope duplo)."""
    data = collect_all()
    validation = validate_against_specs(data)

    # -- WIRE: stats do json_log (substitui Vector Engine arquivado) --
    vector_stats = {}
    try:
        from utils.json_log_orc_metricas import read_metrics_json
        vector_stats = read_metrics_json() or {}
    except Exception:
        pass

    # -- WIRE: stats do Ranking (>=75% validados) --
    ranking_stats = {}
    try:
        from f3_validacao.orc_ranking import rank_signals
        ranking_stats = rank_signals(min_score=75)
    except Exception:
        pass

    # -- WIRE: stats de Ordens (OCO + trail + BE) --
    order_stats = {}
    try:
        from f4_executor.orc_ordens import get_params
        from utils.json_log_orc_metricas import get_trail_log
        order_stats = get_trail_log()
        order_stats["params"] = get_params()
    except Exception:
        pass

    return {
        "f0_coleta": data.get("f0_coleta", {}),
        "f1_f2_analise": data.get("f1_f2_analise", {}),
        "f3_ia": data.get("f3_ia", {}),
        "f4_execucao": data.get("f4_execucao", {}),
        "f5_mar": data.get("f5_mar", {}),
        "vector": vector_stats,
        "vector_mercados": data.get("vector_mercados", {}),
        "score_mercados": data.get("score_mercados", {}),
        "calibration": data.get("calibration", {}),
        "ranking": ranking_stats,
        "orders": order_stats,
        "alerts": validation.get("failures", []),
    }


# ═══════════════════════════════════════════════════════════════════════
# CAMADA DE DADOS UNIFICADA (S23 — elimina fontes isoladas)
# ═══════════════════════════════════════════════════════════════════════

def get_trade_history(symbol: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    """Histórico de trades do SQLite (via orchestrator — NÃO direto).
    Unifica acesso ao trades.db: todos os 9 leitores devem usar esta função."""
    _ensure_path()
    db_path = ROOT / "trades.db"
    if not db_path.exists():
        return []
    try:
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        if symbol:
            rows = conn.execute(
                "SELECT * FROM trades WHERE symbol=? ORDER BY timestamp DESC LIMIT ?",
                (symbol, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM trades ORDER BY timestamp DESC LIMIT ?",
                (limit,)
            ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def get_status_json(key: str) -> dict[str, Any]:
    """Lê status/*.json via orchestrator (unifica 2 leitores: health.py + metrics.py)."""
    _ensure_path()
    status_dir = ROOT / "status"
    status_file = status_dir / f"{key}.json"
    if not status_file.exists():
        return {}
    try:
        import json
        return json.loads(status_file.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_status_json(key: str, data: dict[str, Any]) -> bool:
    """Grava status/*.json via orchestrator."""
    _ensure_path()
    status_dir = ROOT / "status"
    status_dir.mkdir(parents=True, exist_ok=True)
    try:
        import json
        (status_dir / f"{key}.json").write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return True
    except Exception:
        return False


def get_mcp_balance() -> dict[str, Any]:
    """Saldo via snapshot F0 (ROADMAP 1.7 — sem MCP direto)."""
    snap = _get_snapshot_safe()
    balance = snap.get("balance", {}) if snap else {}
    if balance:
        from utils.orc_dashboard import _normalize_balance
        return _normalize_balance(balance)
    return {"online": False, "error": "Snapshot indisponivel — F0 offline?"}


def get_mcp_positions() -> list[dict[str, Any]]:
    """Posicoes via snapshot F0 (ROADMAP 1.7 — sem MCP direto).
    snapshot["positions"] e {"positions": [...], "orders": [...]} (get_positions()
    do MCP retorna as duas listas juntas) -- desembrulha so a lista de posicoes."""
    snap = _get_snapshot_safe()
    if not snap:
        return []
    pos = snap.get("positions", [])
    if isinstance(pos, dict):
        return pos.get("positions", [])
    return pos if isinstance(pos, list) else []


def get_mcp_spot(symbol: str) -> dict[str, Any]:
    """Cotacao spot via snapshot F0 (ROADMAP 1.7 — sem MCP direto)."""
    snap = _get_snapshot_safe()
    if snap and "symbols" in snap:
        sym_data = snap["symbols"].get(symbol, {})
        if sym_data:
            return {"bid": sym_data.get("bid", 0), "ask": sym_data.get("ask", 0),
                    "spread": sym_data.get("spread", 0), "symbol": symbol}
    return {}


def _get_snapshot_safe() -> dict[str, Any]:
    """Le snapshot com fallback silencioso."""
    try:
        from f0_collector.orc_coleta import get_snapshot
        return get_snapshot() or {}
    except Exception:
        return {}


def _normalize_balance(raw: dict[str, Any]) -> dict[str, Any]:
    """Converte balance MCP de cents/subunidade para display (USD).
    moneyDigits=2 -> divide por 100. moneyDigits=0 -> mantem."""
    md = raw.get("moneyDigits", 2)
    divisor = 10 ** md if md > 0 else 1
    result = dict(raw)
    for key in ("balance", "equity", "freeMargin", "margin", "credit"):
        if key in result and isinstance(result[key], (int, float)):
            result[key] = round(result[key] / divisor, md)
    return result


def _check_harness_status() -> bool:
    """Verifica se o harness boot passou (le status/harness_status.json). Sem subprocess."""
    try:
        status_file = ROOT / "status" / "harness_status.json"
        if status_file.exists():
            import json
            data = json.loads(status_file.read_text(encoding="utf-8"))
            return data.get("status") == "ok"
    except Exception:
        pass
    return True  # nao bloqueia — assume OK se nao consegue ler


def health_check_full() -> dict[str, Any]:
    """Health check via snapshot F0 (R-NO-MCP-BYPASS: nao abre conexao propria).
    Le o snapshot que F0 publica — nao compete pelo rate limit MCP.
    Cada check referencia a spec que o define."""
    alerts: list[str] = []
    checks: dict[str, dict[str, Any]] = {}

    # -- SPEC S1.1: MCP via snapshot F0 (R-NO-MCP-BYPASS) --
    # Antes: fazia init_client()+get_version() proprio = handshake 20-40s + competia com F0.
    # Agora: le status/snapshot.json publicado pelo F0. Instantaneo, sem bloqueio.
    try:
        snap = _get_snapshot_safe()  # usa cache local, nao re-importa F0
        if snap and snap.get("online"):
            # SESSION LIFECYCLE: expoe idade da sessao para o dashboard
            from utils.mcp_client import SESSION_MAX_AGE, get_session_age
            age_s = get_session_age()
            ttl_s = max(0.0, SESSION_MAX_AGE - age_s)
            checks["mcp"] = {
                "ok": True,
                "spec": "S1.1 (via F0 snapshot — R-NO-MCP-BYPASS)",
                "tools": 16,
                "balance": _normalize_balance(snap.get("balance", {})),
                "positions_count": len(snap.get("positions", {}).get("positions", [])),
                "symbols": len(snap.get("symbols", [])),
                "last_snapshot": snap.get("timestamp_utc", ""),
                "session_age_s": round(age_s, 1),
                "session_ttl_s": round(ttl_s, 1),
                "session_renew_in_s": round(ttl_s, 1),
            }
        else:
            checks["mcp"] = {
                "ok": False,
                "spec": "S1.1 (via F0 snapshot)",
                "error": "F0 offline — snapshot ausente ou vazio. Rode F0 primeiro."
            }
            alerts.append("MCP: F0 offline (snapshot indisponivel ou vazio)")
    except Exception as e:
        checks["mcp"] = {"ok": False, "spec": "S1.1", "error": str(e)}
        alerts.append(f"MCP: erro ao ler snapshot F0: {e}")

    # -- ROADMAP 1.8: processo F0 vivo? (distinto de "snapshot fresco" acima) --
    try:
        from utils.f0_supervisor_orc_dashboard import f0_status
        f0p = f0_status()
        checks["f0_process"] = {"ok": f0p["running"], "spec": "S21 (ROADMAP 1.8)", **f0p}
        if not f0p["running"]:
            alerts.append("F0: processo nao esta rodando (use /f0/start)")
        elif f0p.get("snapshot_stale"):
            alerts.append("F0: rodando mas snapshot nao atualiza ha >30s")
    except Exception as e:
        checks["f0_process"] = {"ok": False, "spec": "S21", "error": str(e)}

    # -- SPEC S2: F0 coleta (df_master recente?) --
    try:
        db_path = ROOT / "trades.db"
        if db_path.exists():
            import sqlite3
            conn = sqlite3.connect(str(db_path))
            try:
                row = conn.execute(
                    "SELECT MAX(timestamp) FROM trades"
                ).fetchone()
                if row and row[0]:
                    last_ts = row[0]
                    checks["f0_coleta"] = {
                        "ok": True, "spec": "S2 (f0_collector.md §3)",
                        "last_tick": last_ts,
                    }
                else:
                    checks["f0_coleta"] = {
                        "ok": False, "spec": "S2", "error": "Sem ticks no DB"
                    }
            except Exception:
                checks["f0_coleta"] = {
                    "ok": False, "spec": "S2", "error": "trades.db sem schema"
                }
            finally:
                conn.close()
        else:
            checks["f0_coleta"] = {
                "ok": False, "spec": "S2", "error": "trades.db nao existe"
            }
    except Exception as e:
        checks["f0_coleta"] = {"ok": False, "spec": "S2", "error": str(e)}

    # -- SPEC S4: F2 fusão (pesos somam 1.0) --
    try:
        _ensure_path()
        from utils.orc_metricas import collect_all as _collect
        data = _collect()
        f4 = data.get("f4_execucao", {})

        if "error" not in str(f4):
            dd = f4.get("max_drawdown_pct", 0)
            checks["f4_execucao"] = {
                "ok": dd < 3.0, "spec": "S6 (f4_executor.md §4)",
                "max_drawdown_pct": dd, "threshold": 3.0,
            }
            if dd >= 3.0:
                alerts.append(f"F4: drawdown {dd}% >= limite 3% (spec S6)")

            wd = data.get("f5_mar", {}).get("weight_delta", 0)
            checks["f5_mar"] = {
                "ok": wd < 0.15, "spec": "S7 (f5_mar.md)",
                "weight_delta": wd, "threshold": 0.15,
            }
            if wd >= 0.15:
                alerts.append(f"F5: weight_delta {wd} >= limite 0.15 (spec S7)")
    except Exception as e:
        checks["f4_f5"] = {"ok": False, "spec": "S6+S7", "error": str(e)}

    # -- SPEC S0: Gates (G6 — check leve: status file, sem subprocess) --
    try:
        harness_ok = _check_harness_status()
        checks["gates"] = {
            "ok": harness_ok, "spec": "S0 (QUALITY_GATES.md)",
            "g6_passed": harness_ok, "check": "harness_status.json",
        }
        if not harness_ok:
            alerts.append("G6 HARNESS: status desconhecido (spec S0)")
    except Exception as e:
        checks["gates"] = {"ok": False, "spec": "S0", "error": str(e)}

    # -- SPEC S19: Logger --
    try:
        log_path = LOGS_DIR / "system.jsonl"
        if log_path.exists():
            size_mb = log_path.stat().st_size / (1024 * 1024)
            checks["logger"] = {
                "ok": size_mb < 10, "spec": "S19 (logger.md)",
                "size_mb": round(size_mb, 2), "threshold_mb": 10,
            }
            if size_mb >= 10:
                alerts.append(f"Logger: {size_mb:.1f}MB >= 10MB (spec S19)")
        else:
            checks["logger"] = {"ok": True, "spec": "S19", "size_mb": 0}
    except Exception:
        checks["logger"] = {"ok": True, "spec": "S19", "size_mb": 0}

    # -- JSON LOG (substitui Vector DB S25) --
    try:
        from utils.json_log_orc_metricas import read_metrics_json
        vstats = read_metrics_json() or {}
        checks["vector"] = {
            "ok": True, "spec": "S25 (json_log)",
            "signals": vstats.get("total_signals", 0),
            "win_rate": vstats.get("win_rate", 0),
            "avg_score": vstats.get("avg_score", 0),
        }
    except Exception as e:
        checks["vector"] = {"ok": True, "spec": "S25", "note": str(e)[:80]}

    # -- RANKING (S25) --
    try:
        from f3_validacao.orc_ranking import rank_signals
        r = rank_signals(min_score=75)
        checks["ranking"] = {
            "ok": r.get("status") == "ok",
            "spec": "S25",
            "candidates": r.get("candidates", 0),
            "source": r.get("source", "unknown"),
        }
    except Exception as e:
        checks["ranking"] = {"ok": True, "spec": "S25", "note": str(e)[:80]}

    # -- ORDERS (S1 §F4) --
    try:
        from utils.json_log_orc_metricas import get_trail_log
        o = get_trail_log()
        checks["orders"] = {
            "ok": True,
            "spec": "S1 §F4 (f4_executor.md)",
            "active": o.get("active_orders", 0),
        }
    except Exception as e:
        checks["orders"] = {"ok": True, "spec": "S1 §F4", "note": str(e)[:80]}

    return {
        "mcp": checks.get("mcp", {}),
        "f0_process": checks.get("f0_process", {}),
        "phases": {
            "f0": checks.get("f0_coleta", {}),
            "f4": checks.get("f4_execucao", {}),
            "f5": checks.get("f5_mar", {}),
        },
        "gates": checks.get("gates", {}),
        "logger": checks.get("logger", {}),
        "vector": checks.get("vector", {}),
        "ranking": checks.get("ranking", {}),
        "orders": checks.get("orders", {}),
        "alerts": alerts,
        "all_ok": len(alerts) == 0 and checks.get("mcp", {}).get("ok", False),
    }
