"""
data.py — Fetch OHLCV data from yfinance
"""

import yfinance as yf
import pandas as pd


PAIR_MAP = {
    "EUR/USD": "EURUSD=X",
    "GBP/USD": "GBPUSD=X",
    "USD/JPY": "USDJPY=X",
    "XAU/USD": "GC=F",
}

INTERVAL_MAP = {
    "1d": "1d",
    "1h": "1h",
    "4h": "1h",  # yfinance has no 4h; we resample below
}


def fetch_ohlcv(pair: str, start: str, end: str, interval: str = "1d") -> pd.DataFrame:
    """
    Fetch OHLCV data for a given pair and date range.

    Args:
        pair:     Human-readable pair e.g. "EUR/USD"
        start:    Start date string "YYYY-MM-DD"
        end:      End date string "YYYY-MM-DD"
        interval: "1d", "1h", or "4h"

    Returns:
        DataFrame with columns: Open, High, Low, Close, Volume
    """
    ticker = PAIR_MAP.get(pair)
    if not ticker:
        raise ValueError(f"Unknown pair: {pair}. Valid options: {list(PAIR_MAP.keys())}")

    yf_interval = INTERVAL_MAP.get(interval, "1d")
    df = yf.download(ticker, start=start, end=end, interval=yf_interval, progress=False)

    if df.empty:
        raise ValueError(f"No data returned for {pair} ({ticker}). Check date range.")

    # Flatten multi-level columns if present (yfinance sometimes returns them)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()

    # Resample to 4h if requested
    if interval == "4h":
        df = df.resample("4h").agg({
            "Open": "first",
            "High": "max",
            "Low": "min",
            "Close": "last",
            "Volume": "sum",
        }).dropna()

    df.index = pd.to_datetime(df.index)
    return df


def available_pairs() -> list[str]:
    return list(PAIR_MAP.keys())
