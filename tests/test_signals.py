"""
Unit tests for generate_signal() — covers all BUY / SELL / HOLD paths
including stop-loss, filters, and edge cases.
No Alpaca API credentials required.
"""

import numpy as np
import pandas as pd
import pytest
import sys
import os

os.environ.setdefault("ALPACA_API_KEY",    "test-key")
os.environ.setdefault("ALPACA_SECRET_KEY", "test-secret")
os.environ.setdefault("ALPACA_BASE_URL",   "https://paper-api.alpaca.markets")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from strategy import compute_indicators, generate_signal, Config  # noqa: E402


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _base_row() -> dict:
    """Indicator values for a neutral HOLD stock."""
    return {
        "open":       100.0,
        "high":       101.0,
        "low":        99.0,
        "close":      100.0,
        "volume":     1_000_000.0,
        "rsi":        50.0,
        "macd":       0.0,
        "macd_signal":0.0,
        "macd_diff":  0.0,
        "sma_50":     98.0,
        "sma_200":    95.0,
        "bb_upper":   110.0,
        "bb_lower":   90.0,
        "bb_mid":     100.0,
        "atr":        1.5,       # atr_pct = 1.5% → passes volatility filter
    }


def _make_df(overrides_last: dict = None, overrides_prev: dict = None) -> pd.DataFrame:
    """Build a 2-row DataFrame with optional per-row overrides."""
    prev_row = _base_row()
    last_row = _base_row()
    if overrides_prev:
        prev_row.update(overrides_prev)
    if overrides_last:
        last_row.update(overrides_last)
    df = pd.DataFrame(
        [prev_row, last_row],
        index=pd.date_range("2024-01-01", periods=2, freq="B"),
    )
    return df


# ─────────────────────────────────────────────
# Tests — HOLD filters
# ─────────────────────────────────────────────

class TestHoldFilters:

    def test_low_volume_returns_hold(self):
        df = _make_df(overrides_last={"volume": 100_000})
        # Fill all 20 volume rows with low volume
        big_df = pd.concat([_make_df(overrides_last={"volume": 100_000})] * 10, ignore_index=True)
        big_df.index = pd.date_range("2024-01-01", periods=len(big_df), freq="B")
        signal, details = generate_signal(big_df)
        assert signal == "HOLD"
        assert details.get("reason") == "low_volume"

    def test_high_volatility_returns_hold(self):
        # atr_pct > 5% → HOLD
        df = _make_df(overrides_last={"atr": 6.0, "close": 100.0})
        signal, details = generate_signal(df)
        assert signal == "HOLD"
        assert details.get("reason") == "high_volatility"


# ─────────────────────────────────────────────
# Tests — BUY signals
# ─────────────────────────────────────────────

class TestBuySignals:

    def test_buy_on_rsi_recovery_plus_two_more(self):
        """RSI recovery + MACD cross-up + above SMA-50 → score=3 → BUY."""
        df = _make_df(
            overrides_prev={"rsi": 28.0, "macd_diff": -0.1},
            overrides_last={
                "rsi":      32.0,   # rsi_recovery ✓
                "macd_diff": 0.1,   # macd_cross_up ✓
                "close":    99.0,   # above_sma50 ✓ (sma_50=98)
                "sma_50":   98.0,
                "sma_200":  95.0,
            },
        )
        signal, details = generate_signal(df)
        assert signal == "BUY"
        assert details["buy_score"] >= Config.BUY_THRESHOLD

    def test_buy_score_below_threshold_is_hold(self):
        """Only 2 conditions met → HOLD."""
        df = _make_df(
            overrides_prev={"rsi": 28.0, "macd_diff": -0.1},
            overrides_last={
                "rsi":      32.0,   # rsi_recovery ✓
                "macd_diff": 0.1,   # macd_cross_up ✓
                "close":    94.0,   # above_sma50 ✗ (sma_50=98)
                "sma_50":   98.0,
                "sma_200":  99.0,   # golden_cross ✗
                "bb_lower": 88.0,   # near_bb_lower ✗ (close=94, 88*1.015=89.3)
            },
        )
        signal, details = generate_signal(df)
        assert signal in ("HOLD", "SELL")
        if signal == "HOLD":
            assert details.get("buy_score", 0) < Config.BUY_THRESHOLD

    def test_golden_cross_contributes_to_buy(self):
        """SMA-50 > SMA-200 is one of the BUY conditions."""
        df = _make_df(
            overrides_last={"sma_50": 102.0, "sma_200": 98.0}
        )
        _, details = generate_signal(df)
        assert details["buy_conditions"]["golden_cross"] is True

    def test_near_bb_lower_contributes_to_buy(self):
        """close <= bb_lower * 1.015 fires near_bb_lower."""
        df = _make_df(
            overrides_last={"close": 90.5, "bb_lower": 90.0}   # 90.5 <= 90*1.015=91.35 ✓
        )
        _, details = generate_signal(df)
        assert details["buy_conditions"]["near_bb_lower"] is True


# ─────────────────────────────────────────────
# Tests — SELL signals
# ─────────────────────────────────────────────

class TestSellSignals:

    def test_rsi_overbought_triggers_sell(self):
        df = _make_df(overrides_last={"rsi": 75.0})
        signal, details = generate_signal(df)
        assert signal == "SELL"
        assert details["sell_conditions"]["rsi_overbought"] is True

    def test_macd_cross_down_triggers_sell(self):
        df = _make_df(
            overrides_prev={"macd_diff": 0.5},
            overrides_last={"macd_diff": -0.1},
        )
        signal, details = generate_signal(df)
        assert signal == "SELL"
        assert details["sell_conditions"]["macd_cross_down"] is True

    def test_death_cross_triggers_sell(self):
        df = _make_df(
            overrides_last={"sma_50": 90.0, "sma_200": 95.0}
        )
        signal, details = generate_signal(df)
        assert signal == "SELL"
        assert details["sell_conditions"]["death_cross"] is True

    def test_at_bb_upper_triggers_sell(self):
        """close >= bb_upper * 0.99 fires at_bb_upper."""
        df = _make_df(
            overrides_last={"close": 109.5, "bb_upper": 110.0}  # 109.5 >= 110*0.99=108.9 ✓
        )
        signal, details = generate_signal(df)
        assert signal == "SELL"
        assert details["sell_conditions"]["at_bb_upper"] is True

    def test_stop_loss_triggers_sell(self):
        """Price drops 6% below entry → stop-loss fires (threshold=5%)."""
        df = _make_df(overrides_last={"close": 93.0})
        entry = 100.0  # 93 <= 100 * 0.95 → stop_loss ✓
        signal, details = generate_signal(df, entry_price=entry)
        assert signal == "SELL"
        assert details["sell_conditions"]["stop_loss"] is True

    def test_stop_loss_not_triggered_without_entry_price(self):
        """No entry_price → stop_loss condition must be False."""
        df = _make_df(overrides_last={"close": 80.0})
        _, details = generate_signal(df, entry_price=None)
        assert details["sell_conditions"]["stop_loss"] is False

    def test_stop_loss_not_triggered_when_price_above_threshold(self):
        """Price only 2% below entry → stop-loss should NOT fire."""
        df = _make_df(overrides_last={"close": 98.0})
        entry = 100.0
        _, details = generate_signal(df, entry_price=entry)
        assert details["sell_conditions"]["stop_loss"] is False


# ─────────────────────────────────────────────
# Tests — details dict completeness
# ─────────────────────────────────────────────

class TestDetailsDict:

    EXPECTED_KEYS = [
        "rsi", "macd_diff", "sma_50", "sma_200",
        "bb_upper", "bb_lower", "close", "atr_pct",
        "buy_score", "buy_conditions", "sell_conditions",
    ]

    def test_details_contains_all_keys_on_buy(self):
        df = _make_df(
            overrides_prev={"rsi": 28.0, "macd_diff": -0.1},
            overrides_last={"rsi": 32.0, "macd_diff": 0.1, "close": 99.0},
        )
        _, details = generate_signal(df)
        for key in self.EXPECTED_KEYS:
            assert key in details, f"Missing key in details: {key}"

    def test_buy_score_is_integer(self):
        df = _make_df()
        _, details = generate_signal(df)
        assert isinstance(details.get("buy_score", None), int)
