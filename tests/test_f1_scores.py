"""T17: Harness F1 -- scores in [0,100]"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np
import pandas as pd

from f1_analyzer import calculate_macro_score, calculate_tec_score, calculate_vol_score


def test_scores_in_range():
    df = pd.DataFrame({
        "close": np.random.randn(50).cumsum() + 100,
        "high": np.random.randn(50).cumsum() + 101,
        "low": np.random.randn(50).cumsum() + 99,
        "tick_volume": np.random.randint(10, 200, 50),
        "spread": np.random.uniform(0.5, 2.0, 50),
        "dxy_close": np.random.randn(50).cumsum() + 100,
        "sentiment_ratio": np.random.uniform(0.3, 0.8, 50),
    })
    for fn in [calculate_macro_score, calculate_vol_score, calculate_tec_score]:
        s = fn(df)
        assert 0 <= s <= 100, f"Score {s} fora do range"
    print("PASS: Todos scores in [0,100]")

test_scores_in_range()
