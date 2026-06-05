# 📈 Millionaire Stocks — S&P 500 Trading Agent

Automated S&P 500 stock scanner running every trading day at **9:35 AM ET**, powered by the **Alpaca Markets API**.

---

## 🚀 How It Works

1. Fetches the full S&P 500 ticker list (~503 stocks)
2. Downloads 220 days of daily OHLCV data per stock via Alpaca
3. Computes **RSI, MACD, SMA-50/200, Bollinger Bands, ATR**
4. Generates **BUY / SELL / HOLD** signals with 6 conditions
5. Logs alerts and (optionally) executes market orders via Alpaca

---

## 📊 Signal Logic

### BUY — requires 3 of 6 conditions
| Condition | Rule |
|-----------|------|
| RSI Recovery | RSI crosses above 35 (from oversold) |
| MACD Crossover | MACD diff turns positive |
| Above SMA-50 | Price > 50-day moving average |
| Golden Cross | SMA-50 > SMA-200 |
| Near BB Lower | Price ≤ Bollinger lower band × 1.015 |
| Volume Confirm | Today's volume ≥ 1.5× 20-day average |

### SELL — any 1 condition
| Condition | Rule |
|-----------|------|
| Take-Profit | Price ≥ entry × 1.10 (+10%) |
| Stop-Loss | Price ≤ entry × 0.95 (-5%) |
| RSI Overbought | RSI ≥ 72 |
| MACD Reversal | MACD diff turns negative |
| Death Cross | SMA-50 < SMA-200 |
| Near BB Upper | Price ≥ Bollinger upper band × 0.99 |

---

## 🎯 Strategy

- **Monthly target:** $2,000
- **Risk/Reward:** 2:1 (10% gain target vs 5% stop-loss)
- **Min volume:** 2,000,000 shares/day
- **Max positions:** 9

---

## 🧪 Dry Run vs Live

- **`DRY_RUN=true`** (default): Logs signals only, no real orders
- **`DRY_RUN=false`**: Executes real market orders via Alpaca

---

## ⏰ Schedule

Runs at **9:35 AM ET**, Monday–Friday (5 minutes after market open).  
Price updates every 15 minutes, 7 AM–9 PM CST.

---

> ⚠️ **Disclaimer:** For educational purposes only. Always paper-trade first. Past performance does not guarantee future results.
