# 📈 Millionaire Stocks — S&P 500 Alpaca Trading Agent

Automated S&P 500 stock scanner that runs on **GitHub Actions** every trading day at **9:35 AM ET**, powered by the **Alpaca Markets API**.

---

## 🚀 How It Works

1. Fetches the full S&P 500 ticker list (~503 stocks)
2. Downloads 220 days of daily OHLCV data per stock via Alpaca
3. Computes **RSI, MACD, SMA-50/200, Bollinger Bands, ATR**
4. Generates **BUY / SELL / HOLD** signals per stock
5. Logs alerts and (optionally) executes market orders via Alpaca

---

## 📁 Project Structure

```
├── src/
│   └── strategy.py              # Main trading agent
├── .github/
│   └── workflows/
│       └── trading_agent.yml    # GitHub Actions schedule
├── logs/                        # Signal CSVs and run logs (auto-generated)
├── requirements.txt
├── .env.example                 # Copy to .env for local runs
└── README.md
```

---

## ⚙️ Setup

### 1. Add GitHub Secrets

Go to **Settings → Secrets → Actions** and add:

| Secret | Value |
|--------|-------|
| `ALPACA_API_KEY` | Your Alpaca API key |
| `ALPACA_SECRET_KEY` | Your Alpaca secret key |
| `ALPACA_BASE_URL` | `https://paper-api.alpaca.markets` (paper) or `https://api.alpaca.markets` (live) |
| `ALPACA_ACCOUNT_NAME` | Your Alpaca account name/label |

### 2. Enable GitHub Actions

The workflow runs automatically. You can also trigger it manually from the **Actions** tab with options for dry run and order quantity.

---

## 📊 Signal Logic

### BUY (requires 3 of 5 conditions)
| Condition | Rule |
|-----------|------|
| RSI Recovery | RSI crosses above 30 (from oversold) |
| MACD Crossover | MACD diff turns positive |
| Above SMA-50 | Price > 50-day moving average |
| Golden Cross | SMA-50 > SMA-200 |
| Near BB Lower | Price ≤ Bollinger lower band × 1.015 |

### SELL (any 1 condition)
| Condition | Rule |
|-----------|------|
| RSI Overbought | RSI ≥ 70 |
| MACD Reversal | MACD diff turns negative |
| Death Cross | SMA-50 < SMA-200 |
| Near BB Upper | Price ≥ Bollinger upper band × 0.99 |
| Stop-Loss | Price drops ≥ 5% from entry |

---

## 🧪 Dry Run vs Live

- **`DRY_RUN=true`** (default): Logs alerts only, no real orders
- **`DRY_RUN=false`**: Executes real market orders via Alpaca

Toggle via the GitHub Actions manual trigger or by setting the secret.

---

## ⏰ Schedule

Runs at **9:35 AM ET**, Monday–Friday (5 minutes after market open).

Both EST and EDT cron entries are included in the workflow to handle daylight saving time.

---

> ⚠️ **Disclaimer:** For educational purposes. Always paper-trade first. Past performance does not guarantee future results.
