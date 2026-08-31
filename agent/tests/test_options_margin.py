"""Regression (#1294): the options engine now holds margin on short legs and
rejects opens that exceed buying power.

Previously a short open simply credited the premium and cash could go
arbitrarily negative, so naked-selling strategies produced a free-money
curve. The margin model is CBOE-style (premium + max(rate * spot - OTM,
floor * base)), marked daily, with ``margin_enabled: false`` opting back into
the legacy unconstrained behavior for research runs.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from backtest.engines.options_portfolio import run_options_backtest

_DATES = pd.bdate_range("2025-01-01", periods=6)
_BARS = pd.DataFrame(
    {
        "open": [100.0, 100.0, 100.0, 120.0, 120.0, 120.0],
        "high": [101.0, 101.0, 101.0, 121.0, 121.0, 121.0],
        "low": [99.0, 99.0, 99.0, 119.0, 119.0, 119.0],
        "close": [100.0, 100.0, 100.0, 120.0, 120.0, 120.0],
        "volume": [1000] * 6,
    },
    index=_DATES,
)


class _Loader:
    name = "yfinance"

    def fetch(self, codes, start_date, end_date):  # noqa: ANN001
        return {"SPY": _BARS.copy()}


def _engine(signals):
    class _Engine:
        def generate(self, data_map):  # noqa: ANN001
            return signals

    return _Engine()


def _open(date, legs, underlying="SPY"):
    return {"date": date, "action": "open", "underlying": underlying, "legs": legs}


def _close(date, legs, underlying="SPY"):
    return {"date": date, "action": "close", "underlying": underlying, "legs": legs}


def _run(tmp_path: Path, signals, initial_cash=100_000, options_config=None):
    config = {
        "codes": ["SPY"],
        "start_date": "2025-01-01",
        "end_date": "2025-01-08",
        "source": "yfinance",
        "engine": "options",
        "initial_cash": initial_cash,
        "commission": 0.0,
        "options_config": options_config or {"risk_free_rate": 0.0, "contract_multiplier": 1.0},
    }
    run_options_backtest(config, _Loader(), _engine(signals), tmp_path)
    artifacts = tmp_path / "artifacts"
    trades = pd.read_csv(artifacts / "trades.csv")
    equity = pd.read_csv(artifacts / "equity.csv")
    metrics = pd.read_csv(artifacts / "metrics.csv")
    return trades, equity, metrics


def test_naked_short_beyond_buying_power_rejects(tmp_path: Path) -> None:
    # 1 call leg of 500 contracts at spot 100: margin far exceeds the account.
    signals = [_open("2025-01-01", [{"type": "call", "strike": 100.0, "expiry": "2025-03-21", "qty": -500}])]
    trades, equity, metrics = _run(tmp_path, signals, initial_cash=10_000)

    assert trades.iloc[0]["side"] == "reject"
    assert trades.iloc[0]["reason"] == "insufficient buying power"
    assert equity["margin_hold"].max() == 0.0
    assert metrics.iloc[0]["options_rejected_opens"] == 1


def test_short_within_buying_power_posts_margin(tmp_path: Path) -> None:
    signals = [_open("2025-01-01", [{"type": "call", "strike": 110.0, "expiry": "2025-03-21", "qty": -10}])]
    trades, equity, metrics = _run(tmp_path, signals)

    assert trades.iloc[0]["side"] == "sell"
    # CBOE put/call margin on an OTM call at entry (premium + max(20% * spot -
    # OTM, 10% * spot)); the hold must be positive and tracked daily.
    assert equity.iloc[0]["margin_hold"] > 0.0
    # After the underlying jumps to 120, the call is ITM and the hold grows.
    assert equity.iloc[-1]["margin_hold"] > equity.iloc[0]["margin_hold"]


def test_margin_releases_on_close(tmp_path: Path) -> None:
    leg = {"type": "call", "strike": 110.0, "expiry": "2025-03-21", "qty": -10}
    signals = [
        _open("2025-01-01", [leg]),
        _close("2025-01-03", [{"type": "call", "strike": 110.0, "expiry": "2025-03-21"}]),
    ]
    trades, equity, metrics = _run(tmp_path, signals)

    assert trades.iloc[0]["side"] == "sell"
    assert trades.iloc[1]["side"] == "close"
    assert equity.iloc[-1]["margin_hold"] == 0.0


def test_long_open_beyond_buying_power_rejects(tmp_path: Path) -> None:
    signals = [_open("2025-01-01", [{"type": "call", "strike": 100.0, "expiry": "2025-03-21", "qty": 100_000}])]
    trades, equity, metrics = _run(tmp_path, signals, initial_cash=1_000)

    assert trades.iloc[0]["side"] == "reject"
    assert metrics.iloc[0]["options_rejected_opens"] == 1


def test_margin_disabled_restores_unconstrained_behavior(tmp_path: Path) -> None:
    signals = [_open("2025-01-01", [{"type": "call", "strike": 100.0, "expiry": "2025-03-21", "qty": -500}])]
    trades, equity, metrics = _run(
        tmp_path,
        signals,
        initial_cash=10_000,
        options_config={"risk_free_rate": 0.0, "contract_multiplier": 1.0, "margin_enabled": False},
    )

    # Legacy path: the short opens, cash goes negative, no margin is tracked.
    assert trades.iloc[0]["side"] == "sell"
    assert equity["margin_hold"].max() == 0.0
    assert "options_rejected_opens" not in metrics.columns
