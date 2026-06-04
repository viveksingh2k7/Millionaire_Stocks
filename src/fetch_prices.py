"""
fetch_prices.py
===============
Fetches real-time / latest quotes for portfolio tickers and all signal
tickers, then writes docs/prices.json for the GitHub Pages dashboard.

Uses three fallback methods per ticker so we always get a price:
  1. yf.Ticker.fast_info.last_price        (fastest, sometimes None)
  2. yf.Ticker.info regularMarketPrice     (reliable, slightly slower)
  3. yf.Ticker.history(period='2d')        (always works, uses last close)

Run by .github/workflows/prices.yml every 15 min, 7 AM–9 PM CST.
"""

import json
import os
import sys
import time
import logging
from datetime import datetime, timezone

import yfinance as yf

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

PORTFOLIO_PATH = "docs/portfolio.json"
SIGNALS_PATH   = "docs/signals.json"
OUT_PATH       = "docs/prices.json"
GBP_USD_TICKER = "GBPUSD=X"


# ── Helpers ───────────────────────────────────────────────────────────
def load_json(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def get_quote(ticker_sym: str) -> dict | None:
    """
    Fetch price + change for one ticker using three fallback strategies.
    Returns dict with keys: price, prev_close, change, change_pct, currency
    or None on complete failure.
    """
    try:
        t = yf.Ticker(ticker_sym)

        price      = None
        prev_close = None
        currency   = "USD"

        # ── Strategy 1: fast_info ──────────────────────────────────────
        try:
            fi = t.fast_info
            price      = getattr(fi, "last_price",      None)
            prev_close = getattr(fi, "previous_close",  None)
            currency   = getattr(fi, "currency",        "USD") or "USD"
        except Exception:
            pass

        # ── Strategy 2: info dict (more reliable) ─────────────────────
        if not price:
            try:
                info = t.info
                price = (
                    info.get("regularMarketPrice") or
                    info.get("currentPrice")       or
                    info.get("ask")                or
                    info.get("bid")
                )
                prev_close = info.get("regularMarketPreviousClose") or info.get("previousClose")
                currency   = info.get("currency", "USD") or "USD"
            except Exception:
                pass

        # ── Strategy 3: history (always gives at least last close) ─────
        if not price:
            try:
                hist = t.history(period="2d")
                if not hist.empty:
                    price      = float(hist["Close"].iloc[-1])
                    prev_close = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else None
            except Exception:
                pass

        if price is None:
            return None

        price      = float(price)
        prev_close = float(prev_close) if prev_close else None
        change     = round(price - prev_close, 4) if prev_close else None
        change_pct = round((price - prev_close) / prev_close * 100, 4) if prev_close else None

        return {
            "price":      round(price, 4),
            "prev_close": round(prev_close, 4) if prev_close else None,
            "change":     change,
            "change_pct": change_pct,
            "currency":   currency.upper(),
        }

    except Exception as e:
        log.warning(f"  {ticker_sym}: complete failure — {e}")
        return None


def gbp_to_usd(pence: float, rate: float) -> float:
    """GBp (pence) → USD via live GBP/USD rate."""
    return round((pence / 100.0) * rate, 4)


# ── Main ──────────────────────────────────────────────────────────────
def main():
    os.makedirs("docs", exist_ok=True)

    portfolio = load_json(PORTFOLIO_PATH)
    signals   = load_json(SIGNALS_PATH)

    port_holdings = portfolio.get("holdings", [])
    sig_symbols   = list({s["ticker"] for s in signals.get("signals", [])})

    # ── 1. Fetch GBP/USD rate first ────────────────────────────────────
    log.info("Fetching GBP/USD rate…")
    fx = get_quote(GBP_USD_TICKER)
    gbp_usd = fx["price"] if fx else 1.27
    log.info(f"  GBP/USD = {gbp_usd:.4f}")

    # ── 2. Fetch portfolio quotes ──────────────────────────────────────
    log.info(f"Fetching {len(port_holdings)} portfolio quotes…")
    portfolio_prices = []

    for h in port_holdings:
        sym = h["yahoo_symbol"]
        log.info(f"  Fetching {sym}…")
        q = get_quote(sym)
        time.sleep(0.3)

        cur = (h.get("currency") or "USD").upper()

        if q:
            raw_price = q["price"]
            # WISE.L is quoted in GBp (pence) — convert to USD
            if cur in ("GBP", "GBp") or (q["currency"] in ("GBP", "GBp")):
                price_usd  = gbp_to_usd(raw_price, gbp_usd)
                change_usd = gbp_to_usd(q["change"], gbp_usd) if q["change"] else None
                log.info(f"    {sym}: {raw_price}p → ${price_usd:.4f} USD")
            else:
                price_usd  = raw_price
                change_usd = q["change"]
                log.info(f"    {sym}: ${price_usd:.4f}")

            portfolio_prices.append({
                "ticker":        h["ticker"],
                "yahoo_symbol":  sym,
                "name":          h["name"],
                "shares":        h["shares"],
                "avg_cost_usd":  h["avg_cost"],
                "price_usd":     price_usd,
                "change_usd":    round(change_usd, 4) if change_usd else None,
                "change_pct":    q["change_pct"],
                "prev_close_raw":q["prev_close"],
                "currency":      cur,
                "gbp_usd_rate":  round(gbp_usd, 4) if cur in ("GBP","GBp") else None,
            })
        else:
            log.warning(f"    {sym}: no price — keeping placeholder")
            portfolio_prices.append({
                "ticker":        h["ticker"],
                "yahoo_symbol":  sym,
                "name":          h["name"],
                "shares":        h["shares"],
                "avg_cost_usd":  h["avg_cost"],
                "price_usd":     None,
                "change_usd":    None,
                "change_pct":    None,
                "prev_close_raw":None,
                "currency":      cur,
                "gbp_usd_rate":  None,
            })

    # ── 3. Fetch signal quotes (batch — best-effort) ───────────────────
    log.info(f"Fetching {len(sig_symbols)} signal quotes…")
    signal_prices = {}

    for sym in sig_symbols:
        q = get_quote(sym)
        time.sleep(0.2)
        if q:
            signal_prices[sym] = {
                "price":      q["price"],
                "change":     q["change"],
                "change_pct": q["change_pct"],
                "prev_close": q["prev_close"],
            }
            log.info(f"  {sym:<8} ${q['price']:.2f}  ({q['change_pct']:+.2f}%)" if q["change_pct"] else f"  {sym:<8} ${q['price']:.2f}")
        else:
            log.warning(f"  {sym}: skipped")

    # ── 4. Write output ────────────────────────────────────────────────
    payload = {
        "fetched_at":    datetime.now(timezone.utc).isoformat(),
        "gbp_usd_rate":  round(gbp_usd, 4),
        "portfolio":     portfolio_prices,
        "signal_prices": signal_prices,
    }

    with open(OUT_PATH, "w") as f:
        json.dump(payload, f, indent=2)

    filled = sum(1 for p in portfolio_prices if p["price_usd"])
    log.info(f"✅ {OUT_PATH} written — {filled}/{len(portfolio_prices)} portfolio + {len(signal_prices)} signal prices")


if __name__ == "__main__":
    main()
