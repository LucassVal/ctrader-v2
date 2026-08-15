"""Scratch: analisa padroes de gaps para diagnosticar o 'eterno 46 gaps'."""
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

REPORT = Path(r"c:\Workspace\Neocortex v44\neocortex\11.0_apps\ctrader\status\gap_report.json")
report = json.loads(REPORT.read_text(encoding="utf-8"))

print("=" * 70)
print("GAP REPORT ANALYSIS — Diagnostico de gaps persistentes")
print("=" * 70)
print(f"Generated: {report['generated_at']}")
print(f"Window: {report['window_days']}d | Gap min: {report['gap_min_minutes']}min")
print()

for sym, info in report["symbols"].items():
    gaps = info.get("gaps", [])
    total = info.get("total_gaps", len(gaps))
    cov = info.get("coverage_pct", 0)

    # Analisa tamanhos dos gaps
    sizes = []
    for g in gaps:
        if "missing_minutes" in g:
            sizes.append(g["missing_minutes"])
        else:
            dur_ms = g["end_ms"] - g["start_ms"]
            sizes.append(dur_ms // 60000)

    tiny = [s for s in sizes if s <= 15]
    small = [s for s in sizes if 15 < s <= 60]
    medium = [s for s in sizes if 60 < s <= 1440]
    large = [s for s in sizes if s > 1440]

    print(f"\n{'='*50}")
    print(f"{sym}: {total} gaps (total_gaps field), {len(gaps)} in gaps list")
    print(f"  Coverage: {cov}% | Rows: {info.get('rows', 0)}")
    print(f"  Tiny (<=15m): {len(tiny)}")
    print(f"  Small (15-60m): {len(small)}")
    print(f"  Medium (1-24h): {len(medium)}")
    print(f"  Large (>24h): {len(large)}")

    # Analisa horario dos gaps pequenos (provavel calendario)
    daily_pattern = Counter()
    weekday_pattern = Counter()
    for g in gaps:
        dt_start = datetime.fromtimestamp(g["start_ms"] / 1000, tz=UTC)
        dt_end = datetime.fromtimestamp(g["end_ms"] / 1000, tz=UTC)
        dur_min = (g["end_ms"] - g["start_ms"]) // 60000
        if dur_min <= 15:
            daily_pattern[f"{dt_start.hour:02d}:{dt_start.minute:02d}"] += 1
            weekday_pattern[dt_start.weekday()] += 1

    if daily_pattern:
        print("  --- Padrao de gaps <=15min ---")
        for time_str, count in daily_pattern.most_common(5):
            print(f"    {time_str} UTC: {count}x")
        print(f"  Weekdays: {dict(weekday_pattern)}")
        print("  (0=Mon..6=Sun)")

    # Verifica se gaps estao no FUTURO
    now_ms = int(datetime.now(UTC).timestamp() * 1000)
    future = [g for g in gaps if g["start_ms"] > now_ms]
    if future:
        print(f"  *** {len(future)} gaps in FUTURE dates! ***")

    # Amostra de gaps recentes
    if gaps:
        print("  --- Sample recent gaps ---")
        for g in gaps[-3:]:
            dt_s = datetime.fromtimestamp(g["start_ms"] / 1000, tz=UTC)
            dt_e = datetime.fromtimestamp(g["end_ms"] / 1000, tz=UTC)
            dur = (g["end_ms"] - g["start_ms"]) // 60000
            print(f"    {dt_s.strftime('%Y-%m-%d %H:%M')} -> {dt_e.strftime('%Y-%m-%d %H:%M')} ({dur}min) wd={dt_s.weekday()}")

# Diagnostico especifico do XAUUSD (o que o usuario viu com 46 ranges)
print("\n\n" + "=" * 70)
print("DIAGNOSTICO XAUUSD — O caso dos 46 ranges eternos")
print("=" * 70)
xau = report["symbols"].get("XAUUSD", {})
xau_gaps = xau.get("gaps", [])
print(f"total_gaps field: {xau.get('total_gaps', 'N/A')}")
print(f"gaps in list: {len(xau_gaps)}")
print(f"DISCREPANCY: total_gaps ({xau.get('total_gaps', 0)}) != len(gaps) ({len(xau_gaps)})")
print("  -> gap_report foi parcialmente atualizado pelo backfill?")
print("  -> campo total_gaps nao foi recalculado apos update incremental?")
print()

# Simula merge de gaps com threshold 26h
merge_threshold_ms = 26 * 3600 * 1000
sorted_gaps = sorted(xau_gaps, key=lambda g: g["start_ms"])
merged = []
for g in sorted_gaps:
    gs, ge = g["start_ms"], g["end_ms"]
    if merged and gs - merged[-1][1] <= merge_threshold_ms:
        merged[-1] = (merged[-1][0], max(merged[-1][1], ge))
    else:
        merged.append((gs, ge))

print("Merge simulation (threshold=26h):")
print(f"  {len(xau_gaps)} gaps -> {len(merged)} ranges (backfill veria {len(merged)} ranges)")
print()

# Verifica quais ranges sao do PASSADO do backfill (ja deveriam estar preenchidos)
for i, (ms_s, ms_e) in enumerate(merged):
    dt_s = datetime.fromtimestamp(ms_s / 1000, tz=UTC)
    dt_e = datetime.fromtimestamp(ms_e / 1000, tz=UTC)
    dur_h = (ms_e - ms_s) / 3600000
    print(f"  Range {i+1}: {dt_s.strftime('%Y-%m-%d')} -> {dt_e.strftime('%Y-%m-%d')} ({dur_h:.1f}h)")
