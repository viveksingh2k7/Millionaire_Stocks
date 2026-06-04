# Alpaca Stock Broker — S&P 500 Trading Strategy

## Overview

This document outlines a systematic, automated trading strategy using the **Alpaca Markets API** to monitor, analyze, and trade S&P 500 stocks. The strategy combines multiple technical indicators and rule-based logic to generate **BUY** and **SELL** alerts in real time.

---

## 1. Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   Strategy Engine                       │
│                                                         │
│  S&P 500 Universe  →  Data Fetcher  →  Signal Engine   │
│                              ↓                          │
│                       Indicator Layer                   │
│                    (RSI, MACD, SMA, BB)                 │
│                              ↓                          │
│                     Alert Generator                     │
│                    (BUY / SELL / HOLD)                  │
│                              ↓                          │
│                    Alpaca Order Router                   │
└─────────────────────────────────────────────────────────┘
```

---

## 2. Environment Setup

### Install Dependencies

```bash
pip install alpaca-trade-api pandas numpy ta requests python-dotenv
```

### `.env` Configuration

```env
ALPACA_API_KEY=your_api_key_here
ALPACA_SECRET_KEY=your_secret_key_here
ALPACA_BASE_URL=https://paper-api.alpaca.markets   # Use paper trading for testing
```

---

## 3. Alpaca Client Initialization

```python
import os
import alpaca_trade_api as tradeapi
from dotenv import load_dotenv

load_dotenv()

api = tradeapi.REST(
    os.getenv("ALPACA_API_KEY"),
    os.getenv("ALPACA_SECRET_KEY"),
    os.getenv("ALPACA_BASE_URL"),
    api_version="v2"
)
```

---

## 4. S&P 500 Universe Loader

Fetches the current S&P 500 ticker list dynamically from Wikipedia.

```python
import pandas as pd

def get_sp500_tickers() -> list[str]:
    """Scrape the current S&P 500 components from Wikipedia."""
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    table = pd.read_html(url)[0]
    tickers = table["Symbol"].str.replace(".", "-", regex=False).tolist()
    return tickers

SP500 = get_sp500_tickers()
print(f"Loaded {len(SP500)} S&P 500 tickers.")
```

---

## 5. Historical Data Fetcher

```python
import pandas as pd

def fetch_bars(ticker: str, timeframe: str = "1Day", limit: int = 200) -> pd.DataFrame:
    """
    Fetch OHLCV bars from Alpaca for a given ticker.
    timeframe options: "1Min", "5Min", "15Min", "1Hour", "1Day"
    """
    bars = api.get_bars(
        ticker,
        tradeapi.rest.TimeFrame.Day,
        limit=limit,
        adjustment="raw"
    ).df

    bars.index = pd.to_datetime(bars.index)
    bars = bars[["open", "high", "low", "close", "volume"]]
    return bars
```

---

## 6. Technical Indicator Engine

All indicators are calculated using the `ta` library on OHLCV data.

```python
import ta

def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Compute RSI, MACD, SMA, Bollinger Bands on price data."""

    # Relative Strength Index (14-period)
    df["rsi"] = ta.momentum.RSIIndicator(df["close"], window=14).rsi()

    # MACD (12, 26, 9)
    macd_obj = ta.trend.MACD(df["close"], window_slow=26, window_fast=12, window_sign=9)
    df["macd"] = macd_obj.macd()
    df["macd_signal"] = macd_obj.macd_signal()
    df["macd_diff"] = macd_obj.macd_diff()

    # Simple Moving Averages
    df["sma_50"]  = ta.trend.SMAIndicator(df["close"], window=50).sma_indicator()
    df["sma_200"] = ta.trend.SMAIndicator(df["close"], window=200).sma_indicator()

    # Bollinger Bands (20-period, 2 std dev)
    bb = ta.volatility.BollingerBands(df["close"], window=20, window_dev=2)
    df["bb_upper"] = bb.bollinger_hband()
    df["bb_lower"] = bb.bollinger_lband()
    df["bb_mid"]   = bb.bollinger_mavg()

    # Average True Range (volatility filter)
    df["atr"] = ta.volatility.AverageTrueRange(
        df["high"], df["low"], df["close"], window=14
    ).average_true_range()

    return df
```

---

## 7. Signal Logic — BUY / SELL Rules

### 7.1 BUY Signal Conditions (ALL must be true)

| # | Condition | Indicator | Threshold |
|---|-----------|-----------|-----------|
| 1 | RSI oversold recovery | RSI | Crosses above 30 |
| 2 | MACD bullish crossover | MACD diff | Turns positive |
| 3 | Price above trend | Close vs SMA-50 | Close > SMA-50 |
| 4 | Golden cross present | SMA-50 vs SMA-200 | SMA-50 > SMA-200 |
| 5 | Price near lower band | Close vs BB lower | Close ≤ BB lower × 1.01 |

### 7.2 SELL Signal Conditions (ANY is sufficient)

| # | Condition | Indicator | Threshold |
|---|-----------|-----------|-----------|
| 1 | RSI overbought | RSI | RSI ≥ 70 |
| 2 | MACD bearish crossover | MACD diff | Turns negative |
| 3 | Death cross | SMA-50 vs SMA-200 | SMA-50 < SMA-200 |
| 4 | Price at upper band | Close vs BB upper | Close ≥ BB upper × 0.99 |
| 5 | Stop-loss triggered | Price vs entry | Drop ≥ 5% from entry |

```python
def generate_signal(df: pd.DataFrame, entry_price: float = None) -> str:
    """
    Returns 'BUY', 'SELL', or 'HOLD' based on latest bar indicators.
    Pass entry_price to enable stop-loss SELL logic.
    """
    latest = df.iloc[-1]
    prev   = df.iloc[-2]

    # --- BUY conditions ---
    rsi_recovery   = prev["rsi"] < 30 and latest["rsi"] >= 30
    macd_cross_up  = prev["macd_diff"] < 0 and latest["macd_diff"] >= 0
    above_sma50    = latest["close"] > latest["sma_50"]
    golden_cross   = latest["sma_50"] > latest["sma_200"]
    near_bb_lower  = latest["close"] <= latest["bb_lower"] * 1.01

    buy_score = sum([rsi_recovery, macd_cross_up, above_sma50, golden_cross, near_bb_lower])

    if buy_score >= 3:   # Require at least 3 of 5 conditions
        return "BUY"

    # --- SELL conditions ---
    rsi_overbought  = latest["rsi"] >= 70
    macd_cross_down = prev["macd_diff"] > 0 and latest["macd_diff"] <= 0
    death_cross     = latest["sma_50"] < latest["sma_200"]
    at_bb_upper     = latest["close"] >= latest["bb_upper"] * 0.99
    stop_loss       = (entry_price is not None) and (latest["close"] <= entry_price * 0.95)

    sell_triggered = any([rsi_overbought, macd_cross_down, death_cross, at_bb_upper, stop_loss])

    if sell_triggered:
        return "SELL"

    return "HOLD"
```

---

## 8. Alert System

Alerts are printed to the console and can be extended to email/SMS/Slack.

```python
from datetime import datetime

def send_alert(ticker: str, signal: str, price: float, details: dict):
    """Log and broadcast a trading alert."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    border = "=" * 60

    emoji = "🟢" if signal == "BUY" else "🔴" if signal == "SELL" else "⚪"

    print(f"\n{border}")
    print(f"  {emoji}  ALERT — {signal} SIGNAL  {emoji}")
    print(f"  Ticker    : {ticker}")
    print(f"  Price     : ${price:.2f}")
    print(f"  Timestamp : {timestamp}")
    print(f"  RSI       : {details.get('rsi', 'N/A'):.1f}")
    print(f"  MACD Diff : {details.get('macd_diff', 'N/A'):.4f}")
    print(f"  SMA-50    : ${details.get('sma_50', 0):.2f}")
    print(f"  SMA-200   : ${details.get('sma_200', 0):.2f}")
    print(f"{border}\n")

    # ── Optional: extend to Slack webhook ──────────────────────
    # import requests
    # requests.post(SLACK_WEBHOOK_URL, json={"text": f"{emoji} {signal} on {ticker} @ ${price:.2f}"})

    # ── Optional: extend to email via smtplib ──────────────────
    # send_email(subject=f"{signal} Alert: {ticker}", body=message)
```

---

## 9. Order Execution via Alpaca

```python
def place_order(ticker: str, signal: str, qty: int = 1):
    """
    Submit a market order to Alpaca.
    signal: 'BUY' → buy order | 'SELL' → sell/close order
    """
    if signal not in ("BUY", "SELL"):
        return

    side = "buy" if signal == "BUY" else "sell"

    try:
        order = api.submit_order(
            symbol=ticker,
            qty=qty,
            side=side,
            type="market",
            time_in_force="day"
        )
        print(f"✅ Order submitted: {side.upper()} {qty}x {ticker} | Order ID: {order.id}")
    except Exception as e:
        print(f"❌ Order failed for {ticker}: {e}")
```

---

## 10. Main Scanner Loop

Scans every S&P 500 stock and fires alerts when signals are detected.

```python
import time

def run_scanner(tickers: list[str], dry_run: bool = True):
    """
    Scan all S&P 500 tickers. Set dry_run=False to execute live orders.
    """
    print(f"🔍 Starting scan of {len(tickers)} S&P 500 stocks...\n")
    portfolio = {}  # ticker → entry price (for stop-loss tracking)

    for ticker in tickers:
        try:
            df = fetch_bars(ticker, limit=220)

            if len(df) < 210:
                continue  # Not enough history for SMA-200

            df = compute_indicators(df)
            latest = df.iloc[-1]

            entry_price = portfolio.get(ticker)
            signal = generate_signal(df, entry_price=entry_price)

            if signal in ("BUY", "SELL"):
                details = {
                    "rsi":       latest["rsi"],
                    "macd_diff": latest["macd_diff"],
                    "sma_50":    latest["sma_50"],
                    "sma_200":   latest["sma_200"],
                }
                send_alert(ticker, signal, latest["close"], details)

                if not dry_run:
                    place_order(ticker, signal, qty=1)

                if signal == "BUY":
                    portfolio[ticker] = latest["close"]
                elif signal == "SELL" and ticker in portfolio:
                    del portfolio[ticker]

            time.sleep(0.3)   # Rate limit: ~3 requests/sec

        except Exception as e:
            print(f"⚠️  Skipping {ticker}: {e}")

    print("✅ Scan complete.")
```

---

## 11. Scheduling — Run Daily at Market Open

```python
import schedule
import time

def job():
    tickers = get_sp500_tickers()
    run_scanner(tickers, dry_run=True)   # Set dry_run=False for live trading

# Run every weekday at 09:35 ET (5 minutes after market open)
schedule.every().monday.at("09:35").do(job)
schedule.every().tuesday.at("09:35").do(job)
schedule.every().wednesday.at("09:35").do(job)
schedule.every().thursday.at("09:35").do(job)
schedule.every().friday.at("09:35").do(job)

print("⏰ Scheduler started. Waiting for market open...")
while True:
    schedule.run_pending()
    time.sleep(30)
```

---

## 12. Risk Management Rules

| Parameter | Rule |
|-----------|------|
| **Stop-Loss** | Exit if position drops 5% below entry |
| **Max Position Size** | No single stock > 5% of portfolio |
| **Max Open Positions** | Limit to 20 concurrent positions |
| **Sector Concentration** | No single GICS sector > 30% of portfolio |
| **Avoid Earnings Week** | Do not open new positions 3 days before earnings |
| **Liquidity Filter** | Only trade stocks with avg volume > 500K/day |
| **Volatility Filter** | Skip stocks with ATR > 5% of price |

---

## 13. Backtesting Checklist

Before going live, validate this strategy with historical data:

- [ ] Run on 2 years of daily S&P 500 data
- [ ] Calculate Sharpe Ratio (target > 1.0)
- [ ] Calculate Maximum Drawdown (target < 20%)
- [ ] Win Rate analysis per signal type
- [ ] Compare against S&P 500 benchmark (SPY)
- [ ] Paper trade for 30 days via Alpaca Paper Trading account

---

## 14. Quick Start

```bash
# 1. Clone or create your project directory
mkdir alpaca-sp500-strategy && cd alpaca-sp500-strategy

# 2. Install dependencies
pip install alpaca-trade-api pandas numpy ta requests python-dotenv schedule

# 3. Set credentials
cp .env.example .env   # Fill in your Alpaca API keys

# 4. Run in dry-run mode (no real orders)
python strategy.py

# 5. When ready, enable live orders:
#    Set dry_run=False in run_scanner() call
```

---

## 15. Signal Summary Reference

```
RSI < 30 → Oversold         │  RSI > 70 → Overbought
MACD diff turns + → Bullish  │  MACD diff turns − → Bearish
SMA50 > SMA200 → Golden Cross│  SMA50 < SMA200 → Death Cross
Close ≤ BB Lower → Near support│  Close ≥ BB Upper → Near resistance
```

> **Disclaimer:** This strategy is for educational purposes. Always test thoroughly in paper trading before risking real capital. Past performance does not guarantee future results.
