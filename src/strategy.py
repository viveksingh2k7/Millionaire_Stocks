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
import logging
from datetime import datetime, date

import pandas as pd
import numpy as np
import requests
import alpaca_trade_api as tradeapi
from alpaca_trade_api.rest import TimeFrame
import ta

# ─────────────────────────────────────────────
# Logging Setup
# ─────────────────────────────────────────────
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
# Configuration
# ─────────────────────────────────────────────
class Config:
    API_KEY        = os.environ["ALPACA_API_KEY"]
    SECRET_KEY     = os.environ["ALPACA_SECRET_KEY"]
    BASE_URL       = os.environ["ALPACA_BASE_URL"]
    ACCOUNT_NAME   = os.environ.get("ALPACA_ACCOUNT_NAME", "default")

    DRY_RUN        = os.environ.get("DRY_RUN", "true").lower() == "true"
    ORDER_QTY      = int(os.environ.get("ORDER_QTY", "1"))          # shares per trade
    STOP_LOSS_PCT  = float(os.environ.get("STOP_LOSS_PCT", "0.05")) # 5% stop-loss
    BUY_THRESHOLD  = int(os.environ.get("BUY_THRESHOLD", "3"))      # min conditions for BUY
    MIN_VOLUME     = int(os.environ.get("MIN_VOLUME", "500000"))     # liquidity filter
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
        tables = pd.read_html(url)
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
            adjustment="raw",
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

    # Liquidity & volatility filter
    avg_vol = df["volume"].tail(20).mean()
    atr_pct = latest["atr"] / latest["close"] if latest["close"] > 0 else 1.0

    if avg_vol < Config.MIN_VOLUME:
        return "HOLD", {"reason": "low_volume"}
    if atr_pct > 0.05:
        return "HOLD", {"reason": "high_volatility"}

    # ── BUY conditions ────────────────────────────────────────
    rsi_recovery  = (prev["rsi"] < 30) and (latest["rsi"] >= 30)
    macd_cross_up = (prev["macd_diff"] < 0) and (latest["macd_diff"] >= 0)
    above_sma50   = latest["close"] > latest["sma_50"]
    golden_cross  = latest["sma_50"] > latest["sma_200"]
    near_bb_lower = latest["close"] <= latest["bb_lower"] * 1.015

    buy_conditions = {
        "rsi_recovery":  rsi_recovery,
        "macd_cross_up": macd_cross_up,
        "above_sma50":   above_sma50,
        "golden_cross":  golden_cross,
        "near_bb_lower": near_bb_lower,
    }
    buy_score = sum(buy_conditions.values())

    # ── SELL conditions ───────────────────────────────────────
    rsi_overbought  = latest["rsi"] >= 70
    macd_cross_down = (prev["macd_diff"] > 0) and (latest["macd_diff"] <= 0)
    death_cross     = latest["sma_50"] < latest["sma_200"]
    at_bb_upper     = latest["close"] >= latest["bb_upper"] * 0.99
    stop_loss       = (entry_price is not None) and \
                      (latest["close"] <= entry_price * (1 - Config.STOP_LOSS_PCT))

    sell_conditions = {
        "rsi_overbought":  rsi_overbought,
        "macd_cross_down": macd_cross_down,
        "death_cross":     death_cross,
        "at_bb_upper":     at_bb_upper,
        "stop_loss":       stop_loss,
    }

    details = {
        "rsi":            round(float(latest["rsi"]), 2),
        "macd_diff":      round(float(latest["macd_diff"]), 5),
        "sma_50":         round(float(latest["sma_50"]), 2),
        "sma_200":        round(float(latest["sma_200"]), 2),
        "bb_upper":       round(float(latest["bb_upper"]), 2),
        "bb_lower":       round(float(latest["bb_lower"]), 2),
        "close":          round(float(latest["close"]), 2),
        "atr_pct":        round(atr_pct * 100, 2),
        "buy_score":      buy_score,
        "buy_conditions": buy_conditions,
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
# Order Execution
# ─────────────────────────────────────────────
def place_order(api: tradeapi.REST, ticker: str, signal: str, qty: int = None):
    qty = qty or Config.ORDER_QTY
    side = "buy" if signal == "BUY" else "sell"

    if Config.DRY_RUN:
        log.info(f"🧪 [DRY RUN] Would {side.upper()} {qty}x {ticker}")
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

                place_order(api, ticker, signal)

                if signal == "BUY":
                    positions[ticker] = details["close"]
                elif signal == "SELL" and ticker in positions:
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
