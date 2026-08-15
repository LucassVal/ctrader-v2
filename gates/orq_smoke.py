"""PROPOSITO: ORQ smoke test — importa todos os ORQs para validar wiring.
SPEC: BOOT
Usado pelo Abrir_NeoCortex_NovaPulse.ps1 (step ORQ smoke).
"""
import sys
from pathlib import Path

# path do ctrader passado como arg ou deduzido do script
ctrader = sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).resolve().parent)
sys.path.insert(0, ctrader)


print("ORQs OK")
