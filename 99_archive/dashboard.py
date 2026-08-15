"""
PROPOSITO: T24 -- DASHBOARD COMPLETO
SPEC: S20
ROADMAP: D.8
"""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import streamlit as st

# --- PATH SETUP ---
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from utils.metrics import collect_all as collect_metrics, validate_metrics

from utils.health import check_decay, collect_metrics as collect_health

DB_PATH = ROOT / "trades.db"
RULES_PATH = ROOT / "custom_rules.json"

st.set_page_config(page_title="cTrader V2 -- Dashboard", layout="wide")
st.title("🔧 cTrader V2 -- Sistema de Trading Autônomo")

# --- CARREGAR DADOS ---
@st.cache_data(ttl=5)
def load_trades():
    try:
        conn = sqlite3.connect(str(DB_PATH))
        df = pd.read_sql("SELECT * FROM trades ORDER BY timestamp_utc DESC", conn)
        conn.close()
        return df
    except Exception:
        return pd.DataFrame()

df = load_trades()

# --- ABAS ---
tabs = st.tabs([
    " Overview", " Trades", "📈 Scores", "⚖️ MAR",
    "📐 Métricas", "❤️ Health", "📈 Indicadores", "🪵 Logs",
])

# ============================================================
# TAB 1: OVERVIEW
# ============================================================
with tabs[0]:
    col1, col2, col3, col4 = st.columns(4)

    if not df.empty:
        total = len(df)
        pnl_total = df["pnl_net"].sum() if "pnl_net" in df.columns else 0
        approved = df[df["decision"] == "APPROVE"] if "decision" in df.columns else pd.DataFrame()
        win_rate = (approved["pnl_net"] > 0).sum() / max(len(approved), 1) * 100 if not approved.empty else 0

        col1.metric("Total Trades", total)
        col2.metric("PnL Total", f"${pnl_total:.2f}")
        col3.metric("Win Rate", f"{win_rate:.1f}%")
        col4.metric("Avg PnL", f"${df['pnl_net'].mean():.2f}" if "pnl_net" in df.columns else "--")

        if "pnl_net" in df.columns and "timestamp_utc" in df.columns:
            equity = df.sort_values("timestamp_utc")
            equity["cumulative"] = equity["pnl_net"].cumsum()
            st.subheader("Curva de Equity")
            st.line_chart(equity.set_index("timestamp_utc")["cumulative"], use_container_width=True)

        col_a, col_b = st.columns(2)
        with col_a:
            if "decision" in df.columns:
                st.subheader("Decisões")
                st.bar_chart(df["decision"].value_counts())
        with col_b:
            if "symbol" in df.columns:
                st.subheader("Por Ativo")
                st.bar_chart(df["symbol"].value_counts())
    else:
        st.info("🕐 Aguardando trades... Inicie o sistema com: `python run.py`")

# ============================================================
# TAB 2: TRADES
# ============================================================
with tabs[1]:
    if not df.empty:
        cols = ["timestamp_utc", "symbol", "timeframe", "decision", "pnl_net", "exit_reason"]
        available = [c for c in cols if c in df.columns]
        symbol_filter = st.selectbox("Filtrar ativo", ["Todos", *sorted(df["symbol"].unique().tolist())] if "symbol" in df.columns else ["Todos"])
        filtered = df if symbol_filter == "Todos" else df[df["symbol"] == symbol_filter]
        st.dataframe(filtered[available], use_container_width=True, height=400)
        st.caption(f"{len(filtered)} trades | PnL total: ${filtered['pnl_net'].sum():.2f}" if "pnl_net" in filtered.columns else "")
    else:
        st.info("Sem trades registrados.")

# ============================================================
# TAB 3: SCORES
# ============================================================
with tabs[2]:
    st.subheader("Distribuição de Scores (F1-F2)")
    if not df.empty and "scores_json" in df.columns:
        scores_data = []
        for _, row in df.iterrows():
            try:
                s = json.loads(row["scores_json"])
                if "scores" in s:
                    scores_data.append(s["scores"])
            except (json.JSONDecodeError, KeyError):
                pass
        if scores_data:
            scores_df = pd.DataFrame(scores_data)
            if "final_adjusted" in scores_df.columns:
                st.line_chart(scores_df["final_adjusted"], use_container_width=True)
            if all(c in scores_df.columns for c in ["macro", "volatilidade", "tecnico"]):
                st.bar_chart(scores_df[["macro", "volatilidade", "tecnico"]].mean(), use_container_width=True)
    else:
        st.info("Dados de scores disponíveis após integração F1-F2.")

# ============================================================
# TAB 4: MAR
# ============================================================
with tabs[3]:
    st.subheader("Motor de Ajuste de Ranking (F5)")
    if RULES_PATH.exists():
        with open(RULES_PATH) as f:
            rules = json.load(f)
        col1, col2, col3 = st.columns(3)
        col1.metric("Versão", rules.get("version", "--"))
        col2.metric("Threshold", rules.get("threshold", 70))
        col3.metric("Total Trades", rules.get("total_trades", 0))

        weights = rules.get("weights", {})
        if weights:
            st.subheader("Pesos")
            st.bar_chart(pd.Series(weights))

        stats = rules.get("stats", {})
        if stats:
            st.subheader("Estatísticas")
            st.json(stats)

        st.caption(f"Última calibração: {rules.get('last_updated_utc', 'N/A')}")
    else:
        st.info("custom_rules.json será gerado após 5+ trades no dia.")

# ============================================================
# TAB 5: MÉTRICAS (25+ métricas blueprint §9.2)
# ============================================================
with tabs[4]:
    st.subheader("Métricas de Produção (30 dias demo)")

    try:
        metrics = collect_metrics()
    except Exception:
        metrics = {}

    if metrics:
        for phase, data in metrics.items():
            if data:
                st.caption(f"**{phase}**")
                cols = st.columns(len(data))
                for i, (key, val) in enumerate(data.items()):
                    with cols[i]:
                        if isinstance(val, float):
                            st.metric(key, f"{val:.2f}")
                        else:
                            st.metric(key, val)

    # validação contra thresholds
    alerts = validate_metrics(metrics) if metrics else []
    if alerts:
        st.error("[WARN] Alertas de métricas:")
        for a in alerts:
            st.warning(a)
    else:
        st.success("[OK] Todas as métricas dentro dos thresholds.")

# ============================================================
# TAB 6: HEALTH
# ============================================================
with tabs[5]:
    st.subheader("Health Check + Decay Detection")

    try:
        health = collect_health()
    except Exception:
        health = {}

    # status das fases
    phases = health.get("phases", {})
    if phases:
        cols = st.columns(len(phases))
        for i, (phase, data) in enumerate(phases.items()):
            with cols[i]:
                alive = data.get("alive", False)
                age = data.get("heartbeat_age_s", "?")
                if alive:
                    st.success(f"**{phase}** [OK] {age}s")
                elif age is None:
                    st.error(f"**{phase}** [ERR] offline")
                else:
                    st.warning(f"**{phase}** [WARN] {age}s")

    # decay detection
    decay = check_decay()
    if decay:
        st.error("[WARN] Decay detectado:")
        for d in decay:
            st.warning(d)

    # GOD files
    god = health.get("god_files", [])
    if god:
        st.warning(f" {len(god)} arquivos acima de 200L (GOD risk):")
        for g in god:
            st.caption(f"  {g}")

    ruff_errors = health.get("ruff_errors", 0)
    if ruff_errors > 0:
        st.error(f" RUFF: {ruff_errors} erros")
    elif ruff_errors == 0:
        st.success(" RUFF: 0 erros")

# ============================================================
# TAB 7: INDICADORES (Bollinger + Ichimoku por mercado)
# ============================================================
with tabs[6]:
    st.subheader("📈 Indicadores Técnicos em Tempo Real")

    SYMBOLS = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD"]
    TIMEFRAMES = ["M_5", "M_15"]  # M_10 nao existe no servidor
    selected_symbol = st.selectbox("Ativo", SYMBOLS)
    selected_tf = st.selectbox("Timeframe", TIMEFRAMES)

    @st.cache_data(ttl=5)
    def fetch_indicators(symbol: str, timeframe: str) -> dict:
        """Busca dados MCP e calcula Bollinger + Ichimoku."""
        try:
            from utils.mcp_client import get_spot_prices, get_trendbars, init_client
            init_client("config.yaml")

            # candles para Bollinger (20) + Ichimoku (52)
            bars = get_trendbars(symbol=symbol, timeframe=timeframe, count=60)
            if not bars or not isinstance(bars, list):
                return {"error": "Sem dados MCP"}

            closes = [float(b.get("close", 0)) for b in bars if b.get("close")]
            highs = [float(b.get("high", 0)) for b in bars if b.get("high")]
            lows = [float(b.get("low", 0)) for b in bars if b.get("low")]

            if len(closes) < 20:
                return {"error": f"Dados insuficientes ({len(closes)} candles)"}

            # Bollinger Bands
            import statistics
            sma20 = statistics.mean(closes[-20:])
            std20 = statistics.stdev(closes[-20:]) if len(closes[-20:]) > 1 else 0
            upper_bb = sma20 + 2 * std20
            lower_bb = sma20 - 2 * std20
            current = closes[-1]
            boll_pct_b = (current - lower_bb) / (upper_bb - lower_bb) if upper_bb != lower_bb else 0.5

            # Ichimoku
            tenkan = (max(highs[-9:]) + min(lows[-9:])) / 2 if len(highs) >= 9 else 0
            kijun = (max(highs[-26:]) + min(lows[-26:])) / 2 if len(highs) >= 26 else 0
            senkou_a = (tenkan + kijun) / 2
            senkou_b = (max(highs[-52:]) + min(lows[-52:])) / 2 if len(highs) >= 52 else 0

            # spot price
            spot = get_spot_prices(symbol)
            spread = 0.0
            if spot and isinstance(spot, dict):
                spread = float(spot.get("spread", 0))

            return {
                "current": round(current, 5),
                "spread": round(spread, 5),
                "bollinger": {
                    "sma20": round(sma20, 5),
                    "upper": round(upper_bb, 5),
                    "lower": round(lower_bb, 5),
                    "pct_b": round(boll_pct_b, 3),
                    "signal": "SOBRECOMPRADO" if boll_pct_b > 0.8 else ("SOBREVENDIDO" if boll_pct_b < 0.2 else "NEUTRO"),
                },
                "ichimoku": {
                    "tenkan": round(tenkan, 5),
                    "kijun": round(kijun, 5),
                    "senkou_a": round(senkou_a, 5),
                    "senkou_b": round(senkou_b, 5),
                    "tk_cross": "BULLISH" if tenkan > kijun else ("BEARISH" if tenkan < kijun else "FLAT"),
                    "cloud": "ACIMA" if current > max(senkou_a, senkou_b) else ("ABAIXO" if current < min(senkou_a, senkou_b) else "DENTRO"),
                },
            }
        except Exception as e:
            return {"error": str(e)}

    indicators = fetch_indicators(selected_symbol, selected_tf)

    if "error" in indicators:
        st.warning(f"[WARN] {indicators['error']}")
        st.info("O MCP precisa estar rodando (cTrader Web aberto) para dados em tempo real.")
    else:
        # --- Bollinger ---
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Preço Atual", indicators["current"])
            st.metric("Spread", indicators["spread"])
        with col2:
            bb = indicators["bollinger"]
            st.metric("Bollinger %B", bb["pct_b"], delta=bb["signal"])
            st.caption(f"SMA20: {bb['sma20']} | Upper: {bb['upper']} | Lower: {bb['lower']}")

        # --- Ichimoku ---
        st.divider()
        st.subheader("☁️ Ichimoku Kinko Hyo")
        ichi = indicators["ichimoku"]
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Tenkan-sen", ichi["tenkan"])
        c2.metric("Kijun-sen", ichi["kijun"])
        c3.metric("Senkou A", ichi["senkou_a"])
        c4.metric("Senkou B", ichi["senkou_b"])
        c5.metric("TK Cross", ichi["tk_cross"])

        # sinais combinados
        st.divider()
        st.subheader(" Sinais Combinados")
        sig_col1, sig_col2 = st.columns(2)
        with sig_col1:
            if bb["pct_b"] < 0.2 and ichi["tk_cross"] == "BULLISH":
                st.success(" SINAL DE COMPRA (Bollinger sobrevendido + TK bullish)")
            elif bb["pct_b"] > 0.8 and ichi["tk_cross"] == "BEARISH":
                st.error(" SINAL DE VENDA (Bollinger sobrecomprado + TK bearish)")
            else:
                st.info("⚪ Sem sinal claro")

        with sig_col2:
            st.metric("Nuvem", ichi["cloud"])
            if ichi["cloud"] == "ACIMA":
                st.caption("Preço acima da nuvem -> tendência de alta")
            elif ichi["cloud"] == "ABAIXO":
                st.caption("Preço abaixo da nuvem -> tendência de baixa")
            else:
                st.caption("Preço dentro da nuvem -> consolidação")

    st.caption(f"🔄 Atualização a cada 5s | Fonte: cTrader MCP get_trendbars({selected_symbol}, {selected_tf})")

# ============================================================
# TAB 8: LOGS
# ============================================================
with tabs[7]:
    st.subheader("Logs do Sistema")
    log_file = ROOT / "logs" / "system.log"
    if log_file.exists():
        with open(log_file) as f:
            lines = f.readlines()[-50:]  # ultimas 50 linhas
        st.code("".join(lines), language="log")
    else:
        st.info("Arquivo de log não encontrado. Inicie o sistema com `python run.py`")

st.divider()
st.caption(f"🕐 Atualizado: {datetime.now(UTC).isoformat()} UTC | Refresh: 5s | Port: 8501")
