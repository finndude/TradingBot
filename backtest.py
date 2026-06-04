"""
backtest.py — Backtesting Engine
=================================
DO NOT MODIFY THIS FILE.

Tests the strategy in strategy.py across SPY timeframes.
Reads from data/SPY_*.csv files produced by download_data.py.

Usage:
    python backtest.py
"""

import warnings
warnings.filterwarnings("ignore")

import os
import pandas as pd
import numpy as np
import vectorbt as vbt
from datetime import datetime

from strategy import generate_signals, STRATEGY_NAME, PARAMS

# ─────────────────────────────────────────────
# ENGINE CONFIG
# ─────────────────────────────────────────────

DATA_DIR   = "data"
TRAIN_END  = "2019-12-31"
TEST_START = "2020-01-01"

INIT_CASH  = 10_000
FEES       = 0.001     # 0.1% per trade (realistic retail broker)

TIMEFRAMES = {
    "1H": {"file": "SPY_1H.csv",  "freq": "1H",  "hours": 1},
    "4H": {"file": "SPY_4H.csv",  "freq": "4H",  "hours": 4},
    "1D": {"file": "SPY_1D.csv",  "freq": "1D",  "hours": 24},
}


# ─────────────────────────────────────────────
# DATA
# ─────────────────────────────────────────────

def load_ohlcv(filepath):
    df = pd.read_csv(filepath, index_col="datetime", parse_dates=True)
    df.columns = [c.lower() for c in df.columns]
    df = df[["open", "high", "low", "close", "volume"]]
    df = df[~df.index.duplicated(keep="first")]
    df = df.sort_index()
    df = df.dropna()
    return df


def split(df):
    train = df[df.index <= TRAIN_END]
    test  = df[df.index >= TEST_START]
    return train, test


# ─────────────────────────────────────────────
# PORTFOLIO
# ─────────────────────────────────────────────

def run_portfolio(ohlcv, entries, exits, freq, sl_stop=None, tp_stop=None):
    close = ohlcv["close"]
    return vbt.Portfolio.from_signals(
        close,
        entries,
        exits,
        init_cash=INIT_CASH,
        fees=FEES,
        freq=freq,
        sl_stop=sl_stop,
        tp_stop=tp_stop,
    )


def buy_and_hold(ohlcv, freq):
    return vbt.Portfolio.from_holding(
        ohlcv["close"], init_cash=INIT_CASH, fees=FEES, freq=freq
    )


# ─────────────────────────────────────────────
# METRICS
# ─────────────────────────────────────────────

def get_metrics(portfolio, n_candles, freq_hours):
    stats      = portfolio.stats()
    total_ret  = stats.get("Total Return [%]", np.nan)
    sharpe     = stats.get("Sharpe Ratio", np.nan)
    max_dd     = stats.get("Max Drawdown [%]", np.nan)
    num_trades = stats.get("Total Trades", np.nan)
    win_rate   = stats.get("Win Rate [%]", np.nan)

    n_years = (n_candles * freq_hours) / (252 * 6.5)  # SPY trades ~6.5h/day
    cagr = ((1 + total_ret / 100) ** (1 / n_years) - 1) * 100 if n_years > 0 and not np.isnan(total_ret) else np.nan

    return {
        "CAGR %":    round(float(cagr), 2)      if not np.isnan(cagr)       else np.nan,
        "Sharpe":    round(float(sharpe), 2)    if not np.isnan(sharpe)     else np.nan,
        "Max DD %":  round(float(max_dd), 2)    if not np.isnan(max_dd)     else np.nan,
        "Trades":    int(num_trades)             if not np.isnan(num_trades) else 0,
        "Win Rate %":round(float(win_rate), 2)  if not np.isnan(win_rate)   else np.nan,
    }


def print_row(label, m):
    print(f"  {label:<14} {m['CAGR %']:>6}%  {m['Sharpe']:>7}  {m['Max DD %']:>7}%  {m['Trades']:>7}  {m['Win Rate %']:>8}%")


# ─────────────────────────────────────────────
# VERDICT
# ─────────────────────────────────────────────

def verdict(strat, bnh):
    beats_cagr   = strat["CAGR %"]  > bnh["CAGR %"]
    beats_sharpe = strat["Sharpe"]  > bnh["Sharpe"]
    beats_dd     = abs(strat["Max DD %"]) < abs(bnh["Max DD %"])
    score        = sum([beats_cagr, beats_sharpe, beats_dd])
    if score == 3:   return "✅ STRONG"
    elif score == 2: return "⚠️  PARTIAL"
    else:            return "❌ WEAK"


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    print("=" * 72)
    print(f"  STRATEGY : {STRATEGY_NAME}")
    print(f"  PARAMS   : {PARAMS}")
    print(f"  TRAIN    : up to {TRAIN_END}  |  TEST: {TEST_START} → today")
    print("=" * 72)

    results = []

    for tf_name, cfg in TIMEFRAMES.items():
        filepath = os.path.join(DATA_DIR, cfg["file"])

        if not os.path.exists(filepath):
            print(f"\n  ⚠️  {tf_name}: {filepath} not found — run download_data.py first.")
            continue

        print(f"\n── {tf_name} {'─' * 60}")

        try:
            ohlcv = load_ohlcv(filepath)
            train_ohlcv, test_ohlcv = split(ohlcv)
            freq = cfg["freq"]
            fh   = cfg["hours"]

            print(f"  Data: {len(ohlcv)} candles | Train: {len(train_ohlcv)} | Test: {len(test_ohlcv)}")
            if len(train_ohlcv) < 500:
                print(f"  ⚠️  WARNING: thin train set — results may not be reliable.")

            # Benchmark
            bnh_m = get_metrics(buy_and_hold(test_ohlcv, freq), len(test_ohlcv), fh)

            # Strategy — train
            sig_train = generate_signals(train_ohlcv)
            e_tr, x_tr = sig_train[0], sig_train[1]
            sl_tr = sig_train[2] if len(sig_train) > 2 else None
            tp_tr = sig_train[3] if len(sig_train) > 3 else None
            pf_tr = run_portfolio(train_ohlcv, e_tr, x_tr, freq, sl_tr, tp_tr)
            m_tr  = get_metrics(pf_tr, len(train_ohlcv), fh)

            # Strategy — test
            sig_test = generate_signals(test_ohlcv)
            e_te, x_te = sig_test[0], sig_test[1]
            sl_te = sig_test[2] if len(sig_test) > 2 else None
            tp_te = sig_test[3] if len(sig_test) > 3 else None
            pf_te = run_portfolio(test_ohlcv, e_te, x_te, freq, sl_te, tp_te)
            m_te  = get_metrics(pf_te, len(test_ohlcv), fh)

            v = verdict(m_te, bnh_m)

            print(f"  {'':14} {'CAGR':>7}  {'Sharpe':>7}  {'Max DD':>8}  {'Trades':>7}  {'Win Rate':>9}")
            print_row("BnH (test)",    bnh_m)
            print_row("Strat (train)", m_tr)
            print_row("Strat (test)",  m_te)
            print(f"  Verdict: {v}")

            gap = m_tr["CAGR %"] - m_te["CAGR %"]
            if not np.isnan(gap) and gap > 5:
                print(f"  ⚠️  OVERFIT WARNING: Train/Test CAGR gap = {gap:.1f}pp")

            results.append({
                "TF": tf_name,
                "BnH CAGR%":    bnh_m["CAGR %"],
                "Strat CAGR%":  m_te["CAGR %"],
                "Sharpe":       m_te["Sharpe"],
                "Max DD%":      m_te["Max DD %"],
                "Trades":       m_te["Trades"],
                "Win Rate%":    m_te["Win Rate %"],
                "Verdict":      v,
            })

        except Exception as e:
            print(f"  ❌ Error on {tf_name}: {e}")
            import traceback; traceback.print_exc()

    if results:
        print("\n" + "=" * 72)
        print("  SUMMARY — TEST PERIOD")
        print("=" * 72)
        print(pd.DataFrame(results).to_string(index=False))

    print("\n" + "=" * 72)


if __name__ == "__main__":
    main()