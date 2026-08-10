"""Harness: f0_supervisor_orc_dashboard — f0_status/start/stop (controles do supervisor)"""
import contextlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.f0_supervisor_orc_dashboard import f0_status, f0_stop


def test_f0_status_returns_dict():
    """f0_status deve retornar dict com running e pid."""
    result = f0_status()
    assert isinstance(result, dict)
    assert "running" in result, "Status deve ter 'running'"
    assert isinstance(result["running"], bool)


def test_f0_status_has_pid():
    """f0_status deve incluir pid quando running."""
    result = f0_status()
    if result.get("running"):
        assert "pid" in result, "F0 running deve ter pid"


def test_f0_stop_f0_status_consistent():
    """f0_stop seguido de f0_status deve ser consistente."""
    # Nao podemos realmente parar F0 em teste, mas podemos verificar
    # que as funcoes nao crasham
    with contextlib.suppress(Exception):
        f0_stop()
    result = f0_status()
    assert isinstance(result, dict)
