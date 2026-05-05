"""
Fetches historical GBP/USD OHLC data from OANDA API.
Uses M15 (15-minute) candles — ideal for Asian session breakout strategy.
"""

import os
import pandas as pd
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("OANDA_API_KEY")
ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID")
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

INSTRUMENT = "GBP_USD"
GRANULARITY = "H1"   # 1-hour candles


def fetch_candles(instrument: str, granularity: str, from_date: str, to_date: str) -> pd.DataFrame:
    """
    Fetch OHLCV candles from OANDA for a given date range.
    OANDA limits to 5000 candles per request — we batch automatically.
    """
    all_candles = []
    current_from = datetime.fromisoformat(from_date)
    end_date = datetime.fromisoformat(to_date)

    print(f"Fetching {instrument} {granularity} data from {from_date} to {to_date}...")

    while current_from < end_date:
        # Batch in 30-day chunks to stay under the 5000 candle limit
        current_to = min(current_from + timedelta(days=30), end_date)

        url = f"{BASE_URL}/v3/instruments/{instrument}/candles"
        params = {
            "granularity": granularity,
            "from": current_from.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "to": current_to.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "price": "M",  # Midpoint prices
        }

        response = requests.get(url, headers=HEADERS, params=params)

        if response.status_code != 200:
            print(f"Error fetching data: {response.status_code} - {response.text}")
            break

        candles = response.json().get("candles", [])
        all_candles.extend(candles)
        print(f"  Fetched {len(candles)} candles up to {current_to.date()}")
        current_from = current_to

    if not all_candles:
        print("No candles returned. Check your API key and date range.")
        return pd.DataFrame()

    # Parse into DataFrame
    rows = []
    for c in all_candles:
        if c.get("complete", False):
            mid = c["mid"]
            rows.append({
                "datetime": pd.to_datetime(c["time"]),
                "Open":  float(mid["o"]),
                "High":  float(mid["h"]),
                "Low":   float(mid["l"]),
                "Close": float(mid["c"]),
                "Volume": int(c.get("volume", 0)),
            })

    df = pd.DataFrame(rows)
    df.set_index("datetime", inplace=True)
    df.index = df.index.tz_localize(None)  # Remove timezone for backtesting compatibility
    df.sort_index(inplace=True)

    print(f"\nTotal candles fetched: {len(df)}")
    return df


def save_data(df: pd.DataFrame, path: str = "data/GBPUSD_M15.csv"):
    df.to_csv(path)
    print(f"Data saved to {path}")


if __name__ == "__main__":
    # Fetch 2 years of data for robust backtesting
    from_date = (datetime.utcnow() - timedelta(days=730)).strftime("%Y-%m-%d")
    to_date = datetime.utcnow().strftime("%Y-%m-%d")

    df = fetch_candles(INSTRUMENT, GRANULARITY, from_date, to_date)

    if not df.empty:
        save_data(df, "data/GBPUSD_H1.csv")
        print(f"\nSample data:")
        print(df.head(10))
    else:
        print("Failed to fetch data. Check your .env file.")