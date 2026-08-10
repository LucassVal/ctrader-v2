"""PROPOSITO: check_deps.py — Preflight de dependencias + configuracao dos gates G0-G18.
SPEC: S20.2 / QUALITY_GATES.md
ROADMAP: D.10 — verifica pip + npm + qualidade de configuracao.
R-NO-SILENT-FAIL: toda dep/config ausente gera mensagem clara + exit 1.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

CTRADER_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = CTRADER_ROOT.parent.parent / "10.0_ui_dash" / "react-dashboard"

# -- Deps --

PIP_DEPS: list[tuple[str, str]] = [
    ("ruff",            "ruff>=0.4"),
    ("slop_detector",   "ai-slop-detector==3.8.7"),
    ("mockbuster",      "mockbuster==0.1.4"),
    ("pytest",          "pytest>=8"),
]

NPM_DEPS: list[tuple[str, str]] = [
    ("eslint",   "eslint (via npm install)"),
    ("oxlint",   "oxlint (via npm install)"),
]

# -- Config quality checks --

CONFIG_CHECKS: list[tuple[str, str, str]] = [
    # (descricao, arquivo, check)
    ("ruff.toml", str(CTRADER_ROOT / "ruff.toml"), "ruff config existe?"),
    ("oxlintrc.json", str(FRONTEND_DIR / "oxlintrc.json"), "oxlint config existe?"),
    ("eslint.config.js", str(FRONTEND_DIR / "eslint.config.js"), "eslint config existe?"),
]


def check_pip_deps() -> list[str]:
    errors: list[str] = []
    for mod, pkg in PIP_DEPS:
        if importlib.util.find_spec(mod) is None:
            errors.append(f"[FAIL] pip: '{mod}' ausente. Instalar: pip install \"{pkg}\"")
    return errors


def check_npm_deps() -> list[str]:
    errors: list[str] = []
    if not FRONTEND_DIR.exists():
        errors.append(f"[FAIL] npm: diretorio {FRONTEND_DIR} nao encontrado")
        return errors
    node_modules = FRONTEND_DIR / "node_modules"
    if not node_modules.exists():
        errors.append("[FAIL] npm: node_modules ausente. Rodar: cd react-dashboard && npm install")
        return errors
    bin_dir = node_modules / ".bin"
    for bin_name, _desc in NPM_DEPS:
        found = (bin_dir / f"{bin_name}.cmd").exists() or (bin_dir / bin_name).exists()
        if not found:
            errors.append(f"[FAIL] npm: '{bin_name}' ausente. Rodar: cd react-dashboard && npm install")
    return errors


def check_configs() -> list[str]:
    errors: list[str] = []
    for name, path, desc in CONFIG_CHECKS:
        p = Path(path)
        if not p.exists():
            errors.append(f"[FAIL] Config: {name} ausente ({desc})")
            continue

        # Check content quality
        content = p.read_text(encoding="utf-8", errors="ignore")

        if "oxlintrc.json" in name and '"warn"' in content:
                errors.append("[FAIL] oxlintrc.json: contem regra 'warn' — todas devem ser 'error' ou 'off'")

        if "eslint.config" in name and ("'warn'" in content or '"warn"' in content):
                errors.append("[FAIL] eslint.config: contem regra 'warn' — todas devem ser 'error' ou 'off'")

    return errors


def check_ruff_rules() -> list[str]:
    """Verifica se ruff esta usando regras alem do default."""
    errors: list[str] = []
    ruff_toml = CTRADER_ROOT / "ruff.toml"
    ppt = CTRADER_ROOT / "pyproject.toml"

    if ruff_toml.exists():
        content = ruff_toml.read_text(encoding="utf-8", errors="ignore")
        if 'select' not in content.lower():
            errors.append("[INFO] ruff: usando regras default (recomendado). Para max potencial, adicionar 'extend-select'.")
    elif ppt.exists():
        content = ppt.read_text(encoding="utf-8", errors="ignore")
        if '[tool.ruff]' not in content:
            errors.append("[INFO] ruff: sem config explicita. Usando defaults.")
    else:
        errors.append("[WARN] ruff: sem arquivo de config (ruff.toml ou pyproject.toml)")

    return errors


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "--all"

    print("=" * 60)
    print(" PREFLIGHT — check_deps.py (gates G0-G18)")
    print(f" ctrader: {CTRADER_ROOT.name}")
    print("=" * 60)

    all_errors: list[str] = []
    info_messages: list[str] = []

    # 1. Pip deps
    if mode not in ("--npm-only",):
        print("\n[1/3] Verificando dependencias pip...")
        pip_errs = check_pip_deps()
        if pip_errs:
            for e in pip_errs:
                print(f"\n{e}", file=sys.stderr)
            all_errors.extend(pip_errs)
        else:
            deps = ", ".join(m for m, _ in PIP_DEPS)
            print(f"  [OK] {len(PIP_DEPS)} deps: {deps}")

    # 2. Npm deps
    if mode not in ("--pip-only",):
        print("\n[2/3] Verificando dependencias npm...")
        npm_errs = check_npm_deps()
        if npm_errs:
            for e in npm_errs:
                print(f"\n{e}", file=sys.stderr)
            all_errors.extend(npm_errs)
        else:
            deps = ", ".join(n for n, _ in NPM_DEPS)
            print(f"  [OK] {len(NPM_DEPS)} deps: {deps}")

    # 3. Config quality
    print("\n[3/3] Verificando qualidade de configuracao...")
    cfg_errs = check_configs()
    if cfg_errs:
        for e in cfg_errs:
            print(f"\n{e}", file=sys.stderr)
        all_errors.extend(cfg_errs)

    ruff_info = check_ruff_rules()
    for info in ruff_info:
        print(f"  {info}")
        info_messages.append(info)

    ok = len(CONFIG_CHECKS) - len(cfg_errs)
    print(f"  [OK] {ok}/{len(CONFIG_CHECKS)} arquivos de config validos")

    # Final
    print()
    if all_errors:
        print(f"[FAIL] PREFLIGHT: {len(all_errors)} problema(s). Corrigir antes dos gates.")
        return 1

    print("[PASS] PREFLIGHT: todas as dependencias e configuracoes OK.")
    if info_messages:
        print(f"  ({len(info_messages)} sugestoes de otimizacao — veja acima)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
