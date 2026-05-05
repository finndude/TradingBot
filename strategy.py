"""
Asian Range Mean Reversion — v4
=================================
Fixes vs v3:
  - Simplified daily reset: always resets at midnight (date change)
  - Asian session unified: 00:00-07:00 UTC for ALL pairs
    (debug confirmed JPY data has hours 0-6, no special handling needed)
  - Removed over-engineered JPY session offset that caused 0 trades
  - make_strategy() still available for parameter injection

Strategy logic:
  1. Build Asian range: 00:00-07:00 UTC candles
  2. After 07:00, wait for price to PIERCE range boundary by min_pierce
  3. If NEXT candle closes back INSIDE range → enter counter-trend
  4. SHORT fade: SL above pierce extreme (0.5x dist), TP at range low
  5. LONG fade:  SL below pierce extreme (0.5x dist), TP at range high
  6. One trade per day, flat by cutoff hour
"""

import os
import pandas as pd
import numpy as np
from backtesting import Backtest, Strategy
import warnings
warnings.filterwarnings("ignore")

SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = SCRIPT_DIR
os.chdir(PROJECT_ROOT)

ACCOUNT_SIZE = 500
RISK_PCT     = 0.01


def get_pip_size(pair: str) -> float:
    return 0.01 if "JPY" in pair else 0.0001


def get_spread(pair: str) -> float:
    return {
        "EUR_USD": 0.00010,
        "GBP_USD": 0.00015,
        "USD_JPY": 0.0015,
        "AUD_JPY": 0.0025,
        "GBP_JPY": 0.0040,
    }.get(pair, 0.0002)


def is_jpy_pair(pair: str) -> bool:
    return "JPY" in pair


def make_strategy(min_range_val, min_pierce_val, sl_mult_val, cutoff_val, jpy=False):
    """
    Returns a Strategy subclass with parameters baked in.
    Always use this instead of bt.run(param=val) — the latter
    does not reliably override class attributes in backtesting.py.
    """
    class ConfiguredStrategy(MeanReversionV3):
        min_range     = min_range_val
        min_pierce    = min_pierce_val
        sl_multiplier = sl_mult_val
        trade_cutoff  = cutoff_val
    return ConfiguredStrategy


class MeanReversionV3(Strategy):

    asian_start   = 0    # 00:00 UTC
    asian_end     = 7    # 07:00 UTC
    trade_cutoff  = 16
    min_range     = 0.0020
    min_pierce    = 0.0008
    sl_multiplier = 0.5

    def init(self):
        self.asian_high     = None
        self.asian_low      = None
        self.traded_today   = False
        self.current_day    = None
        self.pierced_high   = False
        self.pierced_low    = False
        self.pierce_extreme = None

    def next(self):
        dt    = self.data.index[-1]
        hour  = dt.hour
        day   = dt.date()
        close = self.data.Close[-1]
        high  = self.data.High[-1]
        low   = self.data.Low[-1]

        # ── Reset at midnight (date change) ────────────────────────────────
        if self.current_day != day:
            self.current_day    = day
            self.asian_high     = None
            self.asian_low      = None
            self.traded_today   = False
            self.pierced_high   = False
            self.pierced_low    = False
            self.pierce_extreme = None

        # ── Build Asian range 00:00-07:00 ──────────────────────────────────
        if self.asian_start <= hour < self.asian_end:
            self.asian_high = max(self.asian_high, high) if self.asian_high else high
            self.asian_low  = min(self.asian_low,  low)  if self.asian_low  else low
            return

        # ── Force flat at cutoff ───────────────────────────────────────────
        if hour >= self.trade_cutoff:
            if self.position:
                self.position.close()
            return

        # ── Guards ────────────────────────────────────────────────────────
        if self.asian_high is None or self.asian_low is None:
            return
        if self.traded_today or self.position:
            return

        range_size = self.asian_high - self.asian_low
        if range_size < self.min_range:
            return

        # ── Step 1: Detect pierce ──────────────────────────────────────────
        if not self.pierced_high and not self.pierced_low:
            if high > self.asian_high + self.min_pierce:
                self.pierced_high   = True
                self.pierce_extreme = high
                return
            if low < self.asian_low - self.min_pierce:
                self.pierced_low    = True
                self.pierce_extreme = low
                return

        # ── Step 2: Confirm reversal → enter ──────────────────────────────
        if self.pierced_high and self.pierce_extreme is not None:
            if close < self.asian_high:
                entry       = close
                pierce_dist = self.pierce_extreme - self.asian_high
                sl          = self.pierce_extreme + (pierce_dist * self.sl_multiplier)
                tp          = self.asian_low
                risk        = sl - entry
                if risk > 0 and tp < entry and sl > entry:
                    size = max(0.01, min(
                        round((ACCOUNT_SIZE * RISK_PCT) / (risk * self.equity), 4), 0.5
                    ))
                    self.sell(sl=sl, tp=tp, size=size)
                    self.traded_today   = True
                    self.pierced_high   = False
                    self.pierce_extreme = None
            else:
                self.pierced_high   = False
                self.pierce_extreme = None

        elif self.pierced_low and self.pierce_extreme is not None:
            if close > self.asian_low:
                entry       = close
                pierce_dist = self.asian_low - self.pierce_extreme
                sl          = self.pierce_extreme - (pierce_dist * self.sl_multiplier)
                tp          = self.asian_high
                risk        = entry - sl
                if risk > 0 and tp > entry and sl < entry:
                    size = max(0.01, min(
                        round((ACCOUNT_SIZE * RISK_PCT) / (risk * self.equity), 4), 0.5
                    ))
                    self.buy(sl=sl, tp=tp, size=size)
                    self.traded_today   = True
                    self.pierced_low    = False
                    self.pierce_extreme = None
            else:
                self.pierced_low    = False
                self.pierce_extreme = None


def run_single(data_path: str, pair: str, timeframe: str):
    """Convenience wrapper for running a single pair/timeframe."""
    try:
        df = pd.read_csv(data_path, index_col="datetime", parse_dates=True)
        df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
    except Exception as e:
        print(f"  Could not load {data_path}: {e}")
        return None

    if len(df) < 100:
        return None

    pip    = get_pip_size(pair)
    spread = get_spread(pair)
    cutoff = 20 if timeframe == "H4" else 16

    S = make_strategy(
        min_range_val  = 20 * pip,
        min_pierce_val = 8  * pip,
        sl_mult_val    = 0.5,
        cutoff_val     = cutoff,
    )

    bt = Backtest(df, S, cash=ACCOUNT_SIZE, commission=spread,
                  exclusive_orders=True, trade_on_close=True)
    return bt.run()