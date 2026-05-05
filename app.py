"""
Trading Dashboard — Streamlit
==============================
Real-time monitoring of the Asian Session Breakout bot.
Run with: streamlit run dashboard/app.py
"""

import os
import sys
import requests
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv()

API_KEY    = os.getenv("OANDA_API_KEY")
ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID")
ENVIRONMENT = os.getenv("OANDA_ENVIRONMENT", "practice")

BASE_URL = (
    "https://api-fxtrade.oanda.com"
    if ENVIRONMENT == "live"
    else "https://api-fxpractice.oanda.com"
)

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}

st.set_page_config(
    page_title="GBP/USD Breakout Bot",
    page_icon="📈",
    layout="wide",
)

# ── API Helpers ────────────────────────────────────────────────────────────

@st.cache_data(ttl=30)
def get_account_summary():
    url = f"{BASE_URL}/v3/accounts/{ACCOUNT_ID}/summary"
    r = requests.get(url, headers=HEADERS)
    return r.json().get("account", {})


@st.cache_data(ttl=30)
def get_open_trades():
    url = f"{BASE_URL}/v3/accounts/{ACCOUNT_ID}/openTrades"
    r = requests.get(url, headers=HEADERS)
    return r.json().get("trades", [])


@st.cache_data(ttl=60)
def get_closed_trades(count: int = 100):
    url = f"{BASE_URL}/v3/accounts/{ACCOUNT_ID}/transactions"
    params = {"type": "ORDER_FILL", "count": count}
    r = requests.get(url, headers=HEADERS, params=params)
    return r.json().get("transactions", [])


@st.cache_data(ttl=15)
def get_candles(count: int = 96):
    url = f"{BASE_URL}/v3/instruments/GBP_USD/candles"
    params = {"granularity": "M15", "count": count, "price": "M"}
    r = requests.get(url, headers=HEADERS, params=params)
    rows = []
    for c in r.json().get("candles", []):
        mid = c["mid"]
        rows.append({
            "datetime": pd.to_datetime(c["time"]),
            "Open":  float(mid["o"]),
            "High":  float(mid["h"]),
            "Low":   float(mid["l"]),
            "Close": float(mid["c"]),
        })
    return pd.DataFrame(rows)


# ── UI ─────────────────────────────────────────────────────────────────────

st.title("📈 Asian Breakout Bot — GBP/USD")
st.caption(f"OANDA {'🟡 Practice' if ENVIRONMENT == 'practice' else '🔴 LIVE'} Account  |  Refreshes every 30s")

# Auto-refresh
st.markdown(
    "<meta http-equiv='refresh' content='30'>",
    unsafe_allow_html=True
)

# ── Account metrics ────────────────────────────────────────────────────────
account = get_account_summary()

balance   = float(account.get("balance", 0))
nav       = float(account.get("NAV", 0))
unrealised = float(account.get("unrealizedPL", 0))
open_trade_count = int(account.get("openTradeCount", 0))

col1, col2, col3, col4 = st.columns(4)
col1.metric("💰 Balance",      f"£{balance:,.2f}")
col2.metric("📊 NAV",          f"£{nav:,.2f}")
col3.metric("📉 Unrealised P&L", f"£{unrealised:,.2f}", delta=f"{unrealised:+.2f}")
col4.metric("🔄 Open Trades",  open_trade_count)

st.divider()

# ── Price chart ────────────────────────────────────────────────────────────
st.subheader("GBP/USD — 15 Minute Chart (Last 24h)")

df = get_candles(count=96)

if not df.empty:
    fig = go.Figure(data=[go.Candlestick(
        x=df["datetime"],
        open=df["Open"],
        high=df["High"],
        low=df["Low"],
        close=df["Close"],
        increasing_line_color="#00c853",
        decreasing_line_color="#ff1744",
    )])

    # Add Asian session shading (00:00 - 07:00 UTC)
    now = datetime.now(timezone.utc)
    asian_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    asian_end   = now.replace(hour=7, minute=0, second=0, microsecond=0)

    fig.add_vrect(
        x0=asian_start, x1=asian_end,
        fillcolor="rgba(100, 149, 237, 0.15)",
        layer="below", line_width=0,
        annotation_text="Asian Session", annotation_position="top left"
    )

    fig.update_layout(
        height=400,
        xaxis_rangeslider_visible=False,
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(gridcolor="rgba(128,128,128,0.2)"),
        yaxis=dict(gridcolor="rgba(128,128,128,0.2)"),
        margin=dict(l=0, r=0, t=10, b=0),
    )

    st.plotly_chart(fig, use_container_width=True)

st.divider()

# ── Open trades ────────────────────────────────────────────────────────────
st.subheader("🔄 Open Trades")
open_trades = get_open_trades()

if open_trades:
    rows = []
    for t in open_trades:
        rows.append({
            "ID":         t["id"],
            "Direction":  "🟢 LONG" if int(t["currentUnits"]) > 0 else "🔴 SHORT",
            "Units":      abs(int(t["currentUnits"])),
            "Entry":      float(t["price"]),
            "SL":         float(t.get("stopLossOrder", {}).get("price", 0)),
            "TP":         float(t.get("takeProfitOrder", {}).get("price", 0)),
            "Unrealised": f"£{float(t['unrealizedPL']):+.2f}",
            "Opened":     pd.to_datetime(t["openTime"]).strftime("%H:%M UTC"),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
else:
    st.info("No open trades right now.")

st.divider()

# ── Closed trades / P&L ────────────────────────────────────────────────────
st.subheader("📋 Recent Closed Trades")
transactions = get_closed_trades(count=50)

if transactions:
    rows = []
    for t in transactions:
        pl = float(t.get("pl", 0))
        rows.append({
            "Time":   pd.to_datetime(t["time"]).strftime("%Y-%m-%d %H:%M"),
            "Instrument": t.get("instrument", ""),
            "Units":  t.get("units", ""),
            "Price":  t.get("price", ""),
            "P&L":    f"£{pl:+.2f}",
            "Result": "✅ Win" if pl > 0 else ("❌ Loss" if pl < 0 else "➖ BE"),
        })

    trade_df = pd.DataFrame(rows)
    st.dataframe(trade_df, use_container_width=True, hide_index=True)

    # Equity curve
    pls = [float(t.get("pl", 0)) for t in transactions]
    pls.reverse()
    cumulative = [500 + sum(pls[:i+1]) for i in range(len(pls))]

    if len(cumulative) > 1:
        st.subheader("📈 Equity Curve")
        fig2 = px.line(
            x=list(range(len(cumulative))),
            y=cumulative,
            labels={"x": "Trade #", "y": "Account Balance (£)"},
        )
        fig2.add_hline(y=500, line_dash="dash", line_color="gray", annotation_text="Starting £500")
        fig2.update_layout(
            height=300,
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=0, r=0, t=10, b=0),
        )
        st.plotly_chart(fig2, use_container_width=True)

        # Stats
        wins   = sum(1 for p in pls if p > 0)
        losses = sum(1 for p in pls if p < 0)
        total  = len([p for p in pls if p != 0])
        win_rate = (wins / total * 100) if total > 0 else 0
        total_pl = sum(pls)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Trades", total)
        c2.metric("Win Rate",     f"{win_rate:.1f}%")
        c3.metric("Total P&L",    f"£{total_pl:+.2f}")
        c4.metric("Return",       f"{(total_pl / 500 * 100):+.2f}%")
else:
    st.info("No closed trades yet. The bot will log results here as it trades.")

# ── Log viewer ─────────────────────────────────────────────────────────────
st.divider()
st.subheader("📝 Bot Log (Last 20 lines)")

log_path = "live/trading.log"
if os.path.exists(log_path):
    with open(log_path, "r") as f:
        lines = f.readlines()
    st.code("".join(lines[-20:]), language="text")
else:
    st.info("Log file not found. Start the live trader to see logs.")