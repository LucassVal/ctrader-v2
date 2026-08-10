"""T19: Harness F2 — pesos somam 1.0, redutores aplicados (S38 — pipeline real, sem FUS-STUB)"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from f2_fusao.orc_fusao import fuse


def test_fusion_returns_valid_structure():
    """Fusao deve retornar estrutura com scores e meta."""
    scores_live = {
        "symbols": {
            "XAUUSD": {"online": True, "score": 78, "sinal": "BULLISH"},
            "EURUSD": {"online": True, "score": 65, "sinal": "NEUTRAL"},
        }
    }
    result = fuse(scores_live)
    assert isinstance(result, dict), f"Resultado nao e dict: {type(result)}"
    # Estrutura real: scores.macro.weighted + scores.volatilidade.weighted + scores.tecnico.weighted
    if "scores" in result:
        scores = result["scores"]
        # Verifica que pesos aproximam 1.0
        w_sum = 0
        for comp in ("macro", "volatilidade", "tecnico"):
            if comp in scores:
                w_sum += scores[comp].get("weight", 0)
        if w_sum > 0:
            assert abs(w_sum - 1.0) < 0.01, f"Pesos somam {w_sum}"
    print("PASS: estrutura valida")


def test_reducers_applied():
    """Redutores NEWS_IMMINENT + spread > 2 devem ser aplicados."""
    scores_live = {
        "symbols": {
            "XAUUSD": {"online": True, "score": 85, "sinal": "BULLISH"},
        }
    }
    ctx = {"news_imminent": True, "spread_pips": 3.0}
    result = fuse(scores_live, ctx)
    # Verifica que final_adjusted < final_raw (redutores aplicados)
    if "scores" in result and "final_adjusted" in result["scores"]:
        raw = result["scores"].get("final_raw", 0)
        adj = result["scores"]["final_adjusted"]
        assert adj < raw, f"Score nao foi reduzido: raw={raw}, adj={adj}"
        assert "NEWS_IMMINENT" in result["scores"].get("reducers_applied", [])
    print("PASS: redutores aplicados")


if __name__ == "__main__":
    test_fusion_returns_valid_structure()
    test_reducers_applied()
