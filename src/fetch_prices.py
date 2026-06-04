"""
fetch_prices.py
===============
Fetches real-time quotes for every ticker in portfolio.json and all
signal tickers, then writes docs/prices.json for the GitHub Pages dashboard.

Run by .github/workflows/prices.yml on a 15-minute schedule during
market hours (Mon–Fri 09:30–16:15 ET).

Usage:
    python src/fetch_prices.py
"""

import json
import os
import sys
import time
import logging
from datetime import datetime, timezone

import yfinance as yf

# ── Logging ──────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

PORTFOLIO_PATH = "docs/portfolio.json"
SIGNALS_PATH   = "docs/signals.json"
OUT_PATH       = "docs/prices.json"
GBP_USD_TICKER = "GBPUSD=X"   # for converting Wise LSE pence → USD


# ── Helpers ──────────────────────────────────────────────────────────
def load_json(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def gbp_to_usd(gbp_usd_rate: float, pence: float) -> float:
    """Convert pence (GBp) to USD."""
    gbp = pence / 100.0
    return round(gbp * gbp_usd_rate, 4)


# ── Main ──────────────────────────────────────────────────────────────
def main():
    os.makedirs("docs", exist_ok=True)

    portfolio = load_json(PORTFOLIO_PATH)
    signals   = load_json(SIGNALS_PATH)

    # Collect all yahoo symbols to fetch
    port_holdings = portfolio.get("holdings", [])
    port_symbols  = [h["yahoo_symbol"] for h in port_holdings]

    # Signal tickers (US stocks only — already in USD)
    sig_symbols = list({s["ticker"] for s in signals.get("signals", [])})

    # Deduplicate; always include GBP/USD for WISE conversion
    all_symbols = list(dict.fromkeys([GBP_USD_TICKER] + port_symbols + sig_symbols))

    log.info(f"Fetching {len(all_symbols)} quotes via yfinance…")

    # Batch download — period="1d" gives latest close; fast=True for quotes
    raw: dict[str, float] = {}
    raw_meta: dict[str, dict] = {}

    try:
        tickers = yf.Tickers(" ".join(all_symbols))
        for sym in all_symbols:
            try:
                info = tickers.tickers[sym].fast_info
                price = getattr(info, "last_price", None) \
                     or getattr(info, "previous_close", None)
                prev  = getattr(info, "previous_close", None)
                mktcap = getattr(info, "market_cap", None)
                if price:
                    raw[sym] = float(price)
                    raw_meta[sym] = {
                        "price":         round(float(price), 4),
                        "prev_close":    round(float(prev), 4)  if prev  else None,
                        "change":        round(float(price - prev), 4) if prev else None,
                        "change_pct":    round((price - prev) / prev * 100, 4) if prev else None,
                        "market_cap":    mktcap,
                        "currency":      getattr(info, "currency", "USD"),
                    }
                    log.info(f"  {sym:<12} ${price:.4f}")
                else:
                    log.warning(f"  {sym:<12} no price returned")
            except Exception as e:
                log.warning(f"  {sym}: {e}")
            time.sleep(0.1)   # gentle rate limiting
    except Exception as e:
        log.error(f"Batch fetch failed: {e}")
        sys.exit(1)

    # ── Build portfolio prices (with currency conversion) ──────────────
    gbp_usd = raw.get(GBP_USD_TICKER, 1.27)   # fallback 1.27 if FX unavailable
    log.info(f"GBP/USD rate: {gbp_usd:.4f}")

    portfolio_prices = []
    for h in port_holdings:
        sym   = h["yahoo_symbol"]
        meta  = raw_meta.get(sym, {})
        price = meta.get("price")
        cur   = (h.get("currency") or "USD").upper()

        # Convert GBp (pence) → USD for Wise LSE
        if price and cur == "GBP" or cur == "GBP":
            # Yahoo Finance returns GBp in pence for WISE.L
            price_usd = gbp_to_usd(gbp_usd, price) if price else None
            change_usd = gbp_to_usd(gbp_usd, meta["change"]) if meta.get("change") else None
        elif price and cur == "GBp":
            price_usd = gbp_to_usd(gbp_usd, price) if price else None
            change_usd = gbp_to_usd(gbp_usd, meta["change"]) if meta.get("change") else None
        else:
            price_usd  = price
            change_usd = meta.get("change")

        portfolio_prices.append({
            "ticker":        h["ticker"],
            "yahoo_symbol":  sym,
            "name":          h["name"],
            "shares":        h["shares"],
            "avg_cost_usd":  h["avg_cost"],
            "price_usd":     round(price_usd, 4)   if price_usd  else None,
            "change_usd":    round(change_usd, 4)  if change_usd else None,
            "change_pct":    meta.get("change_pct"),
            "prev_close_raw":meta.get("prev_close"),
            "currency":      cur,
            "gbp_usd_rate":  round(gbp_usd, 4)     if cur in ("GBP","GBp") else None,
        })

    # ── Build signal prices ────────────────────────────────────────────
    signal_prices = {}
    for sym in sig_symbols:
        meta = raw_meta.get(sym, {})
        if meta.get("price"):
            signal_prices[sym] = {
                "price":      meta["price"],
                "change":     meta.get("change"),
                "change_pct": meta.get("change_pct"),
                "prev_close": meta.get("prev_close"),
            }

    # ── Write output ────────────────────────────────────────────────────
    payload = {
        "fetched_at":     datetime.now(timezone.utc).isoformat(),
        "gbp_usd_rate":   round(gbp_usd, 4),
        "portfolio":      portfolio_prices,
        "signal_prices":  signal_prices,
    }

    with open(OUT_PATH, "w") as f:
        json.dump(payload, f, indent=2)

    log.info(f"✅ Wrote {OUT_PATH}  ({len(portfolio_prices)} positions, {len(signal_prices)} signals)")


if __name__ == "__main__":
    main()
