"""PROPOSITO: Harness Boot -- validacao pre-flight de TODOS os orquestradores (Fase 0).
SPEC: S0
ROADMAP: 0.G6 -- boot harness que le todos os orquestradores antes do ciclo de trade.
FLOW:   harness_boot -> importa cada orquestrador -> valida filhos wireados ->
        verifica contratos JSON -> reporta status geral.
        Roda ANTES do F0 iniciar coleta -- se falhar, ctrader nao sobe.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ═══════════════════════════════════════════
# Orquestradores a validar (INDEX SSOT)
# ═══════════════════════════════════════════

ORCHESTRATORS = {
    "F0": {
        "module": "f0_collector.orc_coleta",
        "attrs": ["Collector", "take_snapshot", "get_snapshot", "place_order", "exit_position", "move_stops", "kill_pending"],
        "children": ["poller_orc_coleta", "storage_orc_coleta"],
        "contract": "snapshot.json",
    },
    "F1": {
        "module": "f1_analyzer.orc_analise",
        "attrs": ["analyze"],
        "children": ["pillars_orc_analise", "micro_orc_analise", "sentiment_orc_analise", "dxy_orc_analise", "indicators_orc_analise"],
        "contract": "scores_raw.json",
    },
    "F2": {
        "module": "f2_fusao.orc_fusao",
        "attrs": ["fuse", "fuse_and_save"],
        "children": [],
        "contract": "fusion_output.json",
    },
    "F3": {
        "module": "f3_validacao.orc_validacao",
        "attrs": ["validate", "validate_and_save"],
        "children": [],
        "contract": "verdict.json",
    },
    "F4": {
        "module": "f4_executor.orc_execucao",
        "attrs": ["run_executor"],
        "children": ["monitor_orc_execucao", "safety_orc_execucao", "entry_orc_execucao", "gates_orc_execucao"],
        "contract": None,
    },
    "F4-sub": {
        "module": "f4_executor.orc_ordens",
        "attrs": ["ORDER_PARAMS", "get_params", "calculate_entry_params", "validate_signal_for_entry", "execute_oco_order", "check_scalp_timeout"],
        "children": ["entry_params_orc_ordens", "oco_orc_ordens", "scalp_timeout_orc_ordens"],
        "contract": None,
    },
    "F5": {
        "module": "f5_mar.orc_mar",
        "attrs": ["calibrate", "sync_history"],
        "children": ["rules_orc_mar", "trades_log_orc_mar", "mcp_sync_orc_mar"],
        "contract": "custom_rules.json",
    },
    "DASHBOARD": {
        "module": "utils.orc_dashboard",
        "attrs": ["health_check_full", "collect_all"],
        "children": [],
        "contract": None,
    },
    "METRICS": {
        "module": "utils.orc_metricas",
        "attrs": ["collect_all", "validate_metrics", "f0_metrics", "f1_f2_metrics", "f3_metrics", "f4_metrics", "f5_metrics"],
        "children": ["json_log_orc_metricas"],
        "contract": None,
    },
    "DATASOURCE": {
        "module": "utils.data_source",
        "attrs": ["get_snapshot", "get_balance", "get_markets_raw", "get_positions", "is_online"],
        "children": [],
        "contract": "status/snapshot.json",
    },
    "RANKING": {
        "module": "f3_validacao.orc_ranking",
        "attrs": ["rank_signals"],
        "children": [],
        "contract": "ranking.json",
    },
    "MERCADO": {
        "module": "utils.orc_mercado",
        "attrs": ["normalize_markets", "_read_snapshot"],
        "children": [],
        "contract": "status/snapshot.json",
    },
    "INDICES": {
        "module": "utils.orc_indices",
        "attrs": ["collect_indices", "correlate_with_markets"],
        "children": [],
        "contract": None,
    },
    "STORAGE": {
        "module": "f0_collector.storage_orc_coleta",
        "attrs": ["make_empty_df", "append_to_df", "save_parquet", "load_parquet"],
        "children": [],
        "contract": None,
    },
    "VECTORBT": {
        "module": "utils.orc_vectorbt",
        "attrs": ["compute_indicators", "compute_portfolio_stats"],
        "children": [],
        "contract": None,
    },
}


def validate_orchestrator(name: str, spec: dict) -> dict[str, Any]:
    """Valida um orquestrador: import + attrs + children + contract."""
    result: dict[str, Any] = {"name": name, "status": "ok", "errors": [], "warnings": []}

    # 1. Import module
    try:
        mod = __import__(spec["module"], fromlist=["*"])
    except ImportError as e:
        result["status"] = "FAIL"
        result["errors"].append(f"ImportError: {e}")
        return result
    except Exception as e:
        result["status"] = "FAIL"
        result["errors"].append(f"ModuleError: {e}")
        return result

    # 2. Validate attrs
    for attr in spec["attrs"]:
        if not hasattr(mod, attr):
            result["errors"].append(f"Missing attr: {attr}")
            result["status"] = "FAIL"

    # 3. Validate children (import check)
    for child in spec["children"]:
        child_module = spec["module"].rsplit(".", 1)[0] + "." + child
        try:
            __import__(child_module, fromlist=["*"])
        except ImportError:
            result["warnings"].append(f"Child not importable: {child_module}")

    # 4. Validate contract file
    contract = spec.get("contract")
    if contract:
        contract_path = ROOT / contract
        if contract_path.exists():
            try:
                json.loads(contract_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                result["errors"].append(f"Contract invalid: {contract} -- {e}")
                result["status"] = "FAIL"
        # Contract pode nao existir ainda (runtime artifact) -- so warn
        else:
            result["warnings"].append(f"Contract not found: {contract} (runtime artifact?)")

    return result


def run_boot_harness() -> dict[str, Any]:
    """Executa o harness boot completo -- todos os orquestradores."""
    results = {}
    all_ok = True

    for name, spec in ORCHESTRATORS.items():
        r = validate_orchestrator(name, spec)
        results[name] = r
        if r["status"] != "ok":
            all_ok = False

    # Cross-phase contracts
    cross_contracts = {
        "fusion_output.py": ROOT / "contracts/fusion_output.py",
    }
    for name, path in cross_contracts.items():
        if not path.exists():
            results.setdefault("CONTRACTS", {"errors": []})["errors"].append(f"Missing: {name}")
            all_ok = False

    # -- DATA VALIDATION (S26 — dados reais, nao so imports) --
    try:
        from utils.data_source import get_balance, get_markets_raw, is_online
        online = is_online()
        bal = get_balance()
        mkt = get_markets_raw()
        data_checks = []
        if online and bal.get("balance", 0) <= 0:
            data_checks.append("DataSource: online=True mas balance zerado — MCP pode estar desconectado")
        if online and len(mkt) < 5:
            data_checks.append(f"DataSource: esperado 5 mercados, encontrado {len(mkt)}")
        if not online:
            data_checks.append("DataSource: MCP offline — dados serao zero. Inicie F0.")

        results["DATA_VALIDATION"] = {
            "status": "warn" if data_checks else "ok",
            "online": online,
            "balance": bal.get("balance", 0),
            "markets": len(mkt),
            "alerts": data_checks,
        }
        if any("zerado" in d or "encontrado" in d for d in data_checks):
            all_ok = False
    except Exception as e:
        results["DATA_VALIDATION"] = {"status": "FAIL", "error": str(e)}
        all_ok = False

    return {
        "status": "ok" if all_ok else "FAIL",
        "checked": len(results),
        "passed": sum(1 for r in results.values() if isinstance(r, dict) and r.get("status") == "ok"),
        "orchestrators": results,
    }


def main():
    print("=" * 60)
    print(" HARNESS BOOT -- cTrader V2")
    print("=" * 60)

    report = run_boot_harness()

    for name, r in report["orchestrators"].items():
        if isinstance(r, dict):
            status = r["status"]
            icon = "[OK]" if status == "ok" else "[FAIL]" if status == "FAIL" else "[WARN]"
            print(f"  {icon} {name}")
            for e in r.get("errors", []):
                print(f"      ERR: {e}")
            for w in r.get("warnings", []):
                print(f"      WARN: {w}")
            for a in r.get("alerts", []):
                print(f"      ALERT: {a}")

    # DATA_VALIDATION summary
    dv = report["orchestrators"].get("DATA_VALIDATION", {})
    if dv:
        icon = "[OK]" if dv.get("status") == "ok" else "[WARN]"
        print(f"  {icon} DATA_VALIDATION (online={dv.get('online')}, bal={dv.get('balance')}, mkt={dv.get('markets')})")

    print(f"\n  Total: {report['passed']}/{report['checked']} passed")

    if report["status"] == "ok":
        print("\n[OK] HARNESS BOOT: PASS -- todos os orquestradores validados")
        sys.exit(0)
    else:
        print("\n[FAIL] HARNESS BOOT: FAIL -- corrigir antes de iniciar ctrader")
        sys.exit(1)


if __name__ == "__main__":
    main()
