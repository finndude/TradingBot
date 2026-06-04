"""
strategy.py — Strategy Definition
===================================
THIS is the only file you edit.

Current strategy: RSI Mean Reversion + 200 MA Trend Filter + ATR SL/TP
------------------------------------------------------------------------
Starting fresh on SPY with a clean, well-documented strategy.

Logic:
  - Only enter when SPY is above its 200-period MA (uptrend only)
  - Enter long when RSI drops below oversold threshold (buying the dip)
  - ATR-based stop loss and take profit (no discretionary exits)

This is deliberately simple. Simple strategies that work are more
trustworthy than complex ones — fewer parameters to overfit.

Parameters to tune:
  - MA_WINDOW:   trend filter MA period
  - RSI_WINDOW:  RSI calculation period
  - RSI_ENTRY:   RSI level to trigger entry (lower = more oversold)
  - ATR_WINDOW:  ATR period for sizing SL/TP
  - ATR_MULT_SL: stop loss distance in ATR multiples
  - ATR_MULT_TP: take profit distance in ATR multiples
"""

import pandas as pd
import numpy as np
import vectorbt as vbt

# ─────────────────────────────────────────────
# STRATEGY IDENTITY
# ─────────────────────────────────────────────

STRATEGY_NAME = "RSI Dip Buy + 200 MA + ATR SL/TP"

PARAMS = {
    "MA_WINDOW":   200,
    "RSI_WINDOW":  14,
    "RSI_ENTRY":   40,    # Enter on any mild dip (loosened from 30)
    "ATR_WINDOW":  14,
    "ATR_MULT_SL": 1.5,
    "ATR_MULT_TP": 3.0,   # 2R reward:risk
}


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def compute_atr(ohlcv, window):
    high       = ohlcv["high"]
    low        = ohlcv["low"]
    close      = ohlcv["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(window).mean()


# ─────────────────────────────────────────────
# SIGNAL GENERATION
# ─────────────────────────────────────────────

def generate_signals(ohlcv):
    p     = PARAMS
    close = ohlcv["close"]
    n     = len(ohlcv)

    ma  = close.rolling(p["MA_WINDOW"]).mean()
    rsi = vbt.RSI.run(close, p["RSI_WINDOW"]).rsi
    atr = compute_atr(ohlcv, p["ATR_WINDOW"])

    above_ma     = close > ma
    rsi_oversold = rsi < p["RSI_ENTRY"]

    entries = (above_ma & rsi_oversold).fillna(False)

    # No manual exits — ATR SL/TP handles everything
    exits = pd.Series(False, index=ohlcv.index)

    # SL/TP as fraction of entry price
    sl_stop = ((p["ATR_MULT_SL"] * atr) / close).where(entries)
    tp_stop = ((p["ATR_MULT_TP"] * atr) / close).where(entries)

    return entries, exits, sl_stop, tp_stop