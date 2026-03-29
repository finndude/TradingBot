"""
metrics.py — Chart builders and derived metrics for the dashboard
"""

import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots


ACCENT   = "#00d4aa"   # teal green
NEGATIVE = "#ff4d6d"   # red
NEUTRAL  = "#8892a4"   # muted grey
BG       = "#0d1117"
PANEL    = "#161b22"
TEXT     = "#e6edf3"


def _base_layout(title: str) -> dict:
    return dict(
        title=dict(text=title, font=dict(color=TEXT, size=15)),
        paper_bgcolor=BG,
        plot_bgcolor=PANEL,
        font=dict(color=TEXT, family="monospace"),
        xaxis=dict(gridcolor="#21262d", showgrid=True),
        yaxis=dict(gridcolor="#21262d", showgrid=True),
        margin=dict(l=40, r=20, t=50, b=40),
    )


# ── Equity Curve ──────────────────────────────────────────────────────────────

def plot_equity_curve(equity: pd.Series, initial_cash: float) -> go.Figure:
    color = ACCENT if equity.iloc[-1] >= initial_cash else NEGATIVE

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=equity.index,
        y=equity.values,
        mode="lines",
        name="Portfolio Value",
        line=dict(color=color, width=2),
        fill="tozeroy",
        fillcolor=f"rgba(0,212,170,0.07)" if color == ACCENT else "rgba(255,77,109,0.07)",
    ))
    fig.add_hline(
        y=initial_cash,
        line_dash="dash",
        line_color=NEUTRAL,
        annotation_text="Starting Capital",
        annotation_font_color=NEUTRAL,
    )
    fig.update_layout(**_base_layout("Equity Curve"))
    return fig


# ── Drawdown ──────────────────────────────────────────────────────────────────

def plot_drawdown(equity: pd.Series) -> go.Figure:
    roll_max = equity.cummax()
    drawdown = (equity - roll_max) / roll_max * 100

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=drawdown.index,
        y=drawdown.values,
        mode="lines",
        name="Drawdown %",
        line=dict(color=NEGATIVE, width=1.5),
        fill="tozeroy",
        fillcolor="rgba(255,77,109,0.15)",
    ))
    fig.update_layout(**_base_layout("Drawdown (%)"))
    fig.update_yaxes(ticksuffix="%")
    return fig


# ── Monthly Returns Heatmap ───────────────────────────────────────────────────

def plot_monthly_heatmap(equity: pd.Series) -> go.Figure:
    monthly = equity.resample("ME").last().pct_change().dropna() * 100
    monthly.index = monthly.index.to_period("M")

    df = pd.DataFrame({
        "year":   monthly.index.year,
        "month":  monthly.index.month,
        "return": monthly.values,
    })

    if df.empty:
        fig = go.Figure()
        fig.update_layout(**_base_layout("Monthly Returns (%)"))
        return fig

    pivot = df.pivot(index="year", columns="month", values="return")
    month_labels = ["Jan","Feb","Mar","Apr","May","Jun",
                    "Jul","Aug","Sep","Oct","Nov","Dec"]
    col_labels = [month_labels[c - 1] for c in pivot.columns]

    fig = go.Figure(go.Heatmap(
        z=pivot.values,
        x=col_labels,
        y=[str(y) for y in pivot.index],
        colorscale=[[0, NEGATIVE], [0.5, PANEL], [1, ACCENT]],
        zmid=0,
        text=np.round(pivot.values, 1),
        texttemplate="%{text}%",
        showscale=True,
    ))
    fig.update_layout(**_base_layout("Monthly Returns (%)"))
    return fig


# ── Trade PnL Distribution ────────────────────────────────────────────────────

def plot_pnl_distribution(trade_log: list) -> go.Figure:
    if not trade_log:
        fig = go.Figure()
        fig.update_layout(**_base_layout("P&L Distribution"))
        return fig

    pnls = [t["pnl"] for t in trade_log]
    colors = [ACCENT if p >= 0 else NEGATIVE for p in pnls]

    fig = go.Figure(go.Bar(
        x=list(range(1, len(pnls) + 1)),
        y=pnls,
        marker_color=colors,
        name="Trade P&L",
    ))
    fig.add_hline(y=0, line_color=NEUTRAL, line_dash="dash")
    fig.update_layout(**_base_layout("Trade P&L"))
    fig.update_xaxes(title="Trade #")
    fig.update_yaxes(title="P&L")
    return fig


# ── Price + Signals ───────────────────────────────────────────────────────────

def plot_price_with_trades(ohlcv: pd.DataFrame, trade_log: list) -> go.Figure:
    fig = go.Figure()

    # Candlestick
    fig.add_trace(go.Candlestick(
        x=ohlcv.index,
        open=ohlcv["Open"],
        high=ohlcv["High"],
        low=ohlcv["Low"],
        close=ohlcv["Close"],
        name="EUR/USD",
        increasing_line_color=ACCENT,
        decreasing_line_color=NEGATIVE,
    ))

    # Entry markers
    if trade_log:
        entries = pd.DataFrame(trade_log)
        entries["entry_date"] = pd.to_datetime(entries["entry_date"])
        entries["exit_date"]  = pd.to_datetime(entries["exit_date"])

        # Merge with closest OHLCV price for y-position
        ohlcv_reset = ohlcv.reset_index()
        ohlcv_reset.columns = ["date"] + list(ohlcv.columns)

        fig.add_trace(go.Scatter(
            x=entries["entry_date"],
            y=entries["entry_price"],
            mode="markers",
            marker=dict(symbol="triangle-up", size=10, color=ACCENT),
            name="Entry",
        ))
        fig.add_trace(go.Scatter(
            x=entries["exit_date"],
            y=entries["exit_price"],
            mode="markers",
            marker=dict(symbol="triangle-down", size=10, color=NEGATIVE),
            name="Exit",
        ))

    layout = _base_layout("Price Chart with Trade Entries/Exits")
    layout["xaxis"]["rangeslider"] = {"visible": False}
    fig.update_layout(**layout)
    return fig


# ── Win/Loss Pie ──────────────────────────────────────────────────────────────

def plot_win_loss_pie(won: int, lost: int) -> go.Figure:
    fig = go.Figure(go.Pie(
        labels=["Wins", "Losses"],
        values=[won, lost],
        marker=dict(colors=[ACCENT, NEGATIVE]),
        hole=0.55,
        textinfo="label+percent",
        textfont=dict(color=TEXT),
    ))
    fig.update_layout(**_base_layout("Win / Loss Split"))
    return fig
