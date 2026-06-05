"""
Millionaire Stocks — S&P 500 Alpaca Trading Strategy Agent
============================================================
Scans all S&P 500 stocks using RSI, MACD, SMA, and Bollinger Bands.
Fires BUY / SELL alerts and executes orders via Alpaca Markets API.

Schedule: Runs at 09:35 ET on every market trading day (via GitHub Actions).
"""

import os
import sys
import time
import json
import logging
from datetime import datetime, date, timedelta

import pandas as pd
import numpy as np
import requests
import alpaca_trade_api as tradeapi
from alpaca_trade_api.rest import TimeFrame
import ta

# ─────────────────────────────────────────────
# Ensure logs directory exists before logging
# ─────────────────────────────────────────────
os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/trading_agent.log", mode="a"),
    ],
)
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Signal threshold constants
# ─────────────────────────────────────────────
BB_LOWER_BUFFER  = 1.015   # close <= bb_lower * this → near lower band
BB_UPPER_BUFFER  = 0.99    # close >= bb_upper * this → near upper band
PROFIT_TARGET_PCT = 0.10   # sell when position is +10% from entry (take-profit)


# ─────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────
class Config:
    API_KEY        = os.environ.get("ALPACA_API_KEY")    or sys.exit("ERROR: ALPACA_API_KEY is not set")
    SECRET_KEY     = os.environ.get("ALPACA_SECRET_KEY") or sys.exit("ERROR: ALPACA_SECRET_KEY is not set")
    BASE_URL       = os.environ.get("ALPACA_BASE_URL")   or sys.exit("ERROR: ALPACA_BASE_URL is not set")
    ACCOUNT_NAME   = os.environ.get("ALPACA_ACCOUNT_NAME", "default")

    DRY_RUN            = os.environ.get("DRY_RUN", "true").lower() == "true"
    ORDER_QTY          = int(os.environ.get("ORDER_QTY", "1"))               # shares per trade
    STOP_LOSS_PCT      = float(os.environ.get("STOP_LOSS_PCT", "0.05"))      # 5%  stop-loss
    PROFIT_TARGET_PCT  = float(os.environ.get("PROFIT_TARGET_PCT", "0.10"))  # 10% take-profit
    BUY_THRESHOLD      = int(os.environ.get("BUY_THRESHOLD", "3"))           # min conditions for BUY
    MIN_VOLUME         = int(os.environ.get("MIN_VOLUME", "2000000"))         # liquidity filter (raised to 2M)
    HIGH_VOLUME_MULT   = float(os.environ.get("HIGH_VOLUME_MULT", "1.5"))     # volume spike multiplier
    MAX_POSITIONS  = int(os.environ.get("MAX_POSITIONS", "20"))
    RATE_LIMIT_SEC = float(os.environ.get("RATE_LIMIT_SEC", "0.35"))


# ─────────────────────────────────────────────
# Alpaca Client
# ─────────────────────────────────────────────
def init_client() -> tradeapi.REST:
    client = tradeapi.REST(
        Config.API_KEY,
        Config.SECRET_KEY,
        Config.BASE_URL,
        api_version="v2",
    )
    account = client.get_account()
    log.info(f"✅ Connected to Alpaca | Account: {Config.ACCOUNT_NAME} | "
             f"Equity: ${float(account.equity):,.2f} | "
             f"Buying Power: ${float(account.buying_power):,.2f}")
    return client


# ─────────────────────────────────────────────
# Market Hours Check
# ─────────────────────────────────────────────
def is_market_open(api: tradeapi.REST) -> bool:
    clock = api.get_clock()
    if not clock.is_open:
        log.warning("⚠️  Market is currently CLOSED. Exiting.")
        return False
    log.info(f"🕐 Market is OPEN | Next close: {clock.next_close}")
    return True


# ─────────────────────────────────────────────
# S&P 500 Universe
# ─────────────────────────────────────────────
def get_sp500_tickers() -> list:
    """Fetch current S&P 500 components from Wikipedia."""
    try:
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        html = requests.get(url, timeout=15).text
        tables = pd.read_html(html)
        tickers = tables[0]["Symbol"].str.replace(".", "-", regex=False).tolist()
        log.info(f"📋 Loaded {len(tickers)} S&P 500 tickers from Wikipedia.")
        return tickers
    except Exception as e:
        log.error(f"❌ Failed to fetch S&P 500 list: {e}")
        # Fallback: small representative subset
        return [
            "AAPL","MSFT","AMZN","NVDA","GOOGL","META","BRK-B","LLY",
            "AVGO","TSLA","JPM","V","UNH","XOM","MA","JNJ","HD","PG",
            "MRK","COST","ABBV","BAC","CRM","CVX","NFLX","WMT","AMD",
            "ACN","PEP","LIN","TMO","ADBE","ABT","DHR","KO","MCD","CSCO",
            "TXN","NEE","WFC","ORCL","PM","INTU","AMGN","RTX","IBM","CAT",
            "SPGI","HON","UNP","GS","LOW","ISRG","VRTX","ELV","AMAT","SYK",
        ]


# ─────────────────────────────────────────────
# Data Fetcher
# ─────────────────────────────────────────────
def fetch_bars(api: tradeapi.REST, ticker: str, limit: int = 220) -> pd.DataFrame | None:
    """Fetch daily OHLCV bars from Alpaca."""
    try:
        bars = api.get_bars(
            ticker,
            TimeFrame.Day,
            limit=limit,
            adjustment="split",
        ).df
        bars.index = pd.to_datetime(bars.index)
        bars = bars[["open", "high", "low", "close", "volume"]].copy()
        return bars
    except Exception as e:
        log.debug(f"fetch_bars({ticker}): {e}")
        return None


# ─────────────────────────────────────────────
# Indicator Engine
# ─────────────────────────────────────────────
def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Compute RSI, MACD, SMA-50/200, Bollinger Bands, ATR."""
    df = df.copy()

    # RSI (14)
    df["rsi"] = ta.momentum.RSIIndicator(df["close"], window=14).rsi()

    # MACD (12, 26, 9)
    macd = ta.trend.MACD(df["close"], window_slow=26, window_fast=12, window_sign=9)
    df["macd"]        = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    df["macd_diff"]   = macd.macd_diff()

    # SMAs
    df["sma_50"]  = ta.trend.SMAIndicator(df["close"], window=50).sma_indicator()
    df["sma_200"] = ta.trend.SMAIndicator(df["close"], window=200).sma_indicator()

    # Bollinger Bands (20, 2σ)
    bb = ta.volatility.BollingerBands(df["close"], window=20, window_dev=2)
    df["bb_upper"] = bb.bollinger_hband()
    df["bb_lower"] = bb.bollinger_lband()
    df["bb_mid"]   = bb.bollinger_mavg()

    # ATR (14) — volatility filter
    df["atr"] = ta.volatility.AverageTrueRange(
        df["high"], df["low"], df["close"], window=14
    ).average_true_range()

    return df


# ─────────────────────────────────────────────
# Signal Generator
# ─────────────────────────────────────────────
def generate_signal(df: pd.DataFrame, entry_price: float = None) -> tuple[str, dict]:
    """
    Returns (signal, reasons_dict).
    signal: 'BUY' | 'SELL' | 'HOLD'
    """
    latest = df.iloc[-1]
    prev   = df.iloc[-2]

    # ── Liquidity & volume filters ────────────────────────────
    avg_vol      = df["volume"].tail(20).mean()
    today_vol    = latest["volume"]
    vol_spike    = today_vol / avg_vol if avg_vol > 0 else 0
    atr_pct      = latest["atr"] / latest["close"] if latest["close"] > 0 else 1.0
    is_high_vol  = avg_vol >= Config.MIN_VOLUME and vol_spike >= Config.HIGH_VOLUME_MULT

    if avg_vol < Config.MIN_VOLUME:
        return "HOLD", {"reason": "low_volume"}
    if atr_pct > 0.08:                        # relaxed to 8% to allow momentum stocks
        return "HOLD", {"reason": "high_volatility"}

    # ── BUY conditions ────────────────────────────────────────
    rsi_recovery   = (prev["rsi"] < 35) and (latest["rsi"] >= 35)   # slightly wider RSI window
    macd_cross_up  = (prev["macd_diff"] < 0) and (latest["macd_diff"] >= 0)
    above_sma50    = latest["close"] > latest["sma_50"]
    golden_cross   = latest["sma_50"] > latest["sma_200"]
    near_bb_lower  = latest["close"] <= latest["bb_lower"] * BB_LOWER_BUFFER
    volume_confirm = is_high_vol                                      # ← NEW: volume spike on entry

    buy_conditions = {
        "rsi_recovery":   rsi_recovery,
        "macd_cross_up":  macd_cross_up,
        "above_sma50":    above_sma50,
        "golden_cross":   golden_cross,
        "near_bb_lower":  near_bb_lower,
        "volume_confirm": volume_confirm,                             # ← 6th condition
    }
    buy_score = sum(buy_conditions.values())

    # ── SELL conditions ───────────────────────────────────────
    rsi_overbought  = latest["rsi"] >= 72
    macd_cross_down = (prev["macd_diff"] > 0) and (latest["macd_diff"] <= 0)
    death_cross     = latest["sma_50"] < latest["sma_200"]
    at_bb_upper     = latest["close"] >= latest["bb_upper"] * BB_UPPER_BUFFER
    stop_loss       = (entry_price is not None) and \
                      (latest["close"] <= entry_price * (1 - Config.STOP_LOSS_PCT))
    # ── TAKE-PROFIT: sell when +10% from entry ────────────────
    take_profit     = (entry_price is not None) and \
                      (latest["close"] >= entry_price * (1 + Config.PROFIT_TARGET_PCT))

    sell_conditions = {
        "rsi_overbought":  rsi_overbought,
        "macd_cross_down": macd_cross_down,
        "death_cross":     death_cross,
        "at_bb_upper":     at_bb_upper,
        "stop_loss":       stop_loss,
        "take_profit":     take_profit,                               # ← NEW: 10% target
    }

    # ── Unrealised P&L % if we hold this position ─────────────
    unrealised_pct = None
    if entry_price and entry_price > 0:
        unrealised_pct = round((float(latest["close"]) - entry_price) / entry_price * 100, 2)

    details = {
        "rsi":             round(float(latest["rsi"]), 2),
        "macd_diff":       round(float(latest["macd_diff"]), 5),
        "sma_50":          round(float(latest["sma_50"]), 2),
        "sma_200":         round(float(latest["sma_200"]), 2),
        "bb_upper":        round(float(latest["bb_upper"]), 2),
        "bb_lower":        round(float(latest["bb_lower"]), 2),
        "close":           round(float(latest["close"]), 2),
        "atr_pct":         round(atr_pct * 100, 2),
        "vol_spike":       round(vol_spike, 2),
        "avg_volume":      round(avg_vol, 0),
        "is_high_vol":     is_high_vol,
        "unrealised_pct":  unrealised_pct,
        "buy_score":       buy_score,
        "buy_conditions":  buy_conditions,
        "sell_conditions": sell_conditions,
    }

    if buy_score >= Config.BUY_THRESHOLD:
        return "BUY", details

    if any(sell_conditions.values()):
        return "SELL", details

    return "HOLD", details


# ─────────────────────────────────────────────
# Alert Printer
# ─────────────────────────────────────────────
def print_alert(ticker: str, signal: str, details: dict):
    emoji = "🟢" if signal == "BUY" else "🔴"
    border = "─" * 58
    triggered_buy  = [k for k, v in details.get("buy_conditions", {}).items() if v]
    triggered_sell = [k for k, v in details.get("sell_conditions", {}).items() if v]

    log.info(f"\n╔{border}╗")
    log.info(f"║  {emoji}  {signal} SIGNAL — {ticker:<10}                       ║")
    log.info(f"╠{border}╣")
    log.info(f"║  Price     : ${details['close']:<10.2f}  ATR%: {details['atr_pct']:.2f}%            ║")
    log.info(f"║  RSI       : {details['rsi']:<10.2f}  Buy Score: {details['buy_score']}/5          ║")
    log.info(f"║  MACD Diff : {details['macd_diff']:<15.5f}                       ║")
    log.info(f"║  SMA-50    : ${details['sma_50']:<10.2f}  SMA-200: ${details['sma_200']:.2f}       ║")
    log.info(f"║  BB Upper  : ${details['bb_upper']:<10.2f}  BB Lower: ${details['bb_lower']:.2f}   ║")
    if triggered_buy:
        log.info(f"║  ✅ BUY triggers : {', '.join(triggered_buy):<36}║")
    if triggered_sell:
        log.info(f"║  🚨 SELL triggers: {', '.join(triggered_sell):<36}║")
    log.info(f"╚{border}╝\n")


# ─────────────────────────────────────────────
# Open Positions Tracker
# ─────────────────────────────────────────────
def get_open_positions(api: tradeapi.REST) -> dict:
    """Returns {ticker: entry_price} for all open positions."""
    try:
        positions = api.list_positions()
        return {p.symbol: float(p.avg_entry_price) for p in positions}
    except Exception as e:
        log.warning(f"Could not fetch positions: {e}")
        return {}


# ─────────────────────────────────────────────
# Trade Log
# ─────────────────────────────────────────────
TRADE_LOG_PATH = "docs/trade_log.json"

def _load_trade_log() -> dict:
    """Load existing trade log or return a fresh one."""
    if os.path.exists(TRADE_LOG_PATH):
        with open(TRADE_LOG_PATH) as f:
            return json.load(f)
    return {
        "version": "1.0",
        "strategy": "10% Take-Profit | 5% Stop-Loss | High-Volume Momentum",
        "monthly_target": 2000,
        "trades": [],
        "weekly_reports": [],
    }


def _save_trade_log(data: dict):
    os.makedirs("docs", exist_ok=True)
    with open(TRADE_LOG_PATH, "w") as f:
        json.dump(data, f, indent=2)


def _log_trade(ticker: str, signal: str, qty: int, price: float,
               details: dict, entry_price: float | None):
    """Append a trade entry to the trade log and update weekly report."""
    tl   = _load_trade_log()
    now  = datetime.utcnow()
    side = signal  # "BUY" or "SELL"

    # Generate sequential trade ID
    existing_ids = [t.get("id", "TRD-000") for t in tl["trades"]]
    max_num = max((int(i.split("-")[1]) for i in existing_ids if "-" in i), default=0)
    trade_id = f"TRD-{max_num + 1:03d}"

    # Calculate P&L for SELL orders
    realised_pnl = None
    realised_pct = None
    outcome      = None
    if side == "SELL" and entry_price:
        realised_pnl = round((price - entry_price) * qty, 2)
        realised_pct = round((price - entry_price) / entry_price * 100, 2)
        outcome = "WIN" if realised_pnl > 0 else "LOSS"

    sell_triggers = [k for k, v in details.get("sell_conditions", {}).items() if v]
    buy_triggers  = [k for k, v in details.get("buy_conditions",  {}).items() if v]

    entry = {
        "id":               trade_id,
        "date":             str(date.today()),
        "time":             now.strftime("%H:%M:%S"),
        "ticker":           ticker,
        "action":           side,
        "shares":           qty,
        "price":            round(price, 4),
        "total":            round(price * qty, 2),
        "status":           "OPEN" if side == "BUY" else "CLOSED",
        "triggers":         buy_triggers if side == "BUY" else sell_triggers,
        "buy_score":        details.get("buy_score", 0),
        "rsi":              details.get("rsi", 0),
        "vol_spike":        details.get("vol_spike", 0),
        "stop_price":       round(price * (1 - Config.STOP_LOSS_PCT), 2) if side == "BUY" else None,
        "target_price":     round(price * (1 + Config.PROFIT_TARGET_PCT), 2) if side == "BUY" else None,
        "entry_price":      entry_price if side == "SELL" else None,
        "realised_pnl":     realised_pnl,
        "realised_pnl_pct": realised_pct,
        "outcome":          outcome,
        "dry_run":          Config.DRY_RUN,
        "notes":            ", ".join(sell_triggers) if side == "SELL" else "",
    }

    # Mark the matching open BUY as CLOSED
    if side == "SELL":
        for t in tl["trades"]:
            if t["ticker"] == ticker and t["action"] == "BUY" and t["status"] == "OPEN":
                t["status"]           = "CLOSED"
                t["close_price"]      = round(price, 4)
                t["close_date"]       = str(date.today())
                t["realised_pnl"]     = realised_pnl
                t["realised_pnl_pct"] = realised_pct
                t["outcome"]          = outcome
                break

    tl["trades"].append(entry)
    _update_weekly_report(tl)
    _save_trade_log(tl)

    log.info(f"📓 Trade logged: {trade_id} | {side} {qty}x {ticker} @ ${price:.2f}"
             + (f" | P&L: ${realised_pnl:+.2f} ({realised_pct:+.1f}%)" if realised_pnl is not None else ""))


def _update_weekly_report(tl: dict):
    """Regenerate or upsert the current week's report."""
    today     = date.today()
    week_start = today - timedelta(days=today.weekday())     # Monday
    week_end   = week_start + timedelta(days=6)              # Sunday
    week_key   = f"{today.year}-W{today.isocalendar()[1]:02d}"

    week_trades = [
        t for t in tl["trades"]
        if week_start.isoformat() <= t["date"] <= week_end.isoformat()
    ]

    buys    = [t for t in week_trades if t["action"] == "BUY"]
    sells   = [t for t in week_trades if t["action"] == "SELL"]
    winners = [t for t in sells if (t.get("realised_pnl") or 0) > 0]
    losers  = [t for t in sells if (t.get("realised_pnl") or 0) < 0]
    realised = sum(t.get("realised_pnl") or 0 for t in sells)
    open_pos = [t for t in tl["trades"] if t["action"] == "BUY" and t["status"] == "OPEN"]
    win_rate = round(len(winners) / len(sells) * 100, 1) if sells else 0

    report = {
        "week":           week_key,
        "period":         f"{week_start} to {week_end}",
        "generated_at":   datetime.utcnow().isoformat() + "Z",
        "summary": {
            "total_trades":    len(week_trades),
            "buys":            len(buys),
            "sells":           len(sells),
            "winners":         len(winners),
            "losers":          len(losers),
            "open_positions":  len(open_pos),
            "realised_pnl":    round(realised, 2),
            "win_rate_pct":    win_rate,
            "to_monthly_target": round(2000 - realised, 2),
        },
        "top_winner": max(sells, key=lambda t: t.get("realised_pnl") or 0, default=None) and
                      {"ticker": max(sells, key=lambda t: t.get("realised_pnl") or 0)["ticker"],
                       "pnl":    max(sells, key=lambda t: t.get("realised_pnl") or 0).get("realised_pnl")},
        "notes": f"Week {week_key} auto-generated by trading agent.",
    }

    # Replace existing week report or append
    tl["weekly_reports"] = [r for r in tl["weekly_reports"] if r["week"] != week_key]
    tl["weekly_reports"].insert(0, report)
    # Keep last 12 weeks only
    tl["weekly_reports"] = tl["weekly_reports"][:12]


# ─────────────────────────────────────────────
# Order Execution
# ─────────────────────────────────────────────
def place_order(api: tradeapi.REST, ticker: str, signal: str, qty: int = None,
                details: dict = None, entry_price: float = None):
    qty     = qty or Config.ORDER_QTY
    side    = "buy" if signal == "BUY" else "sell"
    details = details or {}

    if Config.DRY_RUN:
        log.info(f"🧪 [DRY RUN] Would {side.upper()} {qty}x {ticker}")
        _log_trade(ticker, signal, qty, details.get("close", 0), details, entry_price)
        return

    try:
        order = api.submit_order(
            symbol=ticker,
            qty=qty,
            side=side,
            type="market",
            time_in_force="day",
        )
        log.info(f"✅ ORDER SUBMITTED | {side.upper()} {qty}x {ticker} | ID: {order.id}")
        _log_trade(ticker, signal, qty, details.get("close", 0), details, entry_price)
    except Exception as e:
        log.error(f"❌ Order failed [{ticker}]: {e}")


# ─────────────────────────────────────────────
# Summary Report
# ─────────────────────────────────────────────
def print_summary(results: list[dict]):
    buys  = [r for r in results if r["signal"] == "BUY"]
    sells = [r for r in results if r["signal"] == "SELL"]
    holds = [r for r in results if r["signal"] == "HOLD"]
    errors = [r for r in results if r["signal"] == "ERROR"]

    log.info("\n" + "═" * 60)
    log.info(f"  📊  SCAN COMPLETE — {date.today()}")
    log.info("═" * 60)
    log.info(f"  Total Scanned : {len(results)}")
    log.info(f"  🟢 BUY        : {len(buys)}")
    log.info(f"  🔴 SELL       : {len(sells)}")
    log.info(f"  ⚪ HOLD       : {len(holds)}")
    log.info(f"  ⚠️  Errors     : {len(errors)}")
    log.info("─" * 60)

    if buys:
        log.info("  TOP BUY SIGNALS:")
        for r in sorted(buys, key=lambda x: x["details"].get("buy_score", 0), reverse=True)[:10]:
            log.info(f"    • {r['ticker']:<6} | Score {r['details'].get('buy_score',0)}/5 "
                     f"| RSI {r['details'].get('rsi',0):.1f} | ${r['details'].get('close',0):.2f}")

    if sells:
        log.info("  TOP SELL SIGNALS:")
        for r in sells[:10]:
            triggers = [k for k, v in r["details"].get("sell_conditions", {}).items() if v]
            log.info(f"    • {r['ticker']:<6} | Triggers: {', '.join(triggers)}")

    log.info("═" * 60 + "\n")

    # Save CSV summary
    df_out = pd.DataFrame([
        {
            "ticker":     r["ticker"],
            "signal":     r["signal"],
            "close":      r["details"].get("close", ""),
            "rsi":        r["details"].get("rsi", ""),
            "macd_diff":  r["details"].get("macd_diff", ""),
            "sma_50":     r["details"].get("sma_50", ""),
            "sma_200":    r["details"].get("sma_200", ""),
            "buy_score":  r["details"].get("buy_score", ""),
            "timestamp":  datetime.now().isoformat(),
        }
        for r in results if r["signal"] in ("BUY", "SELL")
    ])

    if not df_out.empty:
        out_path = f"logs/signals_{date.today()}.csv"
        df_out.to_csv(out_path, index=False)
        log.info(f"📁 Signal report saved: {out_path}")

    # ── Publish JSON for GitHub Pages dashboard ───────────────────
    _publish_json(results)


# ─────────────────────────────────────────────
# GitHub Pages JSON Publisher
# ─────────────────────────────────────────────
def _publish_json(results: list[dict]):
    """Write docs/signals.json consumed by the GitHub Pages dashboard."""
    os.makedirs("docs", exist_ok=True)

    signals = []
    for r in results:
        if r["signal"] not in ("BUY", "SELL"):
            continue
        d = r.get("details", {})
        buy_conds  = d.get("buy_conditions", {})
        sell_conds = d.get("sell_conditions", {})
        signals.append({
            "ticker":     r["ticker"],
            "signal":     r["signal"],
            "close":      d.get("close", 0),
            "rsi":        d.get("rsi", 0),
            "macd_diff":  d.get("macd_diff", 0),
            "sma_50":     d.get("sma_50", 0),
            "sma_200":    d.get("sma_200", 0),
            "bb_upper":   d.get("bb_upper", 0),
            "bb_lower":   d.get("bb_lower", 0),
            "atr_pct":    d.get("atr_pct", 0),
            "buy_score":  d.get("buy_score", 0),
            "buy_triggers":  [k for k, v in buy_conds.items()  if v],
            "sell_triggers": [k for k, v in sell_conds.items() if v],
        })

    buys   = [r for r in results if r["signal"] == "BUY"]
    sells  = [r for r in results if r["signal"] == "SELL"]
    holds  = [r for r in results if r["signal"] == "HOLD"]
    errors = [r for r in results if r["signal"] == "ERROR"]

    payload = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "scan_date":    str(date.today()),
        "dry_run":      Config.DRY_RUN,
        "summary": {
            "total":  len(results),
            "buy":    len(buys),
            "sell":   len(sells),
            "hold":   len(holds),
            "errors": len(errors),
        },
        "signals": sorted(signals, key=lambda x: (x["signal"], -x["buy_score"])),
    }

    out_path = "docs/signals.json"
    with open(out_path, "w") as f:
        json.dump(payload, f, indent=2)
    log.info(f"🌐 GitHub Pages data published: {out_path}")


# ─────────────────────────────────────────────
# Main Scanner
# ─────────────────────────────────────────────
def run_scanner(api: tradeapi.REST):
    tickers   = get_sp500_tickers()
    positions = get_open_positions(api)

    log.info(f"📈 Open positions: {len(positions)} | Max: {Config.MAX_POSITIONS}")
    log.info(f"🔍 Scanning {len(tickers)} S&P 500 stocks… (DRY_RUN={Config.DRY_RUN})\n")

    results = []

    for ticker in tickers:
        try:
            df = fetch_bars(api, ticker, limit=220)

            if df is None or len(df) < 210:
                results.append({"ticker": ticker, "signal": "HOLD", "details": {"reason": "insufficient_data"}})
                continue

            df = compute_indicators(df)

            if df.iloc[-1][["rsi", "macd_diff", "sma_50", "sma_200"]].isnull().any():
                results.append({"ticker": ticker, "signal": "HOLD", "details": {"reason": "nan_indicators"}})
                continue

            entry_price = positions.get(ticker)
            signal, details = generate_signal(df, entry_price=entry_price)

            results.append({"ticker": ticker, "signal": signal, "details": details})

            if signal in ("BUY", "SELL"):
                print_alert(ticker, signal, details)

                # Don't buy if already at max positions
                if signal == "BUY" and len(positions) >= Config.MAX_POSITIONS:
                    log.info(f"⛔ Max positions reached ({Config.MAX_POSITIONS}). Skipping BUY for {ticker}.")
                    continue

                # Don't sell what we don't own
                if signal == "SELL" and ticker not in positions:
                    log.info(f"ℹ️  SELL signal for {ticker} but no open position. Skipping.")
                    continue

                place_order(api, ticker, signal,
                            details=details, entry_price=entry_price)

                if signal == "SELL" and ticker in positions:
                    del positions[ticker]

            time.sleep(Config.RATE_LIMIT_SEC)

        except KeyboardInterrupt:
            log.warning("⚡ Scanner interrupted by user.")
            break
        except Exception as e:
            log.warning(f"⚠️  {ticker}: {e}")
            results.append({"ticker": ticker, "signal": "ERROR", "details": {"error": str(e)}})

    print_summary(results)


# ─────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────
def main():
    log.info("🚀 Millionaire Stocks Agent — Starting up")
    log.info(f"   Account : {os.environ.get('ALPACA_ACCOUNT_NAME', 'N/A')}")
    log.info(f"   Base URL: {os.environ.get('ALPACA_BASE_URL', 'N/A')}")
    log.info(f"   Dry Run : {os.environ.get('DRY_RUN', 'true')}")

    api = init_client()

    if not is_market_open(api):
        log.info("Market closed — exiting gracefully.")
        sys.exit(0)

    run_scanner(api)
    log.info("✅ Agent finished successfully.")


if __name__ == "__main__":
    main()
