"""TEST CONFORMANCE GATES G11-G14 — fixtures sintéticas (tmp_path)
R-HARNESS: cada check prova que flagra o que promete.
NAO usa arquivos reais do app — tudo gera em tmp_path.
"""
from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path

GATE_RUNNER = Path(__file__).resolve().parent.parent / "gates" / "run_conformance.py"
# tests/ -> ctrader/ -> apps/ -> neocortex/ -> .venv/
VENV_PY = Path(__file__).resolve().parent.parent.parent.parent / ".venv" / "Scripts" / "python.exe"


def _run_gate(check: str, cwd: str) -> subprocess.CompletedProcess:
    """Roda o gate como subprocess (exit code real)."""
    return subprocess.run(
        [str(VENV_PY), str(GATE_RUNNER), "--check", check, "--dir", cwd],
        capture_output=True, text=True, timeout=30,
    )


def _make_py(path: Path, content: str, name: str = "mod.py") -> Path:
    """Cria .py em tmp_path."""
    p = path / name
    p.write_text(content, encoding="utf-8")
    return p


def _make_spec(path: Path, name: str, content: str) -> Path:
    """Cria spec .md em tmp_path/specs/."""
    specs_dir = path / "specs"
    specs_dir.mkdir(exist_ok=True)
    p = specs_dir / name
    p.write_text(content, encoding="utf-8")
    return p


# ══════════════════════════════════════════════════════════════
# G11 — HEADER-SPEC
# ══════════════════════════════════════════════════════════════

def test_g11_missing_proposito(tmp_path: Path) -> None:
    """G11: .py >50L sem PROPOSITO: no docstring -> ERR."""
    _make_py(tmp_path, textwrap.dedent("""\
        \"\"\"So tem docstring sem marcadores.\"\"\"
        x = 1
        y = 2
        z = 3
    """) + "\n" + "a = 1\n" * 50)
    r = _run_gate("header", str(tmp_path))
    assert r.returncode != 0
    assert "sem PROPOSITO" in r.stdout


def test_g11_missing_spec(tmp_path: Path) -> None:
    """G11: .py >50L com PROPOSITO: mas sem SPEC: -> ERR."""
    _make_py(tmp_path, textwrap.dedent("""\
        \"\"\"PROPOSITO: modulo de teste.
        ROADMAP: 0.7
        \"\"\"
        pass
    """) + "\n" + "# padding\n" * 50)
    r = _run_gate("header", str(tmp_path))
    assert r.returncode != 0
    assert "sem SPEC:" in r.stdout


def test_g11_spec_not_in_index(tmp_path: Path) -> None:
    """G11: SPEC: S# inexistente no INDEX -> ERR."""
    _make_py(tmp_path, textwrap.dedent("""\
        \"\"\"PROPOSITO: modulo de teste.
        SPEC: S999
        ROADMAP: 0.7
        \"\"\"
        pass
    """) + "\n" + "# padding\n" * 50)
    # Cria INDEX falso sem S999
    _make_spec(tmp_path, "INDEX.md", "# INDEX\nSPEC S0: exists\n")
    r = _run_gate("header", str(tmp_path))
    assert r.returncode != 0
    assert "nao encontrada" in r.stdout


def test_g11_header_valid(tmp_path: Path) -> None:
    """G11: header completo com SPEC valida -> OK."""
    _make_spec(tmp_path, "INDEX.md", "# INDEX\nSPEC S0: exists\n")
    _make_spec(tmp_path, "ROADMAP.md", "ROADMAP 0.7: test item\n")
    _make_py(tmp_path, textwrap.dedent("""\
        \"\"\"PROPOSITO: modulo de teste.
        SPEC: S0
        ROADMAP: 0.7
        \"\"\"
        pass
    """) + "\n" + "# padding\n" * 50)
    r = _run_gate("header", str(tmp_path))
    # Python OK, specs falham nos fakes — esperado
    assert "Python: 1/1 OK" in r.stdout


def test_g11_spec_missing_markers(tmp_path: Path) -> None:
    """G11: spec .md sem SPEC S# no titulo -> ERR."""
    _make_spec(tmp_path, "test.md", "# Teste sem marcador\nVersao 1.0\n")
    r = _run_gate("header", str(tmp_path))
    assert r.returncode != 0
    assert "sem SPEC S#" in r.stdout or "sem VERSION" in r.stdout


# ══════════════════════════════════════════════════════════════
# G12 — DDD
# ══════════════════════════════════════════════════════════════

def test_g12_satellite_201_lines(tmp_path: Path) -> None:
    """G12: satelite >200L -> GOD ERR."""
    lines = ["x = 1"] * 201
    _make_py(tmp_path, "\n".join(lines))
    r = _run_gate("ddd", str(tmp_path))
    assert r.returncode != 0
    assert "GOD object" in r.stdout


def test_g12_satellite_199_lines(tmp_path: Path) -> None:
    """G12: satelite <=200L -> OK."""
    _make_py(tmp_path, "x = 1\n" * 199)
    r = _run_gate("ddd", str(tmp_path))
    assert "GOD object" not in r.stdout


def test_g12_orq_351_lines(tmp_path: Path) -> None:
    """G12: _orc_ >350L -> GOD ERR."""
    _make_py(tmp_path, "x = 1\n" * 351, name="_orc_test.py")
    r = _run_gate("ddd", str(tmp_path))
    assert r.returncode != 0
    assert "GOD object" in r.stdout


def test_g12_no_docstring_gt_150(tmp_path: Path) -> None:
    """G12: >150L sem docstring -> ERR."""
    _make_py(tmp_path, "x = 1\n" * 151)
    r = _run_gate("ddd", str(tmp_path))
    assert r.returncode != 0
    assert "sem docstring" in r.stdout


# ══════════════════════════════════════════════════════════════
# G13 — SEGURANCA
# ══════════════════════════════════════════════════════════════

def test_g13_sk_key_detected(tmp_path: Path) -> None:
    """G13: sk-XXXX no codigo -> ERR."""
    _make_py(tmp_path, 'API_KEY = "sk-1234567890abcdef1234567890abcdef"')
    r = _run_gate("security", str(tmp_path))
    assert r.returncode != 0
    assert "possivel" in r.stdout.lower()


def test_g13_bearer_token_detected(tmp_path: Path) -> None:
    """G13: Bearer token longo -> ERR."""
    _make_py(tmp_path, 'HEADERS = {"Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"}')
    r = _run_gate("security", str(tmp_path))
    assert r.returncode != 0
    assert "possivel" in r.stdout.lower()


def test_g13_mutant_tool_outside_f4(tmp_path: Path) -> None:
    """G13: create_order fora de f4_executor/ -> ERR."""
    p = tmp_path / "random_tool"
    p.mkdir()
    (p / "danger.py").write_text("create_order(symbol='EURUSD')", encoding="utf-8")
    r = _run_gate("security", str(tmp_path))
    assert r.returncode != 0
    assert "fora de f4_executor" in r.stdout


def test_g13_mutant_tool_inside_f4(tmp_path: Path) -> None:
    """G13: create_order dentro de f4_executor/ -> OK."""
    p = tmp_path / "f4_executor"
    p.mkdir()
    (p / "entry.py").write_text("create_order(symbol='EURUSD')", encoding="utf-8")
    r = _run_gate("security", str(tmp_path))
    assert "usa create_order() fora de" not in r.stdout


# ══════════════════════════════════════════════════════════════
# G14 — ROBUSTEZ-FORMA
# ══════════════════════════════════════════════════════════════

def test_g14_bare_except(tmp_path: Path) -> None:
    """G14: except: bare -> ERR."""
    _make_py(tmp_path, "try:\n    pass\nexcept:\n    pass\n")
    r = _run_gate("robustez", str(tmp_path))
    assert r.returncode != 0
    assert "bare except" in r.stdout


def test_g14_silent_fail(tmp_path: Path) -> None:
    """G14: return False em funcao >10L sem [ERRO] -> ERR."""
    _make_py(tmp_path, textwrap.dedent("""\
        def long_func():
            a = 1
            b = 2
            c = 3
            d = 4
            e = 5
            f = 6
            g = 7
            h = 8
            i = 9
            j = 10
            return False
    """))
    r = _run_gate("robustez", str(tmp_path))
    assert r.returncode != 0
    assert "sem [ERRO]" in r.stdout or "return False" in r.stdout


def test_g14_silent_fail_short_func(tmp_path: Path) -> None:
    """G14: return False em funcao <=10L -> OK (nao checado)."""
    _make_py(tmp_path, textwrap.dedent("""\
        def short_func():
            x = 1
            return False
    """))
    r = _run_gate("robustez", str(tmp_path))
    # Funcao <=10L nao e verificada — pode passar
    assert "return False" not in r.stdout or r.returncode == 0


def test_g14_accent_in_identifier(tmp_path: Path) -> None:
    """G14: acento em identificador -> ERR."""
    _make_py(tmp_path, "# coding: utf-8\nação = 1\n")
    r = _run_gate("robustez", str(tmp_path))
    assert r.returncode != 0
    assert "acento" in r.stdout


def test_g14_hardcoded_path(tmp_path: Path) -> None:
    """G14: C:\\ hardcoded fora de bootstrap -> ERR."""
    _make_py(tmp_path, 'PATH = "C:\\\\data\\\\file.txt"\n')
    r = _run_gate("robustez", str(tmp_path))
    assert r.returncode != 0
    assert "path absoluto" in r.stdout


def test_g14_v43_term(tmp_path: Path) -> None:
    """G14: termo V43 'Eixo 5' -> ERR."""
    _make_py(tmp_path, 'legacy_ref = "Eixo 5"\n')
    r = _run_gate("robustez", str(tmp_path))
    assert r.returncode != 0
    assert "termo V43" in r.stdout


def test_g14_emoji_in_print(tmp_path: Path) -> None:
    """G14: print() com emoji nao-ASCII -> ERR (R-ASCII-OUT)."""
    _make_py(tmp_path, 'print("\\u2705 ok")\n')
    r = _run_gate("robustez", str(tmp_path))
    assert r.returncode != 0
    assert "caractere nao-ASCII em print" in r.stdout


def test_g14_ascii_print_ok(tmp_path: Path) -> None:
    """G14: print() com [OK] ASCII -> OK."""
    _make_py(tmp_path, 'print("[OK] ok")\n')
    r = _run_gate("robustez", str(tmp_path))
    # Deve passar (não flagrar ASCII)
    assert "caractere nao-ASCII em print" not in r.stdout


def test_g14_emoji_in_logger(tmp_path: Path) -> None:
    """G14: logger.error() com emoji nao-ASCII -> ERR."""
    _make_py(tmp_path, 'import logging; logger = logging.getLogger(__name__); logger.error("\\u274c fail")\n')
    r = _run_gate("robustez", str(tmp_path))
    assert r.returncode != 0
    assert "caractere nao-ASCII em logger" in r.stdout
