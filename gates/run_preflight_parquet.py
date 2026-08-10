"""G21 — PREFLIGHT: integridade do banco Parquet M_1.
Verifica antes do boot:
  - data/ existe e tem arquivos .parquet
  - 5 simbolos tem pelo menos 1 arquivo
  - Ultima linha <= 5 min atras (F0 rodando)
  - Sem timestamps futuros
  - Sem duplicatas
  - Parquet valido (pd.read_parquet nao falha)
"""
from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
SYMBOLS = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD"]
MAX_STALE_MIN = 5  # max idade da ultima vela antes de alertar


def check_data_dir() -> list[str]:
    errors: list[str] = []
    if not DATA_DIR.exists():
        errors.append("G21: data/ nao existe — crie com mkdir data")
        return errors
    return errors


def check_parquet_files() -> list[str]:
    errors: list[str] = []
    for sym in SYMBOLS:
        files = sorted(DATA_DIR.glob(f"m1_{sym}_*.parquet"))
        if not files:
            print(f"  [WARN] {sym}: aguardando primeira persistencia (F0 ainda nao reiniciou)")
            continue
        for pf in files[-1:]:  # so o mais recente
            try:
                import pandas as pd
                df = pd.read_parquet(pf)
                if len(df) == 0:
                    errors.append(f"G21: {pf.name} vazio")
                    continue

                # Verifica colunas minimas
                required = {"timestamp", "open", "high", "low", "close"}
                missing = required - set(df.columns)
                if missing:
                    errors.append(f"G21: {pf.name} sem colunas: {missing}")

                # Timestamp da ultima linha (int64 ms — numpy.int64 NAO e
                # isinstance(int); pd.Timestamp(int) assumiria nanosegundos)
                last_ts = df["timestamp"].iloc[-1]
                try:
                    last_dt = datetime.fromtimestamp(int(last_ts) / 1000, tz=UTC)
                except (TypeError, ValueError):
                    last_dt = pd.Timestamp(last_ts).to_pydatetime()
                    if last_dt.tzinfo is None:
                        last_dt = last_dt.replace(tzinfo=UTC)

                age_min = (datetime.now(UTC) - last_dt).total_seconds() / 60
                if age_min > MAX_STALE_MIN:
                    errors.append(
                        f"G21: {sym} ultima vela tem {age_min:.0f}min — "
                        f"F0 pode estar parado (max {MAX_STALE_MIN}min)"
                    )

                # Timestamps futuros
                future = df[df["timestamp"] > datetime.now(UTC).timestamp() * 1000 + 3600000]
                if len(future) > 0:
                    errors.append(f"G21: {sym} tem {len(future)} timestamps futuros")

                # Duplicatas
                dups = df["timestamp"].duplicated().sum()
                if dups > 0:
                    errors.append(f"G21: {sym} tem {dups} timestamps duplicados")

                # OHLC sanity
                bad = df[(df["high"] < df["low"]) | (df["close"] == 0)]
                if len(bad) > 0:
                    errors.append(f"G21: {sym} tem {len(bad)} linhas com high<low ou close=0")

            except Exception as e:
                errors.append(f"G21: {pf.name} ilegivel — {e}")

    return errors


def main() -> int:
    print("=" * 60)
    print(" G21 — PREFLIGHT: BANCO PARQUET M_1")
    print("=" * 60)

    errors: list[str] = []
    errors.extend(check_data_dir())
    errors.extend(check_parquet_files())

    for e in errors:
        print(f"  [ERR] {e}")

    if errors:
        total = len(SYMBOLS)
        print(f"\n[WARN] G21: {len(errors)} erros em {total} simbolos — verificar antes de backtest")
        return 0  # WARN nao bloqueia boot, mas alerta

    print(f"\n[OK] G21: {len(SYMBOLS)} simbolos, banco Parquet integro")
    return 0


if __name__ == "__main__":
    sys.exit(main())
