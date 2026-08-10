"""PROPOSITO: G19 — Trava de alfandega: testes nao podem escrever runtime de producao.
SPEC: harness.md (ISOLAMENTO DE RUNTIME)
ROADMAP: NC-CTRADER-022
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

# ASCII safety
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

# Funcoes de escrita sob vigilancia
WRITE_FUNCTIONS: set[str] = {
    "take_snapshot",
    "save_parquet",
    "log_trade",
    "ensure_schema",
    "log_metrics_json",
}

# Parametros que indicam isolamento
ISOLATION_PARAMS: set[str] = {"tmp_path", "monkeypatch"}


def _has_isolation_params(node: ast.FunctionDef) -> bool:
    """Test function tem tmp_path ou monkeypatch nos parametros?"""
    return any(
        arg.arg in ISOLATION_PARAMS
        for arg in node.args.args
    )


def _find_write_calls(node: ast.FunctionDef) -> list[str]:
    """Encontra chamadas a funcoes de escrita dentro do corpo da funcao."""
    calls: list[str] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Name) and child.func.id in WRITE_FUNCTIONS:
            calls.append(child.func.id)
    return calls


def _is_test_function(node: ast.FunctionDef) -> bool:
    """Funcao com nome test_*"""
    return node.name.startswith("test_")


def scan_test_file(filepath: Path) -> list[str]:
    """Scaneia um arquivo de teste por violacoes de isolamento.
    Retorna lista de mensagens [ERR]."""
    errors: list[str] = []
    try:
        tree = ast.parse(filepath.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError as e:
        return [f"[ERR] {filepath}: SyntaxError — {e}"]

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if not _is_test_function(node):
            continue

        write_calls = _find_write_calls(node)
        if write_calls and not _has_isolation_params(node):
            funcs = ", ".join(sorted(set(write_calls)))
            errors.append(
                f"[ERR] {filepath}:{node.lineno} {node.name}() chama {funcs} "
                f"sem isolamento (tmp_path/monkeypatch)"
            )

    return errors


def main(test_dir: Path | None = None) -> int:
    """Entry point. Retorna 0=PASS, 1=FAIL."""
    if test_dir is None:
        test_dir = Path(__file__).resolve().parent.parent / "tests"

    if not test_dir.is_dir():
        print(f"[ERR] Diretorio de testes nao encontrado: {test_dir}")
        return 1

    all_errors: list[str] = []
    test_files = sorted(test_dir.rglob("test_*.py"))

    if not test_files:
        print(f"[ERR] Nenhum arquivo test_*.py encontrado em {test_dir}")
        return 1

    for tf in test_files:
        errs = scan_test_file(tf)
        all_errors.extend(errs)

    if all_errors:
        for e in all_errors:
            print(e)
        print(f"\n[ERR] G19 FAIL — {len(all_errors)} violacao(oes) de isolamento de runtime")
        print("Fix: adicionar tmp_path/monkeypatch nos parametros do teste e redirecionar paths")
        return 1

    print(f"[OK] G19 PASS — {len(test_files)} arquivos de teste isolados")
    return 0


if __name__ == "__main__":
    _dir = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    sys.exit(main(_dir))
