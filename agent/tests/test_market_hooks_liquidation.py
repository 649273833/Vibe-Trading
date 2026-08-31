"""Non-strict crypto liquidation must not exempt 1x shorts (#1291).

A leverage <= 1 exemption makes sense for a long -- bankruptcy price is zero --
but a 1x short survives an unbounded adverse move with equity below zero. The
hook also marks at the close instead of the adverse extremum, so a wick that
would liquidate any real position is ignored when high/low are present.
"""

from __future__ import annotations

import pandas as pd

from backtest.engines._market_hooks import check_crypto_liquidation
from backtest.models import Position


def _pos(direction: int, leverage: float = 1.0, entry: float = 100.0, size: float = 10.0) -> Position:
    return Position(
        "BTC-USDT-PERP", direction, entry, pd.Timestamp("2026-01-05"), size, leverage
    )


def _bar(close: float, high: float | None = None, low: float | None = None) -> pd.Series:
    row = {"close": close}
    if high is not None:
        row["high"] = high
    if low is not None:
        row["low"] = low
    return pd.Series(row)


def test_1x_short_liquidates_through_twice_the_entry_price() -> None:
    """Margin is the full notional; a 2x adverse move zeroes it."""
    bar = _bar(close=200.0, high=200.0, low=101.0)
    assert check_crypto_liquidation(
        "BTC-USDT-PERP", bar, {"BTC-USDT-PERP": _pos(direction=-1)}
    ) is True


def test_1x_short_favorable_move_survives() -> None:
    """Dropping the exemption must not over-liquidate a profitable short."""
    bar = _bar(close=50.0, high=51.0, low=49.0)
    assert check_crypto_liquidation(
        "BTC-USDT-PERP", bar, {"BTC-USDT-PERP": _pos(direction=-1)}
    ) is False


def test_1x_long_survives_ninety_percent_drawdown() -> None:
    """The direction-aware exemption keeps the 1x long protection."""
    bar = _bar(close=10.0, high=101.0, low=9.0)
    assert check_crypto_liquidation(
        "BTC-USDT-PERP", bar, {"BTC-USDT-PERP": _pos(direction=1)}
    ) is False


def test_wick_through_maintenance_triggers_when_high_low_present() -> None:
    """A levered long whose low pierces the maintenance margin is liquidated."""
    bar = _bar(close=100.0, high=101.0, low=30.0)
    assert check_crypto_liquidation(
        "BTC-USDT-PERP",
        bar,
        {"BTC-USDT-PERP": _pos(direction=1, leverage=2.0)},
    ) is True


def test_close_only_bar_keeps_legacy_behavior() -> None:
    """Without high/low, close-only bars mark at the close as before."""
    bar = _bar(close=100.0)
    assert check_crypto_liquidation(
        "BTC-USDT-PERP",
        bar,
        {"BTC-USDT-PERP": _pos(direction=1, leverage=2.0)},
    ) is False


def test_adverse_close_without_extremum_still_triggers_short() -> None:
    """A short marked at a catastrophic close liquidates even on close-only bars."""
    bar = _bar(close=250.0)
    assert check_crypto_liquidation(
        "BTC-USDT-PERP", bar, {"BTC-USDT-PERP": _pos(direction=-1)}
    ) is True
