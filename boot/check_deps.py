"""
PROPOSITO: Verificador de dependencias do Neocortex V44 + cTrader V2.
SPEC: S0 (pre-flight), S40 (TA-Lib)
ROADMAP: FASE 6 (pre-flight validation)
USO: python check_deps.py
SAIDA: JSON puro (stdout) — sem stdout extra, sem logs.
@NC-TELEM: check_deps
@NC-TRACE: boot-pre-flight

Integrado no pre-flight do Abrir_NeoCortex_NovaPulse.ps1.
IMPORTANTE: saida DEVE ser JSON puro. Qualquer print antes do JSON quebra o ConvertFrom-Json do PowerShell.
"""

import importlib
import json
import sys
from pathlib import Path

CTRADER = Path(__file__).resolve().parent / "11.0_apps" / "ctrader"

CRITICAL = {
    "numpy": ("numpy", ""),
    "pandas": ("pandas", ""),
    "vectorbt": ("vectorbt", ""),
    "talib": ("talib", "TA-Lib (61 candlestick patterns)"),
    "numba": ("numba", "vectorbt JIT"),
    "fastapi": ("fastapi", "Dashboard API"),
    "uvicorn": ("uvicorn", "ASGI server"),
    "pydantic": ("pydantic", "Schema validation"),
    "requests": ("requests", "HTTP client"),
    "scipy": ("scipy", "vectorbt stats"),
}

RECOMMENDED = {
    "plotly": ("plotly", "Dashboard charts"),
    "sklearn": ("sklearn", "ML labeling"),
    "dill": ("dill", "vectorbt persistence"),
    "tqdm": ("tqdm", "Progress bars"),
    "matplotlib": ("matplotlib", "Plots offline"),
}

CTRADER_ORQS = [
    ("utils.orc_vectorbt", "VectorBT indicators"),
    ("f3_validacao.orc_ranking", "Ranking F3"),
    ("utils.orc_mercado", "Market normalization"),
    ("utils.orc_indices", "Correlation matrix"),
    ("f2_fusao.orc_score", "Score S32"),
    ("utils.orc_pattern", "Pattern matching"),
    ("utils.orc_calibracao", "Calibration F5"),
    ("utils.orc_metricas", "29 metrics"),
    ("utils.orc_dashboard", "Dashboard hub"),
    ("utils.mcp_client", "MCP gateway"),
    ("utils.resample", "M1->M5/M15 resample"),
    ("utils.orc_bloco1", "Bloco 1 Torneio (S41)"),
    ("utils.orc_bloco2", "Bloco 2 Sobrevivencia (S42)"),
    ("utils.orc_grid", "Grid/Walk-Forward (S43)"),
    ("f2_fusao.orc_fusao", "Fusion F2"),
]


def _check(module_name):
    try:
        importlib.import_module(module_name)
        return True, ""
    except Exception as e:
        return False, str(e)[:120]


def main():
    sys.path.insert(0, str(CTRADER))
    results = {"status": "ok", "critical": {}, "recommended": {}, "orquestradores": {}, "actions": []}
    all_ok = True

    for import_name, (display, desc) in CRITICAL.items():
        ok, err = _check(import_name)
        results["critical"][display] = {"ok": ok, "description": desc, "error": err}
        if not ok:
            all_ok = False
            results["actions"].append(f"pip install {import_name.split('.')[0]}")

    for import_name, (display, desc) in RECOMMENDED.items():
        ok, _ = _check(import_name)
        results["recommended"][display] = {"ok": ok, "description": desc}

    for module_name, desc in CTRADER_ORQS:
        ok, err = _check(module_name)
        results["orquestradores"][module_name] = {"ok": ok, "description": desc, "error": err}
        if not ok:
            all_ok = False

    if results["critical"].get("talib", {}).get("ok"):
        import talib
        results["talib"] = {"version": talib.__version__, "patterns": 61}

    if results["critical"].get("vectorbt", {}).get("ok"):
        import vectorbt as vbt
        results["vectorbt"] = {"version": vbt.__version__}

    results["all_ok"] = all_ok
    sys.stdout.write(json.dumps(results, indent=2, ensure_ascii=False) + "\n")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
