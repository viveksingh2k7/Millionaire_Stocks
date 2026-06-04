"""
Tests for Config validation — ensures missing credentials exit with a clear
error message instead of a cryptic KeyError or silent 401.
"""

import os
import sys
import subprocess
import pytest


def _run_strategy_with_env(env: dict) -> subprocess.CompletedProcess:
    """Spawn a subprocess that imports strategy.py with a custom environment."""
    src = os.path.join(os.path.dirname(__file__), "..", "src", "strategy.py")
    return subprocess.run(
        [sys.executable, "-c", f"import sys; sys.path.insert(0,'src'); import strategy"],
        env={**os.environ, **env},
        capture_output=True,
        text=True,
        cwd=os.path.join(os.path.dirname(__file__), ".."),
    )


class TestConfigValidation:

    def test_missing_api_key_exits_with_message(self):
        result = _run_strategy_with_env({
            "ALPACA_API_KEY":    "",
            "ALPACA_SECRET_KEY": "secret",
            "ALPACA_BASE_URL":   "https://paper-api.alpaca.markets",
        })
        assert result.returncode != 0
        assert "ALPACA_API_KEY" in result.stdout or "ALPACA_API_KEY" in result.stderr

    def test_missing_secret_key_exits_with_message(self):
        result = _run_strategy_with_env({
            "ALPACA_API_KEY":    "key",
            "ALPACA_SECRET_KEY": "",
            "ALPACA_BASE_URL":   "https://paper-api.alpaca.markets",
        })
        assert result.returncode != 0
        assert "ALPACA_SECRET_KEY" in result.stdout or "ALPACA_SECRET_KEY" in result.stderr

    def test_missing_base_url_exits_with_message(self):
        result = _run_strategy_with_env({
            "ALPACA_API_KEY":    "key",
            "ALPACA_SECRET_KEY": "secret",
            "ALPACA_BASE_URL":   "",
        })
        assert result.returncode != 0
        assert "ALPACA_BASE_URL" in result.stdout or "ALPACA_BASE_URL" in result.stderr

    def test_valid_credentials_do_not_exit_at_import(self):
        """Importing strategy.py with valid env should not call sys.exit."""
        result = _run_strategy_with_env({
            "ALPACA_API_KEY":    "valid-key",
            "ALPACA_SECRET_KEY": "valid-secret",
            "ALPACA_BASE_URL":   "https://paper-api.alpaca.markets",
        })
        # returncode 0 = clean import; non-zero only if sys.exit or exception at import time
        assert result.returncode == 0
