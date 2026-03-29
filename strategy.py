"""
strategy.py — Backtrader trading strategies

Includes:
  - EMACrossStrategy    : Classic fast/slow EMA crossover with RSI filter
  - RSIMeanReversion    : Buy oversold, sell overbought with trend filter
  - MACDStrategy        : MACD signal line crossover

Each strategy logs trades for later analysis.
"""

import backtrader as bt


# ─── Base mixin for trade logging ────────────────────────────────────────────

class TradeLogMixin:
    """Mixin that records every completed trade into self.trade_log."""

    def __init_log__(self):
        self.trade_log = []
        self.entry_price = None
        self.entry_date = None

    def notify_trade(self, trade):
        if trade.isclosed:
            self.trade_log.append({
                "entry_date":  self.entry_date,
                "exit_date":   self.datas[0].datetime.date(0),
                "entry_price": self.entry_price,
                "exit_price":  trade.price,
                "pnl":         round(trade.pnlcomm, 6),
                "size":        trade.size,
            })

    def notify_order(self, order):
        if order.status == order.Completed and order.isbuy():
            self.entry_price = order.executed.price
            self.entry_date  = self.datas[0].datetime.date(0)


# ─── Strategy 1: EMA Crossover + RSI Filter ──────────────────────────────────

class EMACrossStrategy(TradeLogMixin, bt.Strategy):
    """
    Enter long when fast EMA crosses above slow EMA and RSI > 50.
    Enter short when fast EMA crosses below slow EMA and RSI < 50.
    Exit on reverse crossover.
    """

    params = dict(
        fast_period=10,
        slow_period=30,
        rsi_period=14,
        rsi_upper=60,
        rsi_lower=40,
        stake=0.95,           # fraction of available cash per trade
    )

    def __init__(self):
        self.__init_log__()
        self.fast_ema = bt.ind.EMA(period=self.p.fast_period)
        self.slow_ema = bt.ind.EMA(period=self.p.slow_period)
        self.crossover = bt.ind.CrossOver(self.fast_ema, self.slow_ema)
        self.rsi       = bt.ind.RSI(period=self.p.rsi_period)

    def next(self):
        size = (self.broker.getcash() * self.p.stake) / self.data.close[0]

        if not self.position:
            if self.crossover > 0 and self.rsi > self.p.rsi_upper:
                self.buy(size=size)
            elif self.crossover < 0 and self.rsi < self.p.rsi_lower:
                self.sell(size=size)
        else:
            if self.crossover < 0 and self.position.size > 0:
                self.close()
            elif self.crossover > 0 and self.position.size < 0:
                self.close()


# ─── Strategy 2: RSI Mean Reversion ──────────────────────────────────────────

class RSIMeanReversion(TradeLogMixin, bt.Strategy):
    """
    Buy when RSI dips below oversold threshold, sell when it recovers above
    overbought. Uses a 200-period SMA as a trend filter (long-only above SMA).
    """

    params = dict(
        rsi_period=14,
        oversold=30,
        overbought=70,
        sma_period=200,
        stake=0.95,
    )

    def __init__(self):
        self.__init_log__()
        self.rsi = bt.ind.RSI(period=self.p.rsi_period)
        self.sma = bt.ind.SMA(period=self.p.sma_period)

    def next(self):
        size = (self.broker.getcash() * self.p.stake) / self.data.close[0]
        above_sma = self.data.close[0] > self.sma[0]

        if not self.position:
            if self.rsi < self.p.oversold and above_sma:
                self.buy(size=size)
            elif self.rsi > self.p.overbought and not above_sma:
                self.sell(size=size)
        else:
            if self.position.size > 0 and self.rsi > self.p.overbought:
                self.close()
            elif self.position.size < 0 and self.rsi < self.p.oversold:
                self.close()


# ─── Strategy 3: MACD Crossover ──────────────────────────────────────────────

class MACDStrategy(TradeLogMixin, bt.Strategy):
    """
    Enter long when MACD line crosses above signal line (histogram turns positive).
    Enter short on reverse. Optional ATR-based stop loss.
    """

    params = dict(
        macd_fast=12,
        macd_slow=26,
        macd_signal=9,
        atr_period=14,
        atr_stop_mult=2.0,    # ATR multiplier for stop loss (0 = disabled)
        stake=0.95,
    )

    def __init__(self):
        self.__init_log__()
        macd_ind       = bt.ind.MACD(
            period_me1=self.p.macd_fast,
            period_me2=self.p.macd_slow,
            period_signal=self.p.macd_signal,
        )
        self.macd      = macd_ind.macd
        self.signal    = macd_ind.signal
        self.crossover = bt.ind.CrossOver(self.macd, self.signal)
        self.atr       = bt.ind.ATR(period=self.p.atr_period)
        self.stop_price = None

    def next(self):
        size = (self.broker.getcash() * self.p.stake) / self.data.close[0]

        if not self.position:
            if self.crossover > 0:
                self.buy(size=size)
                if self.p.atr_stop_mult:
                    self.stop_price = self.data.close[0] - self.atr[0] * self.p.atr_stop_mult
            elif self.crossover < 0:
                self.sell(size=size)
                if self.p.atr_stop_mult:
                    self.stop_price = self.data.close[0] + self.atr[0] * self.p.atr_stop_mult
        else:
            # ATR stop loss
            if self.p.atr_stop_mult and self.stop_price:
                if self.position.size > 0 and self.data.close[0] < self.stop_price:
                    self.close()
                    return
                if self.position.size < 0 and self.data.close[0] > self.stop_price:
                    self.close()
                    return
            # Signal exit
            if self.crossover < 0 and self.position.size > 0:
                self.close()
            elif self.crossover > 0 and self.position.size < 0:
                self.close()


# ─── Registry ─────────────────────────────────────────────────────────────────

STRATEGIES = {
    "EMA Crossover": EMACrossStrategy,
    "RSI Mean Reversion": RSIMeanReversion,
    "MACD Crossover": MACDStrategy,
}
