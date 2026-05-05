"""
EUR/USD H4 Backtest Runner
===========================
Focused single-pair runner for EUR/USD H4.
Run: python run_all.py  (from your TradingBot/ root folder)
"""

import os, sys
import pandas as pd
from backtesting import Backtest
import warnings
warnings.filterwarnings("ignore")

SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = SCRIPT_DIR
os.chdir(PROJECT_ROOT)
sys.path.insert(0, SCRIPT_DIR)

from strategy import make_strategy, get_pip_size, get_spread, ACCOUNT_SIZE

PAIR      = "EUR_USD"
TIMEFRAME = "H4"


def run():
    data_path = os.path.join("data", f"{PAIR}_{TIMEFRAME}.csv")

    if not os.path.exists(data_path):
        print(f"✗ Missing data file: {data_path}")
        print(f"  Run: python data/fetch_all.py")
        return

    print("=" * 55)
    print("  EUR/USD H4 — Asian Range Mean Reversion v4")
    print("=" * 55)

    try:
        df = pd.read_csv(data_path, index_col="datetime", parse_dates=True)
        df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
    except Exception as e:
        print(f"✗ Load error: {e}")
        return

    print(f"  Candles loaded : {len(df)}")
    print(f"  Date range     : {df.index[0].date()} → {df.index[-1].date()}")

    pip    = get_pip_size(PAIR)
    spread = get_spread(PAIR)

    S = make_strategy(
        min_range_val  = 20 * pip,
        min_pierce_val = 8  * pip,
        sl_mult_val    = 0.5,
        cutoff_val     = 20,   # H4: flat by 20:00 UTC
    )

    bt    = Backtest(df, S, cash=ACCOUNT_SIZE, commission=spread,
                     exclusive_orders=True, trade_on_close=True)
    stats = bt.run()

    trades = int(stats["# Trades"])
    ret    = stats["Return [%]"]
    sharpe = stats["Sharpe Ratio"]
    dd     = stats["Max. Drawdown [%]"]
    wr     = stats["Win Rate [%]"]
    pf     = stats["Profit Factor"]

    print(f"\n  Trades         : {trades}")
    print(f"  Return         : {ret:+.2f}%")
    print(f"  Sharpe         : {sharpe:.2f}")
    print(f"  Max Drawdown   : {dd:.2f}%")
    print(f"  Win Rate       : {wr:.1f}%")
    print(f"  Profit Factor  : {pf:.2f}")
    print("=" * 55)

    if trades > 0:
        os.makedirs("backtest", exist_ok=True)
        chart_path = f"backtest/chart_{PAIR}_{TIMEFRAME}.html"
        bt.plot(filename=chart_path, open_browser=False)
        print(f"\n  Chart saved → {chart_path}")


if __name__ == "__main__":
    run()