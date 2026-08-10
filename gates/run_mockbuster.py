"""PROPOSITO: G3 — MOCKBUSTER v3 (MCP-aware mock detector).
SPEC: S0 (QUALITY_GATES.md)
ROADMAP: D.10 — detecta hardcoded returns que simulam respostas MCP sem chamar MCP.
R21: le o snapshot mcp_tools_snapshot.json para conhecer os shapes esperados.
      Nao wire no orc_metricas — gate puro, sem dependencia de runtime.
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

CTRADER = Path(__file__).resolve().parent.parent

EXCLUDE_DIRS = {
    "ctrader-skills-official", "__pycache__", ".git",
    "99_archive", "legacy", "tests", "gates",
    "data", "status", "logs", "specs", "node_modules",
}

# -- MCP response shapes (from cTrader Remote HTTP MCP, validated 2026-07-24) --
# Keys that identify a dict as simulating an MCP response
MCP_RESPONSE_SHAPES: dict[str, set[str]] = {
    "get_balance": {"balance", "equity", "freeMargin"},
    "get_positions": {"positions", "positionId"},
    "get_spot_prices": {"prices", "symbolId", "bid", "ask"},
    "get_trendbars": {"trendbars", "candles"},
    "get_symbols": {"symbolId", "symbolName"},
    "get_pending_orders": {"orders", "orderId"},
    "get_order_history": {"orders", "orderId"},
    "get_deals": {"deals", "dealId"},
    "get_assets": {"assetId", "description"},
    "get_version": {"version"},
    "get_position_details": {"positionId", "details"},
}

# Minimum number of MCP keys that must match to trigger detection
MIN_KEY_MATCH = 2


def load_snapshot_tools() -> set[str]:
    """Load tool names from the G10 snapshot."""
    snap = CTRADER / "gates" / "mcp_tools_snapshot.json"
    if snap.exists():
        try:
            data = json.loads(snap.read_text(encoding="utf-8"))
            tools = data.get("tools", {})
            if isinstance(tools, dict):
                return set(tools.keys())
        except (json.JSONDecodeError, KeyError):
            pass
    # Fallback: hardcoded list from known contract
    return {
        "get_version", "get_balance", "get_assets", "get_symbols",
        "get_spot_prices", "get_trendbars", "get_positions",
        "get_position_details", "get_pending_orders",
        "get_order_history", "get_deals",
        "create_order", "amend_order", "cancel_order",
        "amend_position", "close_position",
    }


def _extract_tool_name(call_node: ast.Call) -> str | None:
    """Extract tool name from call_tool('name', ...)."""
    if call_node.args and isinstance(call_node.args[0], ast.Constant):
        val = call_node.args[0].value
        if isinstance(val, str):
            return val
    return None


def scan_file(filepath: Path, mcp_tools: set[str]) -> list[str]:
    """Scan a .py file for hardcoded MCP-like returns without calling MCP."""
    violations: list[str] = []
    rel = str(filepath.relative_to(CTRADER)).replace("\\", "/")

    try:
        code = filepath.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return [f"{rel}: unreadable"]

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []

    # Collect all MCP tool calls in this file
    mcp_calls: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        # call_tool("name", ...) or mcp_client.call_tool("name", ...)
        tool_name: str | None = None
        if (isinstance(node.func, ast.Name) and node.func.id == "call_tool") or (isinstance(node.func, ast.Attribute) and node.func.attr == "call_tool"):
            tool_name = _extract_tool_name(node)
        if tool_name:
            mcp_calls.add(tool_name)

    # If this file calls MCP, it's legitimate — skip
    if mcp_calls:
        return []

    # Check each function for hardcoded returns matching MCP shapes
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        # Find return statements with dict literals
        for child in ast.walk(node):
            if not isinstance(child, ast.Return):
                continue
            if not isinstance(child.value, ast.Dict):
                continue

            returned_dict = child.value
            # Extract keys from the returned dict
            returned_keys: set[str] = set()
            for key_node in returned_dict.keys:
                if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str):
                    returned_keys.add(key_node.value)

            if not returned_keys:
                continue

            # Only flag if ALL values are constants (true hardcoded), not computed/derived.
            # Mixed (some constants + some variables) = skip (likely data transformation).
            all_hardcoded = all(
                isinstance(v, ast.Constant)
                for v in returned_dict.values
            )
            if not all_hardcoded:
                continue

            # Check if these keys match any MCP response shape
            for tool_name, shape_keys in MCP_RESPONSE_SHAPES.items():
                if tool_name not in mcp_tools:
                    continue
                matches = returned_keys & shape_keys
                if len(matches) >= MIN_KEY_MATCH:
                    violations.append(
                        f"{rel}:{node.lineno} — funcao '{node.name}' retorna "
                        f"dict 100% hardcoded com chaves MCP ({sorted(matches)}) "
                        f"sem chamar MCP. Tool esperada: {tool_name}"
                    )
                    break  # One violation per function is enough

    # Also check for bare mock/stub comments in production code
    for i, line in enumerate(code.split("\n"), 1):
        stripped_lower = line.strip().lower()
        if any(s in stripped_lower for s in ["# mock", "# stub", "# fake", "# hardcoded"]):
            if not stripped_lower.startswith("#"):
                continue
            violations.append(f"{rel}:{i} — comentario suspeito: {line.strip()[:80]}")

    return violations


def main() -> int:
    target = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else CTRADER

    mcp_tools = load_snapshot_tools()

    py_files = [
        f for f in target.rglob("*.py")
        if not any(ex in str(f) for ex in EXCLUDE_DIRS)
    ]

    all_violations: list[str] = []
    for f in sorted(py_files):
        violations = scan_file(f, mcp_tools)
        all_violations.extend(violations)

    if all_violations:
        print(f"[ERR] MOCKBUSTER v3 (MCP-aware): {len(all_violations)} violacao(oes) em {len(py_files)} arquivos:")
        for v in all_violations[:20]:
            print(f"   {v}")
        if len(all_violations) > 20:
            print(f"   ... +{len(all_violations) - 20} mais")
        return 1

    print(f"[OK] MOCKBUSTER v3 (MCP-aware): {len(py_files)} arquivos limpos "
          f"({len(mcp_tools)} MCP tools, 0 bypass detectado)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
