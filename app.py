"""
app.py — Forex Backtesting Dashboard
Run with: streamlit run app.py
"""

import streamlit as st
import pandas as pd
from datetime import date, timedelta

from backtest import run_backtest
from strategy import STRATEGIES
from data import available_pairs
from metrics import (
    plot_equity_curve,
    plot_drawdown,
    plot_monthly_heatmap,
    plot_pnl_distribution,
    plot_price_with_trades,
    plot_win_loss_pie,
)

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Forex Backtester",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=Inter:wght@300;400;500&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
        background-color: #0d1117;
        color: #e6edf3;
    }
    .stApp { background-color: #0d1117; }

    /* Sidebar */
    section[data-testid="stSidebar"] {
        background-color: #161b22;
        border-right: 1px solid #21262d;
    }

    /* Metric cards */
    div[data-testid="metric-container"] {
        background-color: #161b22;
        border: 1px solid #21262d;
        border-radius: 8px;
        padding: 16px;
    }
    div[data-testid="metric-container"] label {
        color: #8892a4 !important;
        font-family: 'JetBrains Mono', monospace;
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 0.08em;
    }
    div[data-testid="metric-container"] div[data-testid="stMetricValue"] {
        font-family: 'JetBrains Mono', monospace;
        font-size: 24px;
        font-weight: 700;
        color: #e6edf3;
    }

    /* Headers */
    h1 { font-family: 'JetBrains Mono', monospace; font-size: 22px; letter-spacing: -0.02em; }
    h2, h3 { font-family: 'JetBrains Mono', monospace; }

    /* Buttons */
    .stButton > button {
        background-color: #00d4aa;
        color: #0d1117;
        font-family: 'JetBrains Mono', monospace;
        font-weight: 700;
        border: none;
        border-radius: 6px;
        padding: 10px 28px;
        width: 100%;
        font-size: 13px;
        letter-spacing: 0.05em;
        transition: background 0.2s;
    }
    .stButton > button:hover { background-color: #00b894; }

    /* Divider */
    hr { border-color: #21262d; }

    /* Dataframe */
    .stDataFrame { border: 1px solid #21262d; border-radius: 8px; }
</style>
""", unsafe_allow_html=True)


# ── Sidebar — Controls ────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## ⚙️ Backtest Config")
    st.markdown("---")

    pair = st.selectbox("Currency Pair", available_pairs(), index=0)

    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("Start", value=date.today() - timedelta(days=365 * 3))
    with col2:
        end_date = st.date_input("End", value=date.today())

    interval = st.selectbox("Timeframe", ["1d", "1h", "4h"], index=0)

    strategy_name = st.selectbox("Strategy", list(STRATEGIES.keys()))

    st.markdown("---")
    st.markdown("### Strategy Parameters")

    strategy_params = {}

    if strategy_name == "EMA Crossover":
        strategy_params["fast_period"] = st.slider("Fast EMA", 5, 50, 10)
        strategy_params["slow_period"] = st.slider("Slow EMA", 10, 200, 30)
        strategy_params["rsi_period"]  = st.slider("RSI Period", 7, 28, 14)

    elif strategy_name == "RSI Mean Reversion":
        strategy_params["rsi_period"] = st.slider("RSI Period", 7, 28, 14)
        strategy_params["oversold"]   = st.slider("Oversold Level", 10, 40, 30)
        strategy_params["overbought"] = st.slider("Overbought Level", 60, 90, 70)
        strategy_params["sma_period"] = st.slider("Trend SMA", 50, 300, 200)

    elif strategy_name == "MACD Crossover":
        strategy_params["macd_fast"]    = st.slider("MACD Fast", 5, 20, 12)
        strategy_params["macd_slow"]    = st.slider("MACD Slow", 15, 50, 26)
        strategy_params["macd_signal"]  = st.slider("Signal", 5, 20, 9)
        strategy_params["atr_stop_mult"]= st.slider("ATR Stop Multiplier", 0.0, 5.0, 2.0, step=0.5)

    st.markdown("---")
    initial_cash = st.number_input("Starting Capital ($)", value=10_000, step=1_000)
    commission   = st.number_input("Commission (per trade, %)", value=0.02, step=0.01, format="%.3f") / 100

    st.markdown("---")
    run_button = st.button("▶ Run Backtest")


# ── Main Layout ───────────────────────────────────────────────────────────────

st.markdown("# 📈 Forex Backtesting Dashboard")
st.markdown(f"**{pair}** · {strategy_name} · {start_date} → {end_date}")
st.markdown("---")

if not run_button:
    st.info("Configure your backtest in the sidebar and click **▶ Run Backtest** to begin.")
    st.stop()


# ── Run ───────────────────────────────────────────────────────────────────────

with st.spinner("Fetching data and running backtest..."):
    try:
        result = run_backtest(
            pair=pair,
            start=str(start_date),
            end=str(end_date),
            interval=interval,
            strategy_name=strategy_name,
            initial_cash=float(initial_cash),
            commission=commission,
            strategy_params=strategy_params,
        )
    except Exception as e:
        st.error(f"Backtest failed: {e}")
        st.stop()

equity     = result["equity_curve"]
trade_log  = result["trade_log"]
stats      = result["stats"]
ohlcv      = result["ohlcv"]


# ── KPI Cards ─────────────────────────────────────────────────────────────────

st.markdown("### Performance Summary")

c1, c2, c3, c4, c5, c6 = st.columns(6)

ret_delta = f"{stats['total_return']:+.2f}%"

c1.metric("Total Return",    f"{stats['total_return']:+.2f}%")
c2.metric("Final Value",     f"${stats['final_value']:,.2f}")
c3.metric("Sharpe Ratio",    f"{stats['sharpe_ratio']:.3f}")
c4.metric("Max Drawdown",    f"{stats['max_drawdown']:.2f}%")
c5.metric("Win Rate",        f"{stats['win_rate']:.1f}%")
c6.metric("Total Trades",    str(stats['total_trades']))

st.markdown("---")


# ── Charts Row 1 ──────────────────────────────────────────────────────────────

col_left, col_right = st.columns([3, 1])

with col_left:
    st.plotly_chart(
        plot_equity_curve(equity, stats["initial_cash"]),
        use_container_width=True,
    )

with col_right:
    st.plotly_chart(
        plot_win_loss_pie(stats["won"], stats["lost"]),
        use_container_width=True,
    )


# ── Charts Row 2 ──────────────────────────────────────────────────────────────

col_dd, col_pnl = st.columns(2)

with col_dd:
    st.plotly_chart(plot_drawdown(equity), use_container_width=True)

with col_pnl:
    st.plotly_chart(plot_pnl_distribution(trade_log), use_container_width=True)


# ── Monthly Heatmap ───────────────────────────────────────────────────────────

st.plotly_chart(plot_monthly_heatmap(equity), use_container_width=True)


# ── Price Chart ───────────────────────────────────────────────────────────────

# Limit candlestick to last 180 bars for performance
ohlcv_display = ohlcv.tail(180) if len(ohlcv) > 180 else ohlcv
trade_log_display = [
    t for t in trade_log
    if pd.Timestamp(t["entry_date"]) >= ohlcv_display.index[0]
] if trade_log else []

st.plotly_chart(
    plot_price_with_trades(ohlcv_display, trade_log_display),
    use_container_width=True,
)


# ── Trade Log Table ───────────────────────────────────────────────────────────

st.markdown("### Trade Log")

if trade_log:
    df_trades = pd.DataFrame(trade_log)
    df_trades["pnl"] = df_trades["pnl"].round(4)
    df_trades["entry_price"] = df_trades["entry_price"].round(5)
    df_trades["exit_price"]  = df_trades["exit_price"].round(5)

    def colour_pnl(val):
        colour = "#00d4aa" if val >= 0 else "#ff4d6d"
        return f"color: {colour}; font-weight: 600"

    styled = df_trades.style.applymap(colour_pnl, subset=["pnl"])
    st.dataframe(styled, use_container_width=True, height=300)

    # Download
    csv = df_trades.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇ Download Trade Log (CSV)",
        data=csv,
        file_name=f"{pair.replace('/', '')}_{strategy_name.replace(' ', '_')}_trades.csv",
        mime="text/csv",
    )
else:
    st.warning("No trades were generated for this configuration. Try adjusting the strategy parameters or date range.")


# ── Additional Stats ──────────────────────────────────────────────────────────

with st.expander("📊 Detailed Statistics"):
    d1, d2 = st.columns(2)
    with d1:
        st.markdown("**Trade Stats**")
        st.json({
            "Total Trades":   stats["total_trades"],
            "Won":            stats["won"],
            "Lost":           stats["lost"],
            "Win Rate":       f"{stats['win_rate']}%",
            "Profit Factor":  stats["profit_factor"],
            "Avg Win":        stats["avg_win"],
            "Avg Loss":       stats["avg_loss"],
        })
    with d2:
        st.markdown("**Risk Stats**")
        st.json({
            "Initial Capital": f"${stats['initial_cash']:,.2f}",
            "Final Value":     f"${stats['final_value']:,.2f}",
            "Total Return":    f"{stats['total_return']}%",
            "Max Drawdown":    f"{stats['max_drawdown']}%",
            "Sharpe Ratio":    stats["sharpe_ratio"],
        })
