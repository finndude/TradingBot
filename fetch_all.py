"""
Multi-Pair Multi-Timeframe Data Fetcher
========================================
Fetches H1 and H4 candles for all target pairs from OANDA.
Saves each as data/PAIR_TIMEFRAME.csv

Pairs tested:
  - GBP/USD (our baseline)
  - EUR/USD (most liquid, tightest spreads)
  - AUD/JPY (clean Asian session ranges)
  - USD/JPY (strong JPY Asian behaviour)
  - GBP/JPY (volatile but structured)

Run: python data/fetch_all.py
"""

import os
import time
import requests
import pandas as pd
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

API_KEY     = os.getenv("OANDA_API_KEY")
ACCOUNT_ID  = os.getenv("OANDA_ACCOUNT_ID")
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

# ── Pairs and timeframes to fetch ──────────────────────────────────────────
PAIRS = [
    "GBP_USD",
    "EUR_USD",
    "AUD_JPY",
    "USD_JPY",
    "GBP_JPY",
]

TIMEFRAMES = ["H1", "H4"]

LOOKBACK_DAYS = 730  # 2 years


def fetch_candles(instrument: str, granularity: str, from_date: str, to_date: str) -> pd.DataFrame:
    all_candles = []
    current_from = datetime.fromisoformat(from_date)
    end_date     = datetime.fromisoformat(to_date)

    # Batch size per timeframe to stay under 5000 candle limit
    batch_days = 60 if granularity == "H1" else 240

    while current_from < end_date:
        current_to = min(current_from + timedelta(days=batch_days), end_date)

        url    = f"{BASE_URL}/v3/instruments/{instrument}/candles"
        params = {
            "granularity": granularity,
            "from": current_from.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "to":   current_to.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "price": "M",
        }

        r = requests.get(url, headers=HEADERS, params=params)

        if r.status_code != 200:
            print(f"    ⚠ Error {r.status_code}: {r.text[:100]}")
            break

        candles = r.json().get("candles", [])
        all_candles.extend(candles)
        current_from = current_to
        time.sleep(0.3)  # Respect rate limits

    if not all_candles:
        return pd.DataFrame()

    rows = []
    for c in all_candles:
        if c.get("complete", False):
            mid = c["mid"]
            rows.append({
                "datetime": pd.to_datetime(c["time"]),
                "Open":     float(mid["o"]),
                "High":     float(mid["h"]),
                "Low":      float(mid["l"]),
                "Close":    float(mid["c"]),
                "Volume":   int(c.get("volume", 0)),
            })

    df = pd.DataFrame(rows)
    df.set_index("datetime", inplace=True)
    df.index = df.index.tz_localize(None)
    df.sort_index(inplace=True)
    return df


def fetch_all():
    from_date = (datetime.utcnow() - timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    to_date   = datetime.utcnow().strftime("%Y-%m-%d")

    os.makedirs("data", exist_ok=True)

    results = []

    for pair in PAIRS:
        for tf in TIMEFRAMES:
            filename = f"data/{pair}_{tf}.csv"
            print(f"\nFetching {pair} {tf}...")

            df = fetch_candles(pair, tf, from_date, to_date)

            if df.empty:
                print(f"  ✗ No data returned for {pair} {tf}")
                continue

            df.to_csv(filename)
            print(f"  ✓ {len(df)} candles saved → {filename}")
            results.append((pair, tf, len(df), df.index[0].date(), df.index[-1].date()))

    print("\n" + "=" * 55)
    print("  FETCH COMPLETE")
    print("=" * 55)
    for pair, tf, count, start, end in results:
        print(f"  {pair:<10} {tf:<4} {count:>6} candles  {start} → {end}")
    print(f"\n  Ready to run: python backtest/run_all.py")


if __name__ == "__main__":
    fetch_all()