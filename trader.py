"""
Live Trading Engine — OANDA Paper Account
==========================================
Connects to OANDA practice API and executes the Asian Session Breakout
strategy in real-time using the same logic as the backtest.

Run this script to start live paper trading.
It checks for signals every 15 minutes aligned to candle close.
"""

import os
import time
import logging
import requests
import pandas as pd
from datetime import datetime, timezone
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

INSTRUMENT         = "GBP_USD"
UNITS_BASE         = 1000       # 1 micro lot = 1000 units
RISK_PER_TRADE_GBP = 5.0        # £5 per trade (1% of £500)
RISK_REWARD        = 2.0
ASIAN_START_HOUR   = 0
ASIAN_END_HOUR     = 7
CUTOFF_HOUR        = 12
SPREAD_BUFFER      = 0.0002     # 2 pip buffer on entries

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("live/trading.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)


# ── OANDA API helpers ──────────────────────────────────────────────────────

def get_candles(granularity: str = "M15", count: int = 100) -> pd.DataFrame:
    """Fetch the last N candles from OANDA."""
    url = f"{BASE_URL}/v3/instruments/{INSTRUMENT}/candles"
    params = {"granularity": granularity, "count": count, "price": "M"}
    r = requests.get(url, headers=HEADERS, params=params)
    r.raise_for_status()

    rows = []
    for c in r.json().get("candles", []):
        if c.get("complete"):
            mid = c["mid"]
            rows.append({
                "datetime": pd.to_datetime(c["time"]).replace(tzinfo=None),
                "Open":  float(mid["o"]),
                "High":  float(mid["h"]),
                "Low":   float(mid["l"]),
                "Close": float(mid["c"]),
            })

    df = pd.DataFrame(rows).set_index("datetime")
    return df


def get_current_price() -> tuple[float, float]:
    """Get current bid/ask price."""
    url = f"{BASE_URL}/v3/accounts/{ACCOUNT_ID}/pricing"
    params = {"instruments": INSTRUMENT}
    r = requests.get(url, headers=HEADERS, params=params)
    r.raise_for_status()
    prices = r.json()["prices"][0]
    bid = float(prices["bids"][0]["price"])
    ask = float(prices["asks"][0]["price"])
    return bid, ask


def get_open_trades() -> list:
    """Return list of open trades."""
    url = f"{BASE_URL}/v3/accounts/{ACCOUNT_ID}/openTrades"
    r = requests.get(url, headers=HEADERS)
    r.raise_for_status()
    return r.json().get("trades", [])


def get_account_balance() -> float:
    """Get current account balance."""
    url = f"{BASE_URL}/v3/accounts/{ACCOUNT_ID}/summary"
    r = requests.get(url, headers=HEADERS)
    r.raise_for_status()
    return float(r.json()["account"]["balance"])


def place_order(units: int, sl: float, tp: float) -> dict:
    """
    Place a market order.
    Positive units = BUY, negative units = SELL.
    """
    url = f"{BASE_URL}/v3/accounts/{ACCOUNT_ID}/orders"
    payload = {
        "order": {
            "type": "MARKET",
            "instrument": INSTRUMENT,
            "units": str(units),
            "stopLossOnFill": {"price": f"{sl:.5f}"},
            "takeProfitOnFill": {"price": f"{tp:.5f}"},
            "timeInForce": "FOK",  # Fill or Kill
        }
    }
    r = requests.post(url, headers=HEADERS, json=payload)
    r.raise_for_status()
    return r.json()


def close_all_trades():
    """Close all open trades."""
    trades = get_open_trades()
    for trade in trades:
        trade_id = trade["id"]
        url = f"{BASE_URL}/v3/accounts/{ACCOUNT_ID}/trades/{trade_id}/close"
        r = requests.put(url, headers=HEADERS)
        if r.status_code == 200:
            log.info(f"Closed trade {trade_id}")
        else:
            log.warning(f"Failed to close trade {trade_id}: {r.text}")


def calculate_units(risk_gbp: float, risk_price: float) -> int:
    """
    Calculate position size in units based on £ risk.
    GBP/USD: 1 pip = $0.0001. At ~1.27 exchange rate, 1 unit = ~$1.27
    We size to keep risk at £5 regardless of stop distance.
    """
    if risk_price <= 0:
        return UNITS_BASE
    # Rough unit calculation: units = (risk_gbp / risk_price)
    units = int(risk_gbp / risk_price)
    units = max(1000, min(units, 50000))  # Cap between 1k and 50k units
    return units


# ── Strategy state ─────────────────────────────────────────────────────────

class SessionState:
    def __init__(self):
        self.reset()

    def reset(self):
        self.asian_high   = None
        self.asian_low    = None
        self.traded_today = False
        self.date         = None
        log.info("Session state reset for new day")


state = SessionState()


# ── Main signal function ───────────────────────────────────────────────────

def run_signal():
    """
    Called every 15 minutes. Checks for Asian breakout signal and executes.
    """
    now  = datetime.now(timezone.utc)
    hour = now.hour

    # Reset state at midnight
    if state.date != now.date():
        state.reset()
        state.date = now.date()

    log.info(f"Tick — {now.strftime('%Y-%m-%d %H:%M')} UTC | Hour: {hour}")

    try:
        df = get_candles(granularity="M15", count=50)
    except Exception as e:
        log.error(f"Failed to fetch candles: {e}")
        return

    # ── Build Asian range ──────────────────────────────────────────────────
    if ASIAN_START_HOUR <= hour < ASIAN_END_HOUR:
        asian_candles = df[df.index.hour < ASIAN_END_HOUR]
        if not asian_candles.empty:
            state.asian_high = asian_candles["High"].max()
            state.asian_low  = asian_candles["Low"].min()
            log.info(f"Asian range building → High: {state.asian_high:.5f} | Low: {state.asian_low:.5f}")
        return

    # ── Guard conditions ───────────────────────────────────────────────────
    if state.asian_high is None or state.asian_low is None:
        log.info("No Asian range established yet — skipping")
        return

    if state.traded_today:
        log.info("Already traded today — skipping")
        return

    if hour >= CUTOFF_HOUR:
        # Force close any open trades at cutoff
        open_trades = get_open_trades()
        if open_trades:
            log.info("Cutoff reached — closing all trades")
            close_all_trades()
        return

    # Check no open trades
    if get_open_trades():
        log.info("Open trade exists — skipping signal check")
        return

    range_size = state.asian_high - state.asian_low
    if range_size < 0.0010:
        log.info(f"Range too tight ({range_size:.5f}) — skipping")
        return

    try:
        bid, ask = get_current_price()
    except Exception as e:
        log.error(f"Failed to get price: {e}")
        return

    log.info(f"Price — Bid: {bid:.5f} Ask: {ask:.5f} | Range: {state.asian_low:.5f} - {state.asian_high:.5f}")

    # ── LONG signal ────────────────────────────────────────────────────────
    if ask > state.asian_high + SPREAD_BUFFER:
        entry = ask
        sl    = state.asian_high - (range_size * 0.25)
        risk  = entry - sl
        tp    = entry + (risk * RISK_REWARD)
        units = calculate_units(RISK_PER_TRADE_GBP, risk)

        log.info(f"🟢 LONG SIGNAL | Entry: {entry:.5f} | SL: {sl:.5f} | TP: {tp:.5f} | Units: {units}")
        try:
            result = place_order(units, sl, tp)
            log.info(f"Order placed: {result}")
            state.traded_today = True
        except Exception as e:
            log.error(f"Order failed: {e}")

    # ── SHORT signal ───────────────────────────────────────────────────────
    elif bid < state.asian_low - SPREAD_BUFFER:
        entry = bid
        sl    = state.asian_low + (range_size * 0.25)
        risk  = sl - entry
        tp    = entry - (risk * RISK_REWARD)
        units = calculate_units(RISK_PER_TRADE_GBP, risk)

        log.info(f"🔴 SHORT SIGNAL | Entry: {entry:.5f} | SL: {sl:.5f} | TP: {tp:.5f} | Units: {units}")
        try:
            result = place_order(-units, sl, tp)
            log.info(f"Order placed: {result}")
            state.traded_today = True
        except Exception as e:
            log.error(f"Order failed: {e}")

    else:
        log.info("No breakout signal — waiting")


# ── Runner ─────────────────────────────────────────────────────────────────

def run_live():
    log.info("=" * 50)
    log.info("  Asian Breakout Bot — OANDA Practice Account")
    log.info(f"  Instrument : {INSTRUMENT}")
    log.info(f"  Risk/Trade : £{RISK_PER_TRADE_GBP}")
    log.info(f"  R:R Ratio  : {RISK_REWARD}:1")
    log.info("=" * 50)

    balance = get_account_balance()
    log.info(f"Account balance: £{balance:,.2f}")

    while True:
        try:
            run_signal()
        except Exception as e:
            log.error(f"Unexpected error in signal loop: {e}")

        # Wait until next 15-minute candle close
        now     = datetime.now(timezone.utc)
        minutes = now.minute % 15
        wait    = (15 - minutes) * 60 - now.second
        log.info(f"Next check in {wait}s")
        time.sleep(wait)


if __name__ == "__main__":
    run_live()