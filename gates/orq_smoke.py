"""PROPOSITO: ORQ smoke test — importa todos os ORQs para validar wiring.
SPEC: BOOT
Usado pelo Abrir_NeoCortex_NovaPulse.ps1 (step ORQ smoke).
"""
import sys
from pathlib import Path

# path do ctrader passado como arg ou deduzido do script
ctrader = sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).resolve().parent)
sys.path.insert(0, ctrader)

from f3_validacao.orc_ranking import rank_signals
from utils.orc_pattern import extract_feature_vector
from utils.orc_mercado import normalize_markets
from utils.orc_indices import correlate_markets_m1
from f2_fusao.orc_score import combined_score
from utils.orc_vectorbt import compute_indicators

print("ORQs OK")
