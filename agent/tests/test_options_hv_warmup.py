"""Regression: the HV warm-up must not backfill the first computed window.

``historical_volatility`` filled the orphan bars of the 30-day rolling window
with the first valid value -- the volatility computed over bars 1..30, so bars
1..29 were priced with information from bar 30. Warm-up bars now use the
configured default IV instead; bars with a full window keep the real rolling
volatility. (#1293, part 2.)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from backtest.engines.options_portfolio import historical_volatility


def test_warmup_bars_use_default_iv_not_the_first_computed_window() -> None:
    close = pd.Series([100.0] * 40)
    hv = historical_volatility(close)

    # Constant closes: the only rolling volatility anywhere is zero, so the old
    # backfill would plant 0.0 over the warm-up. The first 30 bars must be the
    # default IV instead, the rest the real (zero) rolling volatility.
    assert hv.iloc[:30].eq(0.3).all()
    assert hv.iloc[30:].eq(0.0).all()


def test_default_iv_is_configurable() -> None:
    close = pd.Series([100.0] * 40)
    hv = historical_volatility(close, default_iv=0.5)

    assert hv.iloc[:30].eq(0.5).all()
    assert hv.iloc[30:].eq(0.0).all()


def test_full_window_bars_are_unchanged_by_the_warmup_fix() -> None:
    """A trend keeps its real rolling vol everywhere past the warm-up."""
    close = pd.Series(np.linspace(100.0, 200.0, 60))
    hv = historical_volatility(close)

    log_ret = np.log(close / close.shift(1))
    expected = log_ret.rolling(30).std() * np.sqrt(252)
    pd.testing.assert_series_equal(hv.iloc[30:], expected.iloc[30:].fillna(0.0))
