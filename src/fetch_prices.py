"""
fetch_prices.py
===============
Fetches real-time quotes via Yahoo Finance's public chart API using
direct HTTP requests with browser-like headers (bypasses the yfinance
library which fails from GitHub Actions IPs).

Endpoint: https://query{1|2}.finance.yahoo.com/v8/finance/chart/{symbol}
          ?interval=1d&range=5d

No API key required. Tries query1 then query2 as fallback.
"""

import json
import os
import sys
import time
import logging
from datetime import datetime, timezone

import requests

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

# Realistic Chrome browser headers to avoid Yahoo Finance IP blocking
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":         "https://finance.yahoo.com/",
    "Origin":          "https://finance.yahoo.com",
    "sec-ch-ua":       '"Google Chrome";v="125","Chromium";v="125","Not.A/Brand";v="24"',
    "sec-ch-ua-mobile":"?0",
    "sec-fetch-dest":  "empty",
    "sec-fetch-mode":  "cors",
    "sec-fetch-site":  "same-site",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


# ── Helpers ──────────────────────────────────────────────────────────
def load_json(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def get_quote(symbol: str) -> dict | None:
    """
    Fetch latest price for `symbol` via Yahoo Finance v8 chart API.
    Tries query1 → query2 as fallback.
    Returns {price, prev_close, change, change_pct, currency} or None.
    """
    params = {
        "interval":      "1d",
        "range":         "5d",
        "includePrePost":"false",
    }

    for host in ["https://query1.finance.yahoo.com", "https://query2.finance.yahoo.com"]:
        url = f"{host}/v8/finance/chart/{symbol}"
        try:
            resp = SESSION.get(url, params=params, timeout=15)
            if not resp.ok:
                log.debug(f"  {symbol} → {host} HTTP {resp.status_code}")
                continue

            data   = resp.json()
            result = data.get("chart", {}).get("result")
            if not result:
                log.debug(f"  {symbol} → empty result from {host}")
                continue

            meta  = result[0].get("meta", {})
            price = (
                meta.get("regularMarketPrice") or
                meta.get("postMarketPrice")    or
                meta.get("previousClose")
            )
            prev = (
                meta.get("chartPreviousClose") or
                meta.get("previousClose")
            )

            if not price:
                continue

            price = float(price)
            prev  = float(prev) if prev else None
            change     = round(price - prev, 4)       if prev else None
            change_pct = round((price - prev) / prev * 100, 4) if prev else None

            return {
                "price":      round(price, 4),
                "prev_close": round(prev, 4) if prev else None,
                "change":     change,
                "change_pct": change_pct,
                "currency":   (meta.get("currency") or "USD").upper(),
            }

        except Exception as e:
            log.debug(f"  {symbol} → {host} exception: {e}")
            continue

    return None


def gbp_to_usd(pence: float, rate: float) -> float:
    return round((pence / 100.0) * rate, 4)


# ── Main ─────────────────────────────────────────────────────────────
def main():
    os.makedirs("docs", exist_ok=True)

    portfolio = load_json(PORTFOLIO_PATH)
    signals   = load_json(SIGNALS_PATH)

    port_holdings = portfolio.get("holdings", [])
    sig_symbols   = list({s["ticker"] for s in signals.get("signals", [])})

    # ── 1. GBP/USD rate ───────────────────────────────────────────────
    log.info("📡 Fetching GBP/USD rate…")
    fx = get_quote(GBP_USD_TICKER)
    gbp_usd = fx["price"] if fx else 1.2700
    log.info(f"   GBP/USD = {gbp_usd:.4f}")

    # ── 2. Portfolio quotes ────────────────────────────────────────────
    log.info(f"📡 Fetching {len(port_holdings)} portfolio quotes…")
    portfolio_prices = []

    for h in port_holdings:
        sym = h["yahoo_symbol"]
        cur = (h.get("currency") or "USD").upper()

        log.info(f"   {sym}…")
        q = get_quote(sym)
        time.sleep(0.4)

        if q:
            raw   = q["price"]
            q_cur = q["currency"]

            # WISE.L is quoted in GBp (pence) by Yahoo Finance → convert to USD
            if q_cur in ("GBP", "GBP") or sym.endswith(".L"):
                price_usd  = gbp_to_usd(raw, gbp_usd)
                change_usd = gbp_to_usd(q["change"], gbp_usd) if q["change"] else None
                log.info(f"   {sym}: {raw:.2f}p → ${price_usd:.4f} USD  ({q['change_pct']:+.2f}%)" if q["change_pct"] else f"   {sym}: {raw:.2f}p → ${price_usd:.4f}")
            else:
                price_usd  = raw
                change_usd = q["change"]
                log.info(f"   {sym}: ${price_usd:.4f}  ({q['change_pct']:+.2f}%)" if q["change_pct"] else f"   {sym}: ${price_usd:.4f}")

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
                "gbp_usd_rate":  round(gbp_usd, 4) if sym.endswith(".L") else None,
            })
        else:
            log.warning(f"   {sym}: ⚠ no price returned")
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

    # ── 3. Signal quotes (best-effort) ─────────────────────────────────
    log.info(f"📡 Fetching {len(sig_symbols)} signal quotes…")
    signal_prices = {}

    for sym in sig_symbols:
        q = get_quote(sym)
        time.sleep(0.25)
        if q:
            signal_prices[sym] = {
                "price":      q["price"],
                "change":     q["change"],
                "change_pct": q["change_pct"],
                "prev_close": q["prev_close"],
            }
            log.info(f"   {sym:<8} ${q['price']:.2f}  {q['change_pct']:+.2f}%" if q["change_pct"] else f"   {sym:<8} ${q['price']:.2f}")
        else:
            log.warning(f"   {sym}: skipped")

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
    log.info(f"✅ {OUT_PATH} — {filled}/{len(portfolio_prices)} portfolio + {len(signal_prices)} signal prices written")

    if filled == 0:
        log.error("❌ All portfolio prices are null — Yahoo Finance may be blocking this IP")
        sys.exit(1)   # fail the workflow so it's visible in Actions


if __name__ == "__main__":
    main()
