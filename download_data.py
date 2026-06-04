"""
download_data.py — One-time data downloader
============================================
Downloads SPY (ETF CFD) OHLCV data from Dukascopy for all timeframes.
Data saved to data/ folder as CSVs.

Re-run anytime to refresh data up to today.

Usage:
    python download_data.py
"""

import os
import dukascopy_python as dk
import pandas as pd
from datetime import datetime

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

INSTRUMENT = "SPY.US/USD"    # SPY ETF CFD on Dukascopy
OFFER_SIDE = dk.OFFER_SIDE_BID
START      = datetime(2010, 1, 1)
END        = datetime.today()
DATA_DIR   = "data"

TIMEFRAMES = {
    "1H":  dk.INTERVAL_HOUR_1,
    "4H":  dk.INTERVAL_HOUR_4,
    "1D":  dk.INTERVAL_DAY_1,
}

# ─────────────────────────────────────────────
# DOWNLOAD
# ─────────────────────────────────────────────

def download_all():
    os.makedirs(DATA_DIR, exist_ok=True)

    for tf_name, interval in TIMEFRAMES.items():
        out_path = os.path.join(DATA_DIR, f"SPY_{tf_name}.csv")
        print(f"\nDownloading SPY {tf_name}...", end=" ", flush=True)

        try:
            df = dk.fetch(
                instrument=INSTRUMENT,
                interval=interval,
                offer_side=OFFER_SIDE,
                start=START,
                end=END,
            )

            if df is None or df.empty:
                print(f"❌ No data returned.")
                continue

            df.index.name = "datetime"
            df.columns = [c.lower() for c in df.columns]
            df = df[["open", "high", "low", "close", "volume"]]
            df = df[~df.index.duplicated(keep="first")]
            df.index = pd.to_datetime(df.index, utc=True)
            df.to_csv(out_path)
            print(f"✅ {len(df)} candles → {out_path}  [{df.index[0].date()} to {df.index[-1].date()}]")

        except Exception as e:
            print(f"❌ Failed: {e}")

    print("\n✅ Done. Run backtest.py next.")


if __name__ == "__main__":
    download_all()