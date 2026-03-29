"""
backtest.py — Run a Backtrader backtest and return structured results
"""

import backtrader as bt
import pandas as pd
import numpy as np
from data import fetch_ohlcv
from strategy import STRATEGIES


def run_backtest(
    pair: str,
    start: str,
    end: str,
    interval: str,
    strategy_name: str,
    initial_cash: float = 10_000.0,
    commission: float = 0.0002,      # 0.02% per trade (typical forex spread equivalent)
    strategy_params: dict = None,
) -> dict:
    """
    Run a full backtest and return results as a dict containing:
      - equity_curve : pd.Series (date -> portfolio value)
      - trade_log    : list of trade dicts
      - stats        : dict of summary statistics
      - ohlcv        : pd.DataFrame of raw price data
    """

    # ── Fetch data ────────────────────────────────────────────────────────────
    df = fetch_ohlcv(pair, start, end, interval)

    # ── Build Cerebro ─────────────────────────────────────────────────────────
    cerebro = bt.Cerebro()
    cerebro.broker.setcash(initial_cash)
    cerebro.broker.setcommission(commission=commission)

    # Feed data
    data_feed = bt.feeds.PandasData(dataname=df)
    cerebro.adddata(data_feed)

    # Add strategy
    strategy_cls = STRATEGIES.get(strategy_name)
    if not strategy_cls:
        raise ValueError(f"Unknown strategy: {strategy_name}")

    params = strategy_params or {}
    cerebro.addstrategy(strategy_cls, **params)

    # Observers / analyzers
    cerebro.addanalyzer(bt.analyzers.TimeReturn, _name="time_return")
    cerebro.addanalyzer(bt.analyzers.DrawDown,   _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
    cerebro.addanalyzer(bt.analyzers.SharpeRatio,
                        _name="sharpe",
                        riskfreerate=0.0,
                        annualize=True,
                        timeframe=bt.TimeFrame.Days)

    # ── Run ───────────────────────────────────────────────────────────────────
    results = cerebro.run()
    strat   = results[0]

    # ── Equity curve ──────────────────────────────────────────────────────────
    time_returns = strat.analyzers.time_return.get_analysis()
    equity = _build_equity_curve(time_returns, initial_cash, df.index)

    # ── Trade log ─────────────────────────────────────────────────────────────
    trade_log = getattr(strat, "trade_log", [])

    # ── Summary stats ─────────────────────────────────────────────────────────
    dd_analysis     = strat.analyzers.drawdown.get_analysis()
    trade_analysis  = strat.analyzers.trades.get_analysis()
    sharpe_analysis = strat.analyzers.sharpe.get_analysis()

    final_value  = cerebro.broker.getvalue()
    total_return = (final_value - initial_cash) / initial_cash * 100

    total_trades = trade_analysis.get("total", {}).get("closed", 0)
    won          = trade_analysis.get("won",   {}).get("total", 0)
    lost         = trade_analysis.get("lost",  {}).get("total", 0)
    win_rate     = (won / total_trades * 100) if total_trades else 0

    avg_win  = trade_analysis.get("won",  {}).get("pnl", {}).get("average", 0)
    avg_loss = trade_analysis.get("lost", {}).get("pnl", {}).get("average", 0)
    profit_factor = abs(avg_win / avg_loss) if avg_loss else float("inf")

    stats = {
        "initial_cash":   initial_cash,
        "final_value":    round(final_value, 2),
        "total_return":   round(total_return, 2),
        "total_trades":   total_trades,
        "won":            won,
        "lost":           lost,
        "win_rate":       round(win_rate, 1),
        "profit_factor":  round(profit_factor, 2),
        "max_drawdown":   round(dd_analysis.get("max", {}).get("drawdown", 0), 2),
        "sharpe_ratio":   round(sharpe_analysis.get("sharperatio") or 0, 3),
        "avg_win":        round(avg_win, 6),
        "avg_loss":       round(avg_loss, 6),
    }

    return {
        "equity_curve": equity,
        "trade_log":    trade_log,
        "stats":        stats,
        "ohlcv":        df,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_equity_curve(
    time_returns: dict,
    initial_cash: float,
    price_index: pd.DatetimeIndex,
) -> pd.Series:
    """
    Convert Backtrader's TimeReturn dict into a portfolio value Series
    aligned to the price data's date index.
    """
    if not time_returns:
        return pd.Series([initial_cash], index=[price_index[0]])

    dates  = sorted(time_returns.keys())
    values = [initial_cash]
    current = initial_cash

    for d in dates:
        current *= (1 + time_returns[d])
        values.append(current)

    # Build a clean datetime index
    dt_index = pd.to_datetime([price_index[0]] + [pd.Timestamp(d) for d in dates])
    series = pd.Series(values, index=dt_index)
    series = series[~series.index.duplicated(keep="last")]
    return series
