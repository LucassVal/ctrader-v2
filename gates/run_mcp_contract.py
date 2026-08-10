#!/usr/bin/env python3
"""
G10 MCP-CONTRACT -- padronizacao das chamadas MCP (codigo x contrato x docs).
Teria pegado o bug ROADMAP 1.0 (get_trendbars sem fromTimestamp -> HTTP 400 sempre).

Tres fontes -> um diff:
  (a) CONTRATO  gates/mcp_tools_snapshot.json
                = tools/list do servidor + overlay `quirks` MEDIDOS (onde o schema mente)
  (b) CODIGO    AST de utils/mcp_client.py -- todo call_tool("nome", {...}) literal:
                tool existe? chave desconhecida? required (schema+quirks) presente?
  (c) DOCS      nomes de tool citados em specs/mcp_endpoints.md e no vendor
                remote-http-server.md devem existir no contrato (pega doc-drift
                tipo `trading.get_history`).

Modos:  (default) offline -- deterministico, roda no pre-commit
        --live     re-busca tools/list e diffa contra o snapshot (drift do servidor)
        --refresh  re-gera o snapshot a partir do servidor (preserva quirks)

Spec: S1.1 mcp_endpoints.md + S0 QUALITY_GATES.md.  TICKET: NC-CTRADER-012 (item 0.5)
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = ROOT / "gates" / "mcp_tools_snapshot.json"
MCP_CLIENT = ROOT / "utils" / "mcp_client.py"
DOC_FILES = [
    ROOT / "specs" / "mcp_endpoints.md",
    ROOT / "ctrader-skills-official" / "skills" / "ctrader-mcp-servers"
    / "references" / "remote-http-server.md",
]
TOOL_PREFIXES = ("get_", "create_", "close_", "amend_", "cancel_")
# Linhas de doc que registram AUSENCIA de tool nao contam como citacao
NEGATION_MARKERS = ("sem ", "nao expoe", "não expõe", "removed", "descontinu")

EXIT = 0


def fail(msg: str) -> None:
    global EXIT
    print(f"  [ERR] {msg}")
    EXIT = 1


def ok(msg: str) -> None:
    print(f"  [OK] {msg}")


def load_snapshot() -> dict:
    if not SNAPSHOT.exists():
        print(f"  [ERR] contrato ausente: {SNAPSHOT} -- rode --refresh com o servidor vivo")
        sys.exit(1)
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


def fetch_live_tools() -> dict[str, dict]:
    """Busca tools/list do servidor (usado por --live/--refresh)."""
    sys.path.insert(0, str(ROOT))
    import urllib.request

    from utils import mcp_client as mc
    mc.init_client(str(ROOT / "config.yaml"))
    payload = {"jsonrpc": "2.0", "method": "tools/list", "params": {}, "id": 10}
    req = urllib.request.Request(
        mc._mcp_url, data=json.dumps(payload).encode(),
        headers=mc._mcp_headers, method="POST",
    )
    body = urllib.request.urlopen(req, timeout=45).read().decode()
    res = mc._parse_sse_body(body)
    return {
        t["name"]: {
            "inputSchema": t.get("inputSchema", {}),
            "description": t.get("description", "")[:200],
        }
        for t in res["result"]["tools"]
    }


def extract_call_sites() -> list[tuple[int, str, list[str] | None]]:
    """(linha, tool, chaves-literais|None se args dinamicos) de todo call_tool()."""
    tree = ast.parse(MCP_CLIENT.read_text(encoding="utf-8"))
    sites: list[tuple[int, str, list[str] | None]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = fn.id if isinstance(fn, ast.Name) else getattr(fn, "attr", "")
        if name != "call_tool" or not node.args:
            continue
        first = node.args[0]
        if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
            continue
        tool = first.value
        keys: list[str] | None = None
        if len(node.args) > 1:
            second = node.args[1]
            if isinstance(second, ast.Dict) and all(
                isinstance(k, ast.Constant) for k in second.keys
            ):
                keys = [k.value for k in second.keys]  # type: ignore[union-attr]
            else:
                keys = None  # dict dinamico -- valida so o nome da tool
        else:
            keys = []
        sites.append((node.lineno, tool, keys))
    return sites


def check_code(snapshot: dict) -> None:
    print("=== (b) CODIGO x CONTRATO ===")
    tools = snapshot["tools"]
    quirks = snapshot.get("quirks", {})
    sites = extract_call_sites()
    if not sites:
        fail("nenhum call_tool() encontrado no mcp_client -- parser quebrado?")
        return
    bad = 0
    for lineno, tool, keys in sites:
        where = f"mcp_client.py:{lineno} {tool}"
        if tool not in tools:
            fail(f"{where}: tool INEXISTENTE no servidor")
            bad += 1
            continue
        if keys is None:
            continue  # args dinamicos -- nome validado, chaves fora de alcance estatico
        schema = tools[tool].get("inputSchema", {})
        props = set(schema.get("properties", {}).keys())
        required = set(schema.get("required", []))
        q = quirks.get(tool, {})
        required |= set(q.get("required_extra", []))
        unknown = [k for k in keys if props and k not in props]
        missing = [r for r in required if r not in keys]
        for u in unknown:
            fail(f"{where}: chave desconhecida '{u}' (schema: {sorted(props)})")
            bad += 1
        for m in missing:
            fail(f"{where}: required '{m}' ausente (schema+quirks)")
            bad += 1
    if not bad:
        ok(f"{len(sites)} call-sites validados contra o contrato (schema+quirks)")


def check_docs(snapshot: dict) -> None:
    print("\n=== (c) DOCS x CONTRATO ===")
    known = set(snapshot["tools"].keys())
    total_cited = 0
    for doc in DOC_FILES:
        if not doc.exists():
            fail(f"doc ausente: {doc.relative_to(ROOT)}")
            continue
        unknown_hits: list[str] = []
        for line in doc.read_text(encoding="utf-8", errors="replace").splitlines():
            low = line.lower()
            if any(m in low for m in NEGATION_MARKERS):
                continue
            for tok in re.findall(r"`([a-z][a-z_]{2,40})`", line):
                if tok.startswith(TOOL_PREFIXES) and tok not in known:
                    unknown_hits.append(tok)
        total_cited += 1
        if unknown_hits:
            for t in sorted(set(unknown_hits)):
                fail(f"{doc.name}: cita tool inexistente `{t}` (doc-drift)")
        else:
            ok(f"{doc.name}: todos os nomes de tool citados existem no contrato")


def check_live(snapshot: dict) -> None:
    print("\n=== (--live) SERVIDOR x SNAPSHOT ===")
    live = fetch_live_tools()
    snap_names = set(snapshot["tools"].keys())
    live_names = set(live.keys())
    for gone in sorted(snap_names - live_names):
        fail(f"tool sumiu do servidor: {gone}")
    for new in sorted(live_names - snap_names):
        fail(f"tool NOVA no servidor (snapshot desatualizado): {new}")
    for name in sorted(snap_names & live_names):
        if snapshot["tools"][name]["inputSchema"] != live[name]["inputSchema"]:
            fail(f"schema mudou no servidor: {name} -- rodar --refresh e revalidar quirks")
    if EXIT == 0:
        ok(f"servidor identico ao snapshot ({len(live_names)} tools)")


def refresh_snapshot(snapshot: dict | None) -> None:
    import datetime as dt
    live = fetch_live_tools()
    new = {
        "generated_at": dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "server": "https://mcp.ctrader.com/trading/mcp (ctrader-trading, MCP 2025-03-26)",
        "refresh": "python gates/run_mcp_contract.py --refresh",
        "tools": live,
        "quirks": (snapshot or {}).get("quirks", {}),
    }
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.write_text(json.dumps(new, indent=1, ensure_ascii=True), encoding="utf-8")
    print(f"  [OK] snapshot re-gerado: {len(live)} tools (quirks preservados)")


def main() -> int:
    args = set(sys.argv[1:])
    snap = load_snapshot() if SNAPSHOT.exists() else None
    if "--refresh" in args:
        refresh_snapshot(snap)
        return 0
    if snap is None:
        print(f"  [ERR] contrato ausente: {SNAPSHOT}")
        return 1
    check_code(snap)
    check_docs(snap)
    if "--live" in args:
        check_live(snap)
    print(f"\n{'=' * 50}")
    if EXIT == 0:
        print(f"[OK] G10 MCP-CONTRACT: PASS ({len(snap['tools'])} tools no contrato)")
        return 0
    print("[ERR] G10 MCP-CONTRACT: FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(main())
