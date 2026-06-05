# Millionaire Stocks — $2,000/Month Strategy
## Beat the S&P 500 with High-Volume Momentum + 10% Profit Targets

---

## 1. The Goal

| Target | Value |
|--------|-------|
| Monthly profit | **$2,000** |
| Annual target | **~24–30%** (vs S&P 500 ~12%) |
| Risk per trade | **-5% stop-loss** |
| Reward per trade | **+10% take-profit** |
| Risk/Reward ratio | **2:1** |
| Min volume | **2,000,000 shares/day** |
| Volume spike | **1.5× average** (institutional confirmation) |

---

## 2. Why This Beats Buy-and-Hold S&P 500

| Factor | S&P 500 (Index) | This Strategy |
|--------|----------------|---------------|
| Annual return | ~12% | ~24–30% |
| Takes profit | Never | At **+10%** — locked in |
| Cuts losses | Never | At **-5%** — protected |
| Buys selectively | All 503 stocks | Only **3+/6 condition** setups |
| Volume filter | No | **1.5× spike required** |
| Max drawdown | -50% (2008, 2020) | Capped at -5% per trade |

**The math at 60% win rate:**
```
6 wins  × +10% = +60% on traded capital
4 losses × -5% = -20% on traded capital
Net per cycle  = +40%  ← vs S&P 500's +1% per month
```

---

## 3. Capital Required for $2,000/Month

| Portfolio Size | Monthly Return Needed | Monthly Profit |
|---------------|-----------------------|----------------|
| $20,000 | 10% | $2,000 — too aggressive |
| $40,000 | 5% | $2,000 — aggressive |
| **$80,000** | **2.5%** | **$2,000** ← **Recommended** |
| $100,000 | 2% | $2,000 — conservative |

**Recommended: $80,000 across 9 positions (~$8,900 each)**
- Each +10% win on a position = **~$890 profit**
- Need just **3 winning trades/month** to hit $2,000+ target ✅

---

## 4. The 9 High-Volume Momentum Stocks

Selected for: avg daily volume >15M, AI/growth theme, proven 10%+ swing potential.

| # | Ticker | Name | Live Price | Avg Cost | Shares | Sector | Avg Daily Vol |
|---|--------|------|-----------|----------|--------|--------|--------------|
| 1 | **NVDA** | NVIDIA | $218.66 | $218.66 | 100 | AI / Chips | 50M+ |
| 2 | **AAPL** | Apple | $311.23 | $311.23 | 100 | Tech / AI | 60M+ |
| 3 | **AMD** | AMD | $523.20 | $523.20 | 100 | AI / Chips | 60M+ |
| 4 | **TSLA** | Tesla | $418.45 | $418.45 | 100 | EV / Robotics | 100M+ |
| 5 | **AMZN** | Amazon | $253.79 | $253.79 | 100 | Cloud / AI | 40M+ |
| 6 | **META** | Meta | $627.57 | $627.57 | 100 | AI / Social | 15M+ |
| 7 | **PLTR** | Palantir | $141.70 | $24.80 | 100 | AI / Gov | 100M+ |
| 8 | **MOH** | Molina | $192.81 | $299.40 | 100 | Healthcare | 1M+ |
| 9 | **WISE** | Wise plc | LSE | £9.85 | 100 | Fintech | LSE |

---

## 5. Entry Rules (BUY Signal)

A stock must satisfy **3 or more** of these **6 conditions**:

| # | Condition | Formula | What It Means |
|---|-----------|---------|---------------|
| 1 | RSI Recovery | RSI crosses above 35 | Oversold → buyers returning |
| 2 | MACD Cross Up | MACD diff turns +ve | Momentum turning bullish |
| 3 | Above SMA-50 | Close > SMA-50 | Medium-term uptrend intact |
| 4 | Golden Cross | SMA-50 > SMA-200 | Long-term uptrend confirmed |
| 5 | Near BB Lower | Close ≤ BB_lower × 1.015 | Price near support |
| 6 | **Volume Confirm** ⭐ | Today vol ≥ 1.5× 20-day avg | **Institutions are buying now** |

> **Volume Confirm is the most important filter.** Without big-money volume, even
> technically perfect setups frequently fail. When institutions buy, price follows.

---

## 6. Exit Rules

### ✅ TAKE-PROFIT — +10% from entry (NEW)
```
Sell when:  current_price >= entry_price × 1.10
Example:    Buy NVDA at $200 → Sell at $220 = +$20/share × 100 = $2,000 profit
```

### 🛑 STOP-LOSS — -5% from entry
```
Sell when:  current_price <= entry_price × 0.95
Example:    Buy NVDA at $200 → Sell at $190 = -$10/share × 100 = -$1,000 loss
```

### Additional SELL triggers
| Trigger | Condition | Signal |
|---------|-----------|--------|
| RSI Overbought | RSI ≥ 72 | Price likely to reverse down |
| MACD Cross Down | MACD diff turns negative | Momentum turning bearish |
| Death Cross | SMA-50 < SMA-200 | Long-term trend broken |
| At BB Upper | Close ≥ BB_upper × 0.99 | Price at resistance |

---

## 7. Monthly P&L Model ($80K Portfolio)

### Realistic Month (60% win rate, 5 trades)
| Trade | Stock | Entry | Exit | Result | P&L |
|-------|-------|-------|------|--------|-----|
| 1 | NVDA | $210 | $231 (+10%) | WIN ✅ | +$2,100 |
| 2 | PLTR | $138 | $152 (+10%) | WIN ✅ | +$1,380 |
| 3 | TSLA | $415 | $394 (-5%) | LOSS ❌ | -$1,050 |
| 4 | AMD | $520 | $572 (+10%) | WIN ✅ | +$2,080 |
| 5 | AAPL | $308 | $293 (-5%) | LOSS ❌ | -$750 |
| | | | | **Net** | **+$3,760** ✅ |

> Even with 2 losses out of 5 trades, the 2:1 R/R ratio delivers $3,760 — well above the $2,000 target.

---

## 8. Workflow Configuration

Add these to `workflows/trading_agent.yml`:

```yaml
PROFIT_TARGET_PCT: "0.10"   # 10% take-profit
STOP_LOSS_PCT:     "0.05"   # 5% stop-loss
MIN_VOLUME:        "2000000" # 2M minimum avg daily volume
HIGH_VOLUME_MULT:  "1.5"    # volume must be 1.5× the 20-day average
BUY_THRESHOLD:     "3"      # need 3 of 6 conditions to trigger BUY
MAX_POSITIONS:     "9"      # 9 high-conviction positions
ORDER_QTY:         "1"      # adjust per position sizing
```

---

## 9. Risk Management Rules

| Rule | Setting | Reason |
|------|---------|--------|
| Max positions | 9 | Concentrated but diversified |
| Max per position | ~$9,000 (11% of portfolio) | Limits single-stock risk |
| Stop-loss | -5% | Never let a small loss become a big one |
| Take-profit | +10% | Lock in gains — markets can reverse fast |
| Min avg volume | 2,000,000/day | Ensures institutional liquidity |
| Volume spike | 1.5× avg | Only buy when big money is moving in |
| RSI buy zone | < 35 | Buy cheap, sell expensive |
| RSI sell zone | > 72 | Exit before the crowd does |

---

## 10. S&P 500 Comparison

```
Year 1 simulation ($80,000 starting capital):

S&P 500 buy-and-hold:    $80,000 × 12%  = $89,600  (gain: $9,600)
This strategy (target):  $80,000 × 30%  = $104,000 (gain: $24,000)
This strategy (active):  $80,000 × 40%  = $112,000 (gain: $32,000)

Monthly passive income:
  S&P 500:        $800/month
  This strategy:  $2,000/month ← 2.5× the index ✅
```

---

## 11. Quick-Start Checklist

- [ ] Fund Alpaca account with $80,000 (paper first, then live)
- [ ] Set GitHub Secrets: `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `ALPACA_BASE_URL`
- [ ] Set `DRY_RUN=false` when ready for live trading
- [ ] Confirm `PROFIT_TARGET_PCT=0.10` and `STOP_LOSS_PCT=0.05` in workflow
- [ ] Monitor dashboard: https://viveksingh2k7.github.io/Millionaire_Stocks/
- [ ] Review Portfolio P&L weekly via **My Portfolio** tab
- [ ] Never override the stop-loss — discipline is the edge

---

*⚠️ Not financial advice. All trading involves risk of loss.
Past performance does not guarantee future results.*
