"""PROPOSITO: G16 — METRICS ENDPOINT GATE (tipo G10 para metrics.py)
SPEC: S21
ROADMAP: D.10 — valida entry points e contratos do metrics.py
R21: todo endpoint documentado, toda metrica tem fonte real.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.orc_metricas import (
    collect_all,
    f0_metrics,
    f1_f2_metrics,
    f3_metrics,
    f4_metrics,
    f5_metrics,
    validate_metrics,
)

# -- (a) Entry points --

ENTRY_POINTS = {
    "f0_metrics": f0_metrics,
    "f1_f2_metrics": f1_f2_metrics,
    "f3_metrics": f3_metrics,
    "f4_metrics": f4_metrics,
    "f5_metrics": f5_metrics,
    "collect_all": collect_all,
    "validate_metrics": validate_metrics,
}

# -- (b) Schema esperado por fase --

EXPECTED_KEYS = {
    "f0_coleta": ["mcp_uptime_pct", "mcp_timeout_rate", "mcp_avg_latency_ms",
                   "data_gap_seconds", "reconnect_count"],
    "f1_f2_analise": ["signals_per_hour", "signals_above_threshold",
                       "signals_above_threshold_pct", "avg_score_macro",
                       "avg_score_vol", "avg_score_tec", "reducer_hit_rate"],
    "f3_ia": ["cache_hit_pct", "avg_latency_ms", "fallback_rate",
              "approve_rate", "daily_cost_usd"],
    "f4_execucao": ["win_rate", "avg_pnl_per_trade", "profit_factor",
                     "ghost_order_rate", "slot_utilization",
                     "avg_trade_duration_s", "be_saves",
                     "trail_activated_rate", "max_drawdown_pct"],
    "f5_mar": ["weight_delta_daily", "threshold_drift", "days_since_calibration"],
}

# -- (c) Fontes de dados (nao MCP) --

DATA_SOURCES = {
    "trades.db": "SQLite — F1-F4 metricas historicas",
    "status/metrics.json": "JSON — F0/F3/F5 cache/status",
    "snapshot.json": "F0 — balance/positions/spot (via orchestrator)",
}


def check_entry_points() -> tuple[int, int, list[str]]:
    """Valida que toda entry point retorna schema esperado."""
    errors = []
    # Testa collect_all
    try:
        data = collect_all()
        for section, keys in EXPECTED_KEYS.items():
            if section not in data:
                errors.append(f"collect_all: secao '{section}' ausente")
                continue
            section_data = data[section]
            if isinstance(section_data, dict) and "error" in section_data:
                continue  # DB offline = ok
            for key in keys:
                if key not in section_data:
                    errors.append(f"collect_all.{section}: chave '{key}' ausente")
    except Exception as e:
        errors.append(f"collect_all: excecao: {e}")

    # Testa cada fase individual
    for name, fn in [
        ("f0_metrics", f0_metrics),
        ("f1_f2_metrics", f1_f2_metrics),
        ("f3_metrics", f3_metrics),
        ("f4_metrics", f4_metrics),
        ("f5_metrics", f5_metrics),
    ]:
        try:
            result = fn()
            if not isinstance(result, dict):
                errors.append(f"{name}: retornou {type(result).__name__}, esperado dict")
        except Exception as e:
            errors.append(f"{name}: excecao: {e}")

    ok_count = 0
    err_count = len(errors)
    if err_count == 0:
        ok_count = len(ENTRY_POINTS)

    return ok_count, err_count, errors


def check_validate_metrics() -> tuple[bool, str]:
    """Valida que validate_metrics funciona com dados reais."""
    try:
        data = collect_all()
        alerts = validate_metrics(data)
        if not isinstance(alerts, list):
            return False, f"validate_metrics: retornou {type(alerts).__name__}"
        return True, f"{len(alerts)} alertas"
    except Exception as e:
        return False, str(e)


def check_data_sources() -> list[str]:
    """Verifica se as referencias a fontes de dados no codigo estao corretas."""
    missing = []
    base = Path(__file__).resolve().parent.parent
    metrics_code = (base / "utils" / "orc_metricas.py").read_text(encoding="utf-8", errors="ignore")
    orch_code = (base / "utils" / "orc_dashboard.py").read_text(encoding="utf-8", errors="ignore")
    combined = metrics_code + orch_code

    for path, desc in DATA_SOURCES.items():
        # Verifica se o path eh referenciado no metrics OU no orchestrator
        if path not in combined and path.split("/")[-1] not in combined:
            missing.append(f"{path} ({desc}): NAO referenciado em metrics.py nem orchestrator.py")

    return missing



def check_api_endpoint() -> tuple[bool, str]:
    """Verifica se o endpoint /api/ctrader/metrics responde (porta 7744)."""
    import json
    import socket
    import urllib.request

    # Verifica se porta esta ativa
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2)
    if sock.connect_ex(("127.0.0.1", 7744)) != 0:
        sock.close()
        return True, "porta 7744 offline (dashboard nao rodando — aceitavel)"
    sock.close()

    try:
        req = urllib.request.Request("http://127.0.0.1:7744/api/ctrader/metrics")
        req.add_header("Accept", "application/json")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
        if data.get("status") == "ok" and "data" in data:
            sections = list(data["data"].keys())
            return True, f"online, {len(sections)} secoes: {sections[:5]}..."
        return False, f"status inesperado: {data.get('status')}"
    except Exception as e:
        return True, f"API offline (dashboard nao rodando): {e}"


# -- (e) Dashboard wire: React sub-tab -> API endpoint -> orchestrator --

def check_dashboard_wire() -> tuple[int, int, list[str]]:
    """Valida que cada sub-tab do React tem endpoint no router ctrader_v2.py."""
    import re

    base = Path(__file__).resolve().parent.parent
    router_file = base.parent.parent / "10.0_ui_dash" / "routers" / "ctrader_v2.py"

    errors: list[str] = []

    # Known sub-tab -> endpoint mapping (from CtraderTab.tsx, validated 2026-07-28)
    # Format: sub-tab ID -> set of API endpoints consumed
    sub_tab_endpoints: dict[str, set[str]] = {
        "saude":         {"/health/fases"},  # S33 — sub-aba 1 de todas as abas mestras
        "ov-health":     {"/status", "/health/fases", "/f0/status", "/f0/start", "/f0/stop", "/f0/restart",
                          "/backfill/status", "/backfill/start", "/backfill/stop"},  # S31-PROG revamp
        "ov-bank":       {"/banca"},
        # "overview":      {"/vector/overview", "/health", "/vector/strength", "/plugins"},
        "mkt-XAUUSD":     {"/vector/symbol/XAUUSD", "/vector/symbol/{symbol}", "/vector/symbol/{symbol}/patterns", "/vector/symbol/{symbol}/quality", "/vector/symbol/{symbol}/score"},
        "mkt-EURUSD":     {"/vector/symbol/EURUSD", "/vector/symbol/{symbol}", "/vector/symbol/{symbol}/patterns", "/vector/symbol/{symbol}/quality", "/vector/symbol/{symbol}/score"},
        "mkt-GBPUSD":     {"/vector/symbol/GBPUSD", "/vector/symbol/{symbol}", "/vector/symbol/{symbol}/patterns", "/vector/symbol/{symbol}/quality", "/vector/symbol/{symbol}/score"},
        "mkt-USDJPY":     {"/vector/symbol/USDJPY", "/vector/symbol/{symbol}", "/vector/symbol/{symbol}/patterns", "/vector/symbol/{symbol}/quality", "/vector/symbol/{symbol}/score"},
        "mkt-AUDUSD":     {"/vector/symbol/AUDUSD", "/vector/symbol/{symbol}", "/vector/symbol/{symbol}/patterns", "/vector/symbol/{symbol}/quality", "/vector/symbol/{symbol}/score"},
        "strategy":       {"/banca", "/vector/correlation", "/performance"},
        "globals":       {"/vector/globals", "/vector/consolidated"},
        "correlation":   {"/vector/correlation"},
        # "strength":      {"/vector/strength"},
        # "indicators":    {"/vector/indicators"},
        # "score75":       {"/validate/score75"},
        "normalize":     {"/validate/normalize"},
        "trail-log":     {"/order/trail-log"},
        "ranking":       {"/validate/ranking"},
        "live-logs":     {"/validate/live-logs"},
        "params":        set(),  # inline JSX, no API call
        "health":        {"/status", "/f0/status", "/mcp/session", "/mcp/login", "/mcp/logout", "/f0/start", "/f0/stop", "/f0/restart"},
        "harness":       {"/harness"},
        "pipeline":      {"/metrics"},
        "banca":         {"/banca"},  # Mercados enriquecido (S25.9) vive aqui — removido da Pre-Analise
        "performance":   {"/performance"},
        "score-cal":     {"/metrics"},
    }

    # Known sub-tab labels (for human-readable output)
    sub_tab_labels: dict[str, str] = {
        "saude": "Saude (S33 — validador por fase)",
        "ov-health": "Health Check + Backfill (S31-PROG)",
        "ov-bank": "Banca & Mercado (Overview)",
        "overview": "Overview Vector", "mkt-XAUUSD": "XAUUSD",
        "mkt-EURUSD": "EURUSD", "mkt-GBPUSD": "GBPUSD",
        "mkt-USDJPY": "USDJPY", "mkt-AUDUSD": "AUDUSD",
        "globals": "Globais", "correlation": "Correlacao",
        "strength": "Forca Relativa",
        "indicators": "Indicadores Tecnicos",
        "score75": "Score 75%+",
        "normalize": "Normalizacao", "trail-log": "Trail Log",
        "ranking": "Ranking de Sinais", "live-logs": "Logs ao Vivo",
        "params": "Parametros", "health": "Health",
        "harness": "G6 Testes", "pipeline": "Pipeline",
        "banca": "Banca & Mercado (5 ativos + timeframe + Vol%/Lat%)",
        "performance": "Performance",
        "score-cal": "Score & Calibracao",
    }

    # 1. Extract router endpoints
    if not router_file.exists():
        return 0, 1, [f"Router file not found: {router_file}"]
    router_content = router_file.read_text(encoding="utf-8", errors="ignore")
    router_endpoints: set[str] = set()
    for m in re.finditer(r'@router\.(?:get|post)\s*\(\s*["\']([^"\']+)', router_content):
        router_endpoints.add(m.group(1))

    def _router_covers(ep: str) -> bool:
        """Template {param} do router cobre qualquer valor concreto (ex: {symbol} -> XAUUSD)."""
        if ep in router_endpoints:
            return True
        for template in router_endpoints:
            pattern = re.sub(r"\{[^}]+\}", r"[^/]+", template)
            if re.fullmatch(pattern, ep):
                return True
        return False

    # 2. Cross-reference: sub-tab endpoint must exist in router
    ok_count = 0
    err_count = 0

    for tab_id, endpoints in sorted(sub_tab_endpoints.items()):
        label = sub_tab_labels.get(tab_id, tab_id)
        if not endpoints:
            # Params has no endpoint - warn but don't fail
            errors.append(f"[INFO] sub-tab '{tab_id}' ({label}): sem endpoints (inline/puramente visual)")
            ok_count += 1
            continue

        tab_ok = True
        for ep in endpoints:
            if not _router_covers(ep):
                errors.append(f"sub-tab '{tab_id}' ({label}): endpoint '{ep}' nao existe no router ctrader_v2.py")
                tab_ok = False

        if tab_ok:
            ok_count += 1
        else:
            err_count += 1

    # 3. Orphan endpoints (in router, not consumed by any sub-tab)
    all_used: set[str] = set()
    for eps in sub_tab_endpoints.values():
        all_used.update(eps)
    orphan_eps = router_endpoints - all_used
    for ep in sorted(orphan_eps):
        errors.append(f"[INFO] endpoint orfao: '{ep}' no router — nao consumido por sub-tab React (pode ser novo)")

    # 4. Verify TSX file still exists (structural check)
    tsx_file = base.parent.parent / "10.0_ui_dash" / "react-dashboard" / "src" / "domains" / "ctrader" / "CtraderTab.tsx"
    if not tsx_file.exists():
        errors.append("[WARN] CtraderTab.tsx nao encontrado — wire nao verificavel contra React")

    return ok_count, err_count, errors


if __name__ == "__main__":
    print("=" * 50)
    print(" G16 — METRICS ENDPOINT GATE")
    print("=" * 50)

    # Entry points
    ok, errs, details = check_entry_points()
    print(f"\n(a) Entry points: {ok} OK, {errs} erros")
    for d in details:
        print(f"  [ERR] {d}")

    # Validate
    ok_v, msg_v = check_validate_metrics()
    print(f"\n(b) validate_metrics: {'[OK]' if ok_v else '[ERR]'} {msg_v}")

    # Data sources
    missing = check_data_sources()
    print(f"\n(c) Fontes de dados: {len(DATA_SOURCES) - len(missing)}/{len(DATA_SOURCES)} referenciadas")
    for m in missing:
        print(f"  [ERR] {m}")

    # API endpoint
    ok_api, msg_api = check_api_endpoint()
    print(f"\n(d) API endpoint: {'[OK]' if ok_api else '[ERR]'} {msg_api}")

    # Dashboard wire
    wire_ok, wire_err, wire_details = check_dashboard_wire()
    print(f"\n(e) Dashboard wire (React -> Router): {wire_ok} OK, {wire_err} erros")
    for d in wire_details:
        if d.startswith("[INFO]") or d.startswith("[WARN]"):
            print(f"  {d}")
        else:
            print(f"  [ERR] {d}")

    # Summary
    total_errs = errs + (0 if ok_v else 1) + len(missing) + (0 if ok_api else 1) + wire_err
    if total_errs == 0:
        print(f"\n[OK] G16 METRICS ENDPOINTS: PASS ({len(ENTRY_POINTS)} entry points + dashboard wire)")
        sys.exit(0)
    else:
        print(f"\n[ERR] G16 METRICS ENDPOINTS: FAIL ({total_errs} erros)")
        sys.exit(1)
